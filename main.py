import os
import asyncio
import threading
import json
import requests
import io
import logging
from flask import Flask, request
from pyrogram import Client, filters
from pyrogram.types import (
    Message, ReplyKeyboardMarkup,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.enums import ChatAction
import assemblyai as aai

flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7770743573:AAF9mwgq3efTrJ5iaXQu5VVfnFijUxPsAsg"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"
GEMINI_API_KEY = "AIzaSyAKrnVxMMPIqSzovoUggXy5CQ_4Hi7I_NU"
REQUEST_TIMEOUT_GEMINI = 300

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

aai.settings.api_key = ASSEMBLYAI_API_KEY

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

LANGS = [
("🇬🇧 English","en"), ("🇸🇦 العربية","ar"), ("🇪🇸 Español","es"), ("🇫🇷 Français","fr"),
("🇷🇺 Русский","ru"), ("🇩🇪 Deutsch","de"), ("🇮🇳 हिन्दी","hi"), ("🇮🇷 فارسی","fa"),
("🇮🇩 Indonesia","id"), ("🇺🇦 Українська","uk"), ("🇦🇿 Azərbaycan","az"), ("🇮🇹 Italiano","it"),
("🇹🇷 Türkçe","tr"), ("🇧🇬 Български","bg"), ("🇷🇸 Srpski","sr"), ("🇵🇰 اردو","ur"),
("🇹🇭 ไทย","th"), ("🇻🇳 Tiếng Việt","vi"), ("🇯🇵 日本語","ja"), ("🇰🇷 한국어","ko"),
("🇨🇳 中文","zh"), ("🇳🇱 Nederlands:nl", "nl"), ("🇸🇪 Svenska","sv"), ("🇳🇴 Norsk","no"),
("🇮🇱 עברית","he"), ("🇩🇰 Dansk","da"), ("🇪🇹 አማርኛ","am"), ("🇫🇮 Suomi","fi"),
("🇧🇩 বাংলা","bn"), ("🇰🇪 Kiswahili","sw"), ("🇪🇹 Oromoo","om"), ("🇳🇵 नेपाली","ne"),
("🇵🇱 Polski","pl"), ("🇬🇷 Ελληνικά","el"), ("🇨🇿 Čeština","cs"), ("🇮🇸 Íslenska","is"),
("🇱🇹 Lietuvių","lt"), ("🇱🇻 Latviešu","lv"), ("🇭🇷 Hrvatski","hr"), ("🇷🇸 Bosanski","bs"),
("🇭🇺 Magyar","hu"), ("🇷🇴 Română","ro"), ("🇸🇴 Somali","so"), ("🇲🇾 Melayu","ms"),
("🇺🇿 O'zbekcha","uz"), ("🇵🇭 Tagalog","tl"), ("🇵🇹 Português","pt")
]

LABELS = [label for label,code in LANGS]
LABEL_TO_CODE = {label: code for label,code in LANGS}
user_lang = {}
user_mode = {}
user_transcriptions = {}
action_usage = {}

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def ask_gemini(text, instruction, timeout=REQUEST_TIMEOUT_GEMINI):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": instruction}, {"text": text}]}]}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        if "candidates" in result and isinstance(result["candidates"], list) and len(result["candidates"]) > 0:
            try:
                return result['candidates'][0]['content']['parts'][0]['text']
            except Exception:
                return json.dumps(result['candidates'][0])
        raise RuntimeError(f"Gemini response lacks candidates: {json.dumps(result)}")
    except Exception as e:
        logging.warning(f"Gemini API key failed: {str(e)}.")
        raise RuntimeError(f"Gemini API failed. Error: {str(e)}")

def build_action_keyboard(chat_id, message_id, text_length):
    buttons = []
    buttons.append(
        [InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}")]
    )
    if text_length > 1000:
        buttons.append(
            [InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")]
        )
    return InlineKeyboardMarkup(buttons)

async def download_media(message: Message, file_path: str) -> str:
    await message.download(file_path)
    return file_path

def transcribe_file(file_path: str, lang_code: str = "en") -> str:
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcript = transcriber.transcribe(file_path, config)
    if transcript.error:
        return f"Error: {transcript.error}"
    return transcript.text

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    buttons, row = [], []
    for i, label in enumerate(LABELS, 1):
        row.append(label)
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text("Choose your **language**:", reply_markup=keyboard)

@app.on_message(filters.command("mode") & filters.private)
async def choose_mode(client, message: Message):
    keyboard = ReplyKeyboardMarkup([["💬 Split messages", "📄 Text File"]], resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text("Choose **output mode**:", reply_markup=keyboard)

@app.on_message(filters.private & filters.text)
async def handle_text(client, message: Message):
    text = message.text
    uid = message.from_user.id
    if text in LABEL_TO_CODE:
        code = LABEL_TO_CODE[text]
        user_lang[uid] = code
        await message.reply_text(f"Language set to: **{code}**")
        return
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        await message.reply_text(f"Output mode set to: **{text}**")
        return

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message: Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "en")
    mode = user_mode.get(uid, "📄 Text File")
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    ext = ""
    if message.audio:
        ext = ".mp3"
    elif message.voice:
        ext = ".ogg"
    elif message.video:
        ext = ".mp4"
    elif message.document:
        ext = os.path.splitext(message.document.file_name or "")[1] or ""
    file_path = os.path.join(DOWNLOADS_DIR, f"{message.id}{ext}")
    try:
        await download_media(message, file_path)
    except Exception as e:
        await message.reply_text(f"⚠️ Download error: {e}")
        return
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_file, file_path, lang)
    except Exception as e:
        await message.reply_text(f"❌ Transcription error: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    if not text or text.startswith("Error:"):
        await message.reply_text(text or "⚠️ Warning Make sure the voice is clear or speaking in the language you Choosed.", reply_to_message_id=message.id)
        return

    reply_msg_id = message.id
    sent_message = None
    
    if len(text) > 4000:
        if mode == "💬 Split messages":
            for part in [text[i:i+4000] for i in range(0, len(text), 4000)]:
                await client.send_chat_action(message.chat.id, ChatAction.TYPING)
                sent_message = await message.reply_text(part, reply_to_message_id=reply_msg_id)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{message.id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
            sent_message = await message.reply_document(file_name, caption="Open this file and copy the text inside 👍", reply_to_message_id=reply_msg_id)
            os.remove(file_name)
    else:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        sent_message = await message.reply_text(text, reply_to_message_id=reply_msg_id)

    if sent_message:
        try:
            keyboard = build_action_keyboard(sent_message.chat.id, sent_message.id, len(text))
            user_transcriptions.setdefault(sent_message.chat.id, {})[sent_message.id] = text
            
            action_usage[f"{sent_message.chat.id}|{sent_message.id}|clean"] = 0
            if len(text) > 1000:
                action_usage[f"{sent_message.chat.id}|{sent_message.id}|summarize"] = 0
            
            if message.document or mode == "📄 Text File":
                await sent_message.edit_reply_markup(keyboard)
            else:
                await sent_message.edit_reply_markup(keyboard)
        except Exception as e:
            logging.error(f"Failed to attach keyboard or init usage: {e}")


@app.on_callback_query(filters.regex(r"^clean\|"))
async def clean_up_callback(client, callback_query):
    try:
        _, chat_id_str, msg_id_str = callback_query.data.split("|")
        chat_id = int(chat_id_str)
        msg_id = int(msg_id_str)
    except Exception:
        await callback_query.answer("Invalid callback data.", show_alert=True)
        return

    usage_key = f"{chat_id}|{msg_id}|clean"
    usage = action_usage.get(usage_key, 0)
    
    if usage >= 1:
        await callback_query.answer("Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    action_usage[usage_key] = usage + 1

    stored_text = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored_text:
        await callback_query.answer("Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    
    await callback_query.answer("Cleaning up...")
    status_msg = await callback_query.message.reply_text("🔄 Processing clean transcript...")
    
    try:
        loop = asyncio.get_event_loop()
        uid = callback_query.from_user.id
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        
        cleaned_text = await loop.run_in_executor(None, ask_gemini, stored_text, instruction)
        
        if not cleaned_text:
            await status_msg.edit_text("No cleaned text returned.")
            return

        if len(cleaned_text) > 4000:
            if mode == "💬 Split messages":
                await status_msg.delete()
                for part in [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]:
                    await callback_query.message.reply_text(part)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, f"cleaned_{callback_query.id}.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(cleaned_text)
                await status_msg.delete()
                await callback_query.message.reply_document(file_name, caption="Cleaned Transcript")
                os.remove(file_name)
        else:
            await status_msg.edit_text(cleaned_text)

    except Exception as e:
        logging.exception("Error in clean_up_callback")
        await status_msg.edit_text(f"❌ Error during cleanup: {e}")


@app.on_callback_query(filters.regex(r"^summarize\|"))
async def get_key_points_callback(client, callback_query):
    try:
        _, chat_id_str, msg_id_str = callback_query.data.split("|")
        chat_id = int(chat_id_str)
        msg_id = int(msg_id_str)
    except Exception:
        await callback_query.answer("Invalid callback data.", show_alert=True)
        return

    usage_key = f"{chat_id}|{msg_id}|summarize"
    usage = action_usage.get(usage_key, 0)
    
    if usage >= 1:
        await callback_query.answer("Summarize unavailable (maybe expired or not found).", show_alert=True)
        return
    action_usage[usage_key] = usage + 1

    stored_text = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored_text:
        await callback_query.answer("Summarize unavailable (maybe expired or not found).", show_alert=True)
        return

    await callback_query.answer("Generating summary...")
    status_msg = await callback_query.message.reply_text("🔄 Processing summary...")

    try:
        loop = asyncio.get_event_loop()
        uid = callback_query.from_user.id
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        
        summary = await loop.run_in_executor(None, ask_gemini, stored_text, instruction)
        
        if not summary:
            await status_msg.edit_text("No Summary returned.")
            return

        if len(summary) > 4000:
            if mode == "💬 Split messages":
                await status_msg.delete()
                for part in [summary[i:i+4000] for i in range(0, len(summary), 4000)]:
                    await callback_query.message.reply_text(part)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, f"summary_{callback_query.id}.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(summary)
                await status_msg.delete()
                await callback_query.message.reply_document(file_name, caption="Summary")
                os.remove(file_name)
        else:
            await status_msg.edit_text(summary)
            
    except Exception as e:
        logging.exception("Error in get_key_points_callback")
        await status_msg.edit_text(f"❌ Error during summary: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
