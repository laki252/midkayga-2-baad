import os
import asyncio
import threading
from flask import Flask, request
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatAction
import assemblyai as aai
from google import genai
from collections import defaultdict
import time
from threading import Lock

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
GEMINI_API_KEY = "AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"

aai.settings.api_key = ASSEMBLYAI_API_KEY
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

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

user_transcriptions = defaultdict(dict)
memory_lock = Lock()
TRANSCRIPT_LIFETIME = 86400

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

def ask_gemini(text: str, instruction: str) -> str:
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[instruction, text]
    )
    return response.text.strip()

def attach_action_buttons(chat_id: int, message_id: int, text: str):
    include_summarize = len(text) > 1000
    m = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{message_id}")],
            ([InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{message_id}")] if include_summarize else [])
        ]
    )
    return m

def delete_transcription_later(chat_id, message_id):
    time.sleep(TRANSCRIPT_LIFETIME)
    with memory_lock:
        if message_id in user_transcriptions.get(chat_id, {}):
            del user_transcriptions[chat_id][message_id]

def split_text_into_chunks(text, limit=4000):
    if not text: return []
    chunks = []; start = 0; n = len(text)
    while start < n:
        end = min(start + limit, n)
        if end < n:
            last_space = text.rfind(" ", start, end)
            if last_space > start: end = last_space
        chunk = text[start:end].strip()
        if not chunk:
            end = start + limit
            chunk = text[start:end].strip()
        chunks.append(chunk); start = end
    return chunks

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
    chat_id = message.chat.id
    lang = user_lang.get(uid, "en")
    mode = user_mode.get(uid, "📄 Text File")
    await client.send_chat_action(chat_id, ChatAction.TYPING)
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
    await client.send_chat_action(chat_id, ChatAction.TYPING)
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
    reply_msg_id = message.id
    sent_message = None

    if len(text) > 4000:
        if mode == "💬 Split messages":
            chunks = split_text_into_chunks(text, limit=4000)
            for part in chunks:
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                sent_message = await message.reply_text(part, reply_to_message_id=reply_msg_id)
                reply_msg_id = sent_message.id
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{message.id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            sent_message = await message.reply_document(file_name, caption="Open this file and copy the text inside 👍", reply_to_message_id=reply_msg_id)
            os.remove(file_name)
    else:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        sent_message = await message.reply_text(text, reply_to_message_id=reply_msg_id)

    if sent_message:
        inline_keyboard = attach_action_buttons(chat_id, sent_message.id, text)
        await sent_message.edit_reply_markup(reply_markup=inline_keyboard)
        with memory_lock:
            user_transcriptions[chat_id][sent_message.id] = text
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, delete_transcription_later, chat_id, sent_message.id)

@app.on_callback_query(filters.regex("^clean\\|\\d+"))
async def clean_up_callback(client, callback_query):
    chat_id = callback_query.message.chat.id
    msg_id = int(callback_query.data.split("|")[1])
    original_text = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not original_text:
        await callback_query.answer("Clean up unavailable (maybe expired)", show_alert=True)
        return
    
    await callback_query.answer("Cleaning up...")
    status_msg = await client.send_message(chat_id, "🔄 Processing...", reply_to_message_id=msg_id)
    
    try:
        lang = user_lang.get(chat_id, "en")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        loop = asyncio.get_event_loop()
        cleaned = await loop.run_in_executor(None, ask_gemini, original_text, instruction)
    except Exception as e:
        cleaned = f"Error during clean-up: {e}"
        await client.edit_message_text(chat_id, status_msg.id, cleaned)
        return
    finally:
        await client.delete_messages(chat_id, status_msg.id)

    user_mode_val = user_mode.get(chat_id, "📄 Text File")
    
    if len(cleaned) > 4000:
        if user_mode_val == "📄 Text File":
            file_name = os.path.join(DOWNLOADS_DIR, f"cleaned_{msg_id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(cleaned)
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            sent_message = await client.send_document(chat_id, file_name, caption="Cleaned transcript.", reply_to_message_id=msg_id)
            os.remove(file_name)
        else:
            chunks = split_text_into_chunks(cleaned, limit=4000)
            sent_message = None
            for part in chunks:
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                sent_message = await client.send_message(chat_id, part, reply_to_message_id=msg_id)
    else:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        sent_message = await client.send_message(chat_id, cleaned, reply_to_message_id=msg_id)

    if sent_message:
        inline_keyboard = attach_action_buttons(chat_id, sent_message.id, cleaned)
        await sent_message.edit_reply_markup(reply_markup=inline_keyboard)
        with memory_lock:
            user_transcriptions[chat_id][sent_message.id] = cleaned
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, delete_transcription_later, chat_id, sent_message.id)

@app.on_callback_query(filters.regex("^summarize\\|\\d+"))
async def get_key_points_callback(client, callback_query):
    chat_id = callback_query.message.chat.id
    msg_id = int(callback_query.data.split("|")[1])
    original_text = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not original_text:
        await callback_query.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
        return
    
    await callback_query.answer("Generating...")
    status_msg = await client.send_message(chat_id, "🔄 Processing...", reply_to_message_id=msg_id)
    
    try:
        lang = user_lang.get(chat_id, "en")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, ask_gemini, original_text, instruction)
        
        if not summary:
            summary = "No Summary returned."
            
        await client.edit_message_text(chat_id, status_msg.id, summary)

    except Exception as e:
        await client.edit_message_text(chat_id, status_msg.id, f"Error during summarization: {e}")


if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
