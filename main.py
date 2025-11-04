import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction
import assemblyai as aai
import requests
import json
import threading
from flask import Flask, request

flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive(): return "Bot is alive ✅", 200
def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

GEMINI_API_KEY = "AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"
API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7770743573:AAF9mwgq3efTrJ5iaXQu5VVfnFijUxPsAsg"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"
REQUEST_TIMEOUT_GEMINI = 300

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
CODE_TO_LABEL = {code: label for label,code in LANGS}
user_lang = {}
user_mode = {}
temp_transcriptions = {} 

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def ask_gemini(text: str, instruction: str, timeout: int = REQUEST_TIMEOUT_GEMINI) -> str:
    if not GEMINI_API_KEY: 
        raise RuntimeError("GEMINI_API_KEY is not set.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": instruction}, {"text": text}]}]}
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    result = resp.json()
    if "candidates" in result and len(result["candidates"]) > 0:
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except:
            return json.dumps(result['candidates'][0])
    raise RuntimeError(json.dumps(result))

def clean_up_text(text: str, lang_code: str) -> str:
    instruction = f"Clean and normalize this transcription (lang={lang_code}). Remove ASR artifacts and filler noises. Produce clean readable text."
    return ask_gemini(text, instruction)

def summarize_text(text: str, lang_code: str) -> str:
    instruction = f"Summarize this text into (lang={lang_code}) without introductions or notes."
    return ask_gemini(text, instruction)

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

def attach_action_buttons(text: str, chat_id: int, message_id: int) -> InlineKeyboardMarkup:
    include_summarize = len(text) > 1000 if text else False
    buttons = [[InlineKeyboardButton("⭐️Clean transcript", callback_data=f"cleanup|{chat_id}|{message_id}")]]
    if include_summarize:
        buttons.append([InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    buttons, row = [], []
    for i, label in enumerate(LABELS, 1):
        row.append(label)
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
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
    if message.audio: ext = ".mp3"
    elif message.voice: ext = ".ogg"
    elif message.video: ext = ".mp4"
    elif message.document: ext = os.path.splitext(message.document.file_name or "")[1] or ""
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
        if os.path.exists(file_path): os.remove(file_path)
        return
    finally:
        if os.path.exists(file_path): os.remove(file_path)

    reply_msg_id = message.id
    if len(text) > 4000:
        if mode == "💬 Split messages":
            for part in [text[i:i+4000] for i in range(0, len(text), 4000)]:
                await client.send_chat_action(message.chat.id, ChatAction.TYPING)
                await message.reply_text(part, reply_to_message_id=reply_msg_id)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{message.id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
            await message.reply_document(file_name, caption="📄 Transcription saved", reply_to_message_id=reply_msg_id)
            os.remove(file_name)
    else:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        final_message = await message.reply_text(text, reply_to_message_id=reply_msg_id)
        temp_transcriptions[(final_message.chat.id, final_message.id)] = text
        keyboard = attach_action_buttons(text, final_message.chat.id, final_message.id)
        await final_message.edit_reply_markup(reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^cleanup\|"))
async def handle_cleanup_callback(client, call: CallbackQuery):
    await call.answer("Cleaning up...")
    _, chat_id, msg_id = call.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)
    key = (chat_id, msg_id)
    stored_text = temp_transcriptions.pop(key, None)
    uid = call.from_user.id
    mode = user_mode.get(uid, "📄 Text File")
    if not stored_text:
        await call.answer("❌ Clean up unavailable", show_alert=True)
        await client.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
        return
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    lang_code = user_lang.get(uid, "en")
    loop = asyncio.get_event_loop()
    cleaned_text = await loop.run_in_executor(None, clean_up_text, stored_text, lang_code)
    await client.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
    if len(cleaned_text) > 4000:
        if mode == "💬 Split messages":
            for part in [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]:
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                await client.send_message(chat_id, part, reply_to_message_id=msg_id)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"cleaned_{msg_id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            await client.send_document(chat_id, file_name, caption="📄 Cleaned Transcript", reply_to_message_id=msg_id)
            os.remove(file_name)
    else:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        await client.send_message(chat_id, cleaned_text, reply_to_message_id=msg_id)

@app.on_callback_query(filters.regex(r"^summarize\|"))
async def handle_summarize_callback(client, call: CallbackQuery):
    await call.answer("Generating Summary...")
    _, chat_id, msg_id = call.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)
    key = (chat_id, msg_id)
    stored_text = temp_transcriptions.pop(key, None)
    uid = call.from_user.id
    mode = user_mode.get(uid, "📄 Text File")
    if not stored_text:
        await call.answer("❌ Summarize unavailable", show_alert=True)
        await client.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
        return
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    lang_code = user_lang.get(uid, "en")
    loop = asyncio.get_event_loop()
    summary_text = await loop.run_in_executor(None, summarize_text, stored_text, lang_code)
    await client.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
    if len(summary_text) > 4000:
        if mode == "💬 Split messages":
            for part in [summary_text[i:i+4000] for i in range(0, len(summary_text), 4000)]:
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                await client.send_message(chat_id, part, reply_to_message_id=msg_id)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"summary_{msg_id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(summary_text)
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            await client.send_document(chat_id, file_name, caption="📄 Summary", reply_to_message_id=msg_id)
            os.remove(file_name)
    else:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        await client.send_message(chat_id, summary_text, reply_to_message_id=msg_id)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
