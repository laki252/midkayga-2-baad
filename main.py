import os
import re
import asyncio
import threading
import logging
import aiohttp
import aiofiles
import requests
import json
from flask import Flask, request, abort
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction, ChatMemberStatus
import assemblyai as aai
from pymongo import MongoClient
import yt_dlp
import telebot

COOKIES_TXT_PATH = "cookies.txt"
DB_USER = "lakicalinuur"
DB_PASSWORD = "DjReFoWZGbwjry8K"
DB_APPNAME = "SpeechBot"
MONGO_URI = f"mongodb+srv://{DB_USER}:{DB_PASSWORD}@cluster0.n4hdlxk.mongodb.net/?retryWrites=true&w=majority&appName={DB_APPNAME}"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_APPNAME]
users_collection = db.users

flask_app = Flask(__name__)

API_ID = int(os.environ.get("API_ID", "29169428"))
API_HASH = os.environ.get("API_HASH", "55742b16a85aac494c7944568b5507e5")
TRANSCRIBER_TOKEN = os.environ.get("BOT_TOKEN", "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw")
DOWNLOADER_TOKEN = os.environ.get("BOT1_TOKEN", "8378888955:AAH51OZ3ZIjGtEZTkZcPe_GPUwVqGRFJF6A")
TELEBOT_TOKEN = os.environ.get("BOT2_TOKEN", "8581764529:AAGShqZAxGe2pRJOxEqB6HDLxOMOSGOgrxs")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "https://midkayga-2-baad-1ggd.onrender.com")
PORT = int(os.environ.get("PORT", 8080))
REQUEST_TIMEOUT_GEMINI = int(os.environ.get("REQUEST_TIMEOUT_GEMINI", "300"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "250"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024
MAX_MESSAGE_CHUNK = 4095

DEFAULT_ASSEMBLY_KEYS = "e27f99e6c34e44a4af5e0934b34b3e6f,a6d887c307044ee4a918b868a770e8ef,0272c2f92b1e4b1a96fcec55975c5c2e,b77044ed989546c9ab3a064df4a46d8c,2b7533db7ec849668716b00cb64a9235,defa21f626764d71a1373437f6300d80,26293b7d8dbf43d883ce8a43d3c06f63"
DEFAULT_GEMINI_KEYS = "AIzaSyADfan-yL9WdrlVd3vzbCdJM7tXbA72dG,AIzaSyAKrnVxMMPIqSzovoUggXy5CQ_4Hi7I_NU,AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"
ASSEMBLYAI_API_KEYS = os.environ.get("ASSEMBLYAI_API_KEYS", DEFAULT_ASSEMBLY_KEYS)
GEMINI_API_KEYS = os.environ.get("GEMINI_API_KEYS", DEFAULT_GEMINI_KEYS)

def parse_keys(s):
    if not s:
        return []
    parts = [p.strip() for p in s.split(",")]
    return [p for p in parts if p]

class KeyRotator:
    def __init__(self, keys):
        self.keys = list(keys)
        self.pos = 0
        self.lock = threading.Lock()
    def get_order(self):
        with self.lock:
            n = len(self.keys)
            if n == 0:
                return []
            return [self.keys[(self.pos + i) % n] for i in range(n)]
    def mark_success(self, key):
        with self.lock:
            try:
                i = self.keys.index(key)
                self.pos = i
            except Exception:
                pass
    def mark_failure(self, key):
        with self.lock:
            n = len(self.keys)
            if n == 0:
                return
            try:
                i = self.keys.index(key)
                self.pos = (i + 1) % n
            except Exception:
                self.pos = (self.pos + 1) % n

assembly_keys_list = parse_keys(ASSEMBLYAI_API_KEYS)
gemini_keys_list = parse_keys(GEMINI_API_KEYS)
assembly_rotator = KeyRotator(assembly_keys_list)
gemini_rotator = KeyRotator(gemini_keys_list)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if assembly_rotator.keys:
    aai.settings.api_key = assembly_rotator.keys[0]

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@norshub")

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
user_usage_count = {}

transcriber_client = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=TRANSCRIBER_TOKEN)
downloader_client = Client("video_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=DOWNLOADER_TOKEN)
telebot_bot = telebot.TeleBot(TELEBOT_TOKEN)

active_downloads = 0
queue = None
lock = None

YDL_OPTS_PIN = {
    "format": "bestvideo+bestaudio/best",
    "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
    "noplaylist": True,
    "quiet": True,
    "cookiefile": COOKIES_TXT_PATH
}

YDL_OPTS_YOUTUBE = {
    "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
    "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
    "noplaylist": True,
    "quiet": True,
    "cookiefile": COOKIES_TXT_PATH
}

YDL_OPTS_DEFAULT = {
    "format": "best",
    "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
    "noplaylist": True,
    "quiet": True,
    "cookiefile": COOKIES_TXT_PATH
}

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be", "facebook.com", "fb.watch", "pin.it",
    "x.com", "tiktok.com", "snapchat.com", "instagram.com"
]

def set_user_preferences(uid, lang=None, mode=None):
    update = {}
    if lang is not None:
        update["lang"] = lang
    if mode is not None:
        update["mode"] = mode
    if update:
        users_collection.update_one({"_id": uid}, {"$set": update}, upsert=True)
        if "lang" in update:
            user_lang[uid] = update["lang"]
        if "mode" in update:
            user_mode[uid] = update["mode"]

def get_user_preferences(uid):
    doc = users_collection.find_one({"_id": uid})
    return doc or {}

def get_user_lang(uid, default="en"):
    if uid in user_lang:
        return user_lang[uid]
    doc = get_user_preferences(uid)
    lang = doc.get("lang")
    if lang:
        user_lang[uid] = lang
        return lang
    return default

def get_user_mode(uid, default="📄 Text File"):
    if uid in user_mode:
        return user_mode[uid]
    doc = get_user_preferences(uid)
    mode = doc.get("mode")
    if mode:
        user_mode[uid] = mode
        return mode
    return default

def ask_gemini(text, instruction, timeout=REQUEST_TIMEOUT_GEMINI):
    if not gemini_rotator.keys:
        raise RuntimeError("No GEMINI keys available")
    last_exc = None
    for key in gemini_rotator.get_order():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": instruction}, {"text": text}]}]}
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()
            if "candidates" in result and isinstance(result["candidates"], list) and len(result["candidates"]) > 0:
                try:
                    gemini_rotator.mark_success(key)
                    return result['candidates'][0]['content']['parts'][0]['text']
                except Exception:
                    gemini_rotator.mark_success(key)
                    return json.dumps(result['candidates'][0])
            gemini_rotator.mark_success(key)
            raise RuntimeError(f"Gemini response lacks candidates: {json.dumps(result)}")
        except Exception as e:
            logging.warning("Gemini key failed, rotating to next key: %s", str(e))
            gemini_rotator.mark_failure(key)
            last_exc = e
            continue
    raise RuntimeError(f"All Gemini keys failed. Last error: {last_exc}")

def build_action_keyboard(chat_id, message_id, text_length):
    buttons = []
    buttons.append([InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}")])
    if text_length > 1000:
        buttons.append([InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")])
    return InlineKeyboardMarkup(buttons)

async def download_media(message: Message) -> str:
    file_path = await message.download(file_name=os.path.join(DOWNLOADS_DIR, ""))
    return file_path

def transcribe_file(file_path: str, lang_code: str = "en") -> str:
    if not assembly_rotator.keys:
        raise RuntimeError("No AssemblyAI keys available")
    last_exc = None
    for key in assembly_rotator.get_order():
        try:
            aai.settings.api_key = key
            transcriber = aai.Transcriber()
            config = aai.TranscriptionConfig(language_code=lang_code)
            transcript = transcriber.transcribe(file_path, config)
            if transcript.error:
                raise RuntimeError(transcript.error)
            assembly_rotator.mark_success(key)
            return transcript.text
        except Exception as e:
            logging.warning("AssemblyAI key failed, rotating to next key: %s", str(e))
            assembly_rotator.mark_failure(key)
            last_exc = e
            continue
    raise RuntimeError(f"All AssemblyAI keys failed. Last error: {last_exc}")

WELCOME_MESSAGE = """👋 **Salaam!**
• Send me
• **voice message**
• **audio file**
• **video**
• to transcribe for free
"""

HELP_MESSAGE = f"""Commands supported:
/start - Show welcome message
/lang  - Change language
/mode  - Change result delivery mode
/help  - This help message

Send a voice/audio/video (up to {MAX_UPLOAD_MB}MB) and I will transcribe it Powered by @norshub
"""

async def is_user_in_channel(client, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.RESTRICTED)
    except Exception:
        return False

async def ensure_joined(client, obj) -> bool:
    if isinstance(obj, CallbackQuery):
        uid = obj.from_user.id
        reply_target = obj.message
    else:
        uid = obj.from_user.id
        reply_target = obj
    count = user_usage_count.get(uid, 0)
    if count < 3:
        user_usage_count[uid] = count + 1
        return True
    try:
        if await is_user_in_channel(client, uid):
            return True
    except Exception:
        pass
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]])
    text = f"🚫 First join the channel {REQUIRED_CHANNEL} to use this bot"
    try:
        if isinstance(obj, CallbackQuery):
            try:
                await obj.answer("🚫 First join the channel", show_alert=True)
            except Exception:
                pass
        await reply_target.reply_text(text, reply_markup=kb)
    except Exception:
        try:
            await client.send_message(uid, text, reply_markup=kb)
        except Exception:
            pass
    return False

@transcriber_client.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    if not await ensure_joined(client, message):
        return
    buttons, row = [], []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = InlineKeyboardMarkup(buttons)
    await message.reply_text("**Choose your file language for transcription using the below buttons:**", reply_markup=keyboard)

@transcriber_client.on_message(filters.command("help") & filters.private)
async def help_command(client, message: Message):
    if not await ensure_joined(client, message):
        return
    await message.reply_text(HELP_MESSAGE)

@transcriber_client.on_message(filters.command("lang") & filters.private)
async def lang_command(client, message: Message):
    if not await ensure_joined(client, message):
        return
    buttons, row = [], []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|lang"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = InlineKeyboardMarkup(buttons)
    await message.reply_text("**Choose your file language for transcription using the below buttons:**", reply_markup=keyboard)

@transcriber_client.on_callback_query(filters.regex(r"^lang\|"))
async def language_callback_query(client, callback_query: CallbackQuery):
    if not await ensure_joined(client, callback_query):
        return
    try:
        parts = callback_query.data.split("|")
        _, code, label = parts[:3]
        origin = parts[3] if len(parts) > 3 else "unknown"
    except Exception:
        await callback_query.answer("Invalid language selection data.", show_alert=True)
        return
    uid = callback_query.from_user.id
    set_user_preferences(uid, lang=code)
    if origin == "start":
        await callback_query.message.edit_text(WELCOME_MESSAGE, reply_markup=None)
    elif origin == "lang":
        await callback_query.message.delete()
    await callback_query.answer(f"Language set to: {label}", show_alert=False)

@transcriber_client.on_message(filters.command("mode") & filters.private)
async def choose_mode(client, message: Message):
    if not await ensure_joined(client, message):
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Split messages", callback_data="mode|Split messages")],
        [InlineKeyboardButton("📄 Text File", callback_data="mode|Text File")]
    ])
    await message.reply_text("Choose **output mode**:", reply_markup=keyboard)

@transcriber_client.on_callback_query(filters.regex(r"^mode\|"))
async def mode_callback_query(client, callback_query: CallbackQuery):
    if not await ensure_joined(client, callback_query):
        return
    try:
        _, mode_name = callback_query.data.split("|")
    except Exception:
        await callback_query.answer("Invalid mode selection data.", show_alert=True)
        return
    uid = callback_query.from_user.id
    set_user_preferences(uid, mode=mode_name)
    await callback_query.answer(f"Mode set to: {mode_name}", show_alert=False)
    try:
        await callback_query.message.delete()
    except Exception:
        pass

@transcriber_client.on_message(filters.private & filters.text)
async def handle_text(client, message: Message):
    if not await ensure_joined(client, message):
        return
    uid = message.from_user.id
    text = message.text
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        set_user_preferences(uid, mode=text)
        await message.reply_text(f"Output mode set to: **{text}**")
        return

@transcriber_client.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message: Message):
    if not await ensure_joined(client, message):
        return
    uid = message.from_user.id
    if not get_user_lang(uid, None):
        buttons, row = [], []
        for i, (label, code) in enumerate(LANGS, 1):
            row.append(InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start"))
            if i % 3 == 0:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        keyboard = InlineKeyboardMarkup(buttons)
        await message.reply_text("**Please choose your file language first:**", reply_markup=keyboard)
        return
    size = None
    try:
        if getattr(message, "document", None) and getattr(message.document, "file_size", None):
            size = message.document.file_size
        elif getattr(message, "audio", None) and getattr(message.audio, "file_size", None):
            size = message.audio.file_size
        elif getattr(message, "video", None) and getattr(message.video, "file_size", None):
            size = message.video.file_size
        elif getattr(message, "voice", None) and getattr(message.voice, "file_size", None):
            size = message.voice.file_size
    except Exception:
        size = None
    if size is not None and size > MAX_UPLOAD_SIZE:
        await message.reply_text(f"Just Send me a file less than {MAX_UPLOAD_MB}MB 😎")
        return
    lang = get_user_lang(uid)
    mode = get_user_mode(uid, "📄 Text File")
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    file_path = None
    try:
        file_path = await download_media(message)
    except Exception as e:
        await message.reply_text(f"⚠️ Download error: {e}")
        return
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_file, file_path, lang)
    except Exception as e:
        await message.reply_text(f"❌ Transcription error: {e}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    if not text or text.startswith("Error:"):
        await message.reply_text(text or "⚠️ Warning Make sure the voice is clear or speaking in the language you Choosed.", reply_to_message_id=message.id)
        return
    reply_msg_id = message.id
    sent_message = None
    if len(text) > MAX_MESSAGE_CHUNK:
        if mode == "💬 Split messages":
            for part in [text[i:i+MAX_MESSAGE_CHUNK] for i in range(0, len(text), MAX_MESSAGE_CHUNK)]:
                await client.send_chat_action(message.chat.id, ChatAction.TYPING)
                sent_message = await message.reply_text(part, reply_to_message_id=reply_msg_id)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, "Transcript.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
            sent_message = await client.send_document(message.chat.id, file_name, caption="Open this file and copy the text inside 👍", reply_to_message_id=reply_msg_id)
            os.remove(file_name)
    else:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        sent_message = await message.reply_text(text, reply_to_message_id=reply_msg_id)
    if sent_message:
        try:
            keyboard = build_action_keyboard(sent_message.chat.id, sent_message.id, len(text))
            user_transcriptions.setdefault(sent_message.chat.id, {})[sent_message.id] = {"text": text, "origin": reply_msg_id}
            action_usage[f"{sent_message.chat.id}|{sent_message.id}|clean"] = 0
            if len(text) > 1000:
                action_usage[f"{sent_message.chat.id}|{sent_message.id}|summarize"] = 0
            await sent_message.edit_reply_markup(keyboard)
        except Exception as e:
            logging.error(f"Failed to attach keyboard or init usage: {e}")

@transcriber_client.on_callback_query(filters.regex(r"^clean\|"))
async def clean_up_callback(client, callback_query: CallbackQuery):
    if not await ensure_joined(client, callback_query):
        return
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
    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        await callback_query.answer("Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    stored_text = stored.get("text")
    orig_msg_id = stored.get("origin")
    await callback_query.answer("Cleaning up...", show_alert=False)
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    try:
        loop = asyncio.get_event_loop()
        uid = callback_query.from_user.id
        lang = get_user_lang(uid, "en")
        mode = get_user_mode(uid, "📄 Text File")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        cleaned_text = await loop.run_in_executor(None, ask_gemini, stored_text, instruction)
        if not cleaned_text:
            await client.send_message(chat_id, "No cleaned text returned.", reply_to_message_id=orig_msg_id)
            return
        if len(cleaned_text) > MAX_MESSAGE_CHUNK:
            if mode == "💬 Split messages":
                for part in [cleaned_text[i:i+MAX_MESSAGE_CHUNK] for i in range(0, len(cleaned_text), MAX_MESSAGE_CHUNK)]:
                    await client.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, "Cleaned.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(cleaned_text)
                await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
                await client.send_document(chat_id, file_name, caption="Cleaned Transcript", reply_to_message_id=orig_msg_id)
                os.remove(file_name)
        else:
            await client.send_message(chat_id, cleaned_text, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in clean_up_callback")
        await client.send_message(chat_id, f"❌ Error during cleanup: {e}", reply_to_message_id=orig_msg_id)

@transcriber_client.on_callback_query(filters.regex(r"^summarize\|"))
async def get_key_points_callback(client, callback_query: CallbackQuery):
    if not await ensure_joined(client, callback_query):
        return
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
    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        await callback_query.answer("Summarize unavailable (maybe expired or not found).", show_alert=True)
        return
    stored_text = stored.get("text")
    orig_msg_id = stored.get("origin")
    await callback_query.answer("Generating summary...", show_alert=False)
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    try:
        loop = asyncio.get_event_loop()
        uid = callback_query.from_user.id
        lang = get_user_lang(uid, "en")
        mode = get_user_mode(uid, "📄 Text File")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        summary = await loop.run_in_executor(None, ask_gemini, stored_text, instruction)
        if not summary:
            await client.send_message(chat_id, "No Summary returned.", reply_to_message_id=orig_msg_id)
            return
        if len(summary) > MAX_MESSAGE_CHUNK:
            if mode == "💬 Split messages":
                for part in [summary[i:i+MAX_MESSAGE_CHUNK] for i in range(0, len(summary), MAX_MESSAGE_CHUNK)]:
                    await client.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, "Summary.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(summary)
                await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
                await client.send_document(chat_id, file_name, caption="Summary", reply_to_message_id=orig_msg_id)
                os.remove(file_name)
        else:
            await client.send_message(chat_id, summary, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in get_key_points_callback")
        await client.send_message(chat_id, f"❌ Error during summary: {e}", reply_to_message_id=orig_msg_id)

async def download_thumbnail(url, target_path):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    f = await aiofiles.open(target_path, mode='wb')
                    await f.write(await resp.read())
                    await f.close()
                    if os.path.exists(target_path):
                        return target_path
    except:
        pass
    return None

def extract_metadata_from_info(info):
    width = info.get("width")
    height = info.get("height")
    duration = info.get("duration")
    if not width or not height:
        formats = info.get("formats") or []
        best = None
        for f in formats:
            if f.get("width") and f.get("height"):
                best = f
                break
        if best:
            if not width:
                width = best.get("width")
            if not height:
                height = best.get("height")
            if not duration:
                dms = best.get("duration_ms")
                duration = info.get("duration") or (dms / 1000 if dms else None)
    return width, height, duration

async def download_video(url: str):
    loop = asyncio.get_running_loop()
    try:
        lowered = url.lower()
        is_pin = "pin.it" in lowered
        is_youtube = "youtube.com" in lowered or "youtu.be" in lowered
        if is_pin:
            ydl_opts = YDL_OPTS_PIN.copy()
        elif is_youtube:
            ydl_opts = YDL_OPTS_YOUTUBE.copy()
        else:
            ydl_opts = YDL_OPTS_DEFAULT.copy()
        def extract_info_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        info = await loop.run_in_executor(None, extract_info_sync)
        width, height, duration = extract_metadata_from_info(info)
        if duration and duration > 2400:
            return None
        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dl = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dl)
                return info_dl, filename
        info, filename = await loop.run_in_executor(None, download_sync)
        title = info.get("title") or ""
        desc = info.get("description") or ""
        is_youtube_flag = "youtube.com" in url.lower() or "youtu.be" in url.lower()
        if is_youtube_flag:
            caption = title or "@SooDajiye_Bot"
            if len(caption) > 1024:
                caption = caption[:1024]
        else:
            caption = desc.strip() or "@SooDajiye_Bot"
            if len(caption) > 1024:
                caption = caption[:1021] + "..."
        thumb = None
        thumb_url = info.get("thumbnail")
        if thumb_url:
            thumb_path = os.path.splitext(filename)[0] + ".jpg"
            thumb = await download_thumbnail(thumb_url, thumb_path)
        return caption, filename, width, height, duration, thumb
    except Exception as e:
        logging.exception(e)
        return "ERROR"

async def download_audio_only(url: str):
    loop = asyncio.get_running_loop()
    lowered_url = url.lower()
    is_supported = any(domain in lowered_url for domain in ["youtube.com", "youtu.be", "facebook.com", "fb.watch"])
    if not is_supported:
        return None
    try:
        ydl_opts_info = {
            "skip_download": True,
            "quiet": True,
            "cookiefile": COOKIES_TXT_PATH
        }
        def extract_info_sync():
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                return ydl.extract_info(url, download=False)
        info = await loop.run_in_executor(None, extract_info_sync)
        duration = info.get("duration")
        if not duration or duration <= 120:
            return None
        ydl_opts_audio = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": os.path.join("downloads", "%(title)s.m4a"),
            "noplaylist": True,
            "quiet": True,
            "cookiefile": COOKIES_TXT_PATH
        }
        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                info_dl = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dl)
                return info_dl, filename
        info_dl, filename = await loop.run_in_executor(None, download_sync)
        title = info_dl.get("title") or "Audio"
        caption = f"🎧 Muuqaalka Codkiisa oo kaliya\n\n{title}"
        return caption, filename
    except Exception as e:
        logging.exception(e)
        return None

async def process_download(client, message, url):
    global active_downloads
    async with lock:
        active_downloads += 1
    try:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        result = await download_video(url)
        if result is None:
            await message.reply("Masoo dajin kari video ka dheer 40 minute 👍")
        elif result == "ERROR":
            await message.reply("Qalad ayaa dhacay, fadlan isku day mar kale 😓")
        else:
            caption, file_path, width, height, duration, thumb = result
            await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
            kwargs = {"video": file_path, "caption": caption, "supports_streaming": True}
            if width:
                kwargs["width"] = int(width)
            if height:
                kwargs["height"] = int(height)
            if duration:
                kwargs["duration"] = int(float(duration))
            if thumb and os.path.exists(thumb):
                kwargs["thumb"] = thumb
            await client.send_video(message.chat.id, **kwargs)
            audio_result = await download_audio_only(url)
            if audio_result:
                audio_caption, audio_path = audio_result
                try:
                    await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_AUDIO)
                except:
                    try:
                        await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
                    except:
                        pass
                try:
                    await client.send_audio(
                        message.chat.id,
                        audio=audio_path,
                        caption=audio_caption,
                        title=os.path.splitext(os.path.basename(audio_path))[0],
                        performer="Powered by SooDajiye Bot.m4a"
                    )
                except Exception:
                    logging.exception("Sending audio failed")
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except:
                        pass
            for f in [file_path, thumb]:
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass
    finally:
        async with lock:
            active_downloads -= 1
        await start_next_download()

async def start_next_download():
    async with lock:
        while not queue.empty() and active_downloads < 5:
            client, message, url = await queue.get()
            asyncio.create_task(process_download(client, message, url))

@downloader_client.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply(
        "👋 Salaam!\n"
        "Iisoodir link Video kasocdo baraha hoos kuxusan si aan kuugu soo dajiyo.\n\n"
        "Supported sites:\n"
        "• YouTube\n"
        "• Facebook\n"
        "• Pinterest\n"
        "• X (Twitter)\n"
        "• TikTok\n"
        "• Instagram"
    )

@downloader_client.on_message(filters.private & filters.text)
async def handle_link(client, message: Message):
    url = message.text.strip()
    if not any(domain in url.lower() for domain in SUPPORTED_DOMAINS):
        await message.reply("kaliya Soodir link video saxa 👍")
        return
    async with lock:
        if active_downloads < 5:
            asyncio.create_task(process_download(client, message, url))
        else:
            await queue.put((client, message, url))

@telebot_bot.message_handler(func=lambda m: m.chat.type in ["group", "supergroup"] and m.content_type == 'text')
def anti_spam_filter(message):
    try:
        bot_member = telebot_bot.get_chat_member(message.chat.id, telebot_bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            return
        user_member = telebot_bot.get_chat_member(message.chat.id, message.from_user.id)
        if user_member.status in ['administrator', 'creator']:
            return
        text = message.text or ""
        if (
            len(text) > 1000
            or re.search(r"https?://", text)
            or "t.me/" in text
            or re.search(r"@\w+", text)
        ):
            telebot_bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        logging.exception("Anti-spam check failed")

def set_bot2_info():
    cmds = [
        telebot.types.BotCommand("start", "Start the bot"),
    ]
    try:
        telebot_bot.set_my_commands(cmds)
    except Exception:
        logging.exception("Failed to set bot info")

@telebot_bot.message_handler(commands=['start'])
def handle_start(message):
    telebot_bot.send_message(
        message.chat.id,
        "👋 Welcome! Add me to your group and make me an admin to remove URls and @tags."
    )

@telebot_bot.message_handler(commands=['help'])
def handle_help(message):
    telebot_bot.send_message(
        message.chat.id,
        "Commands:\n"
        "/start - Start bot\n"
        "/help - This help message\n\n"
        "This bot only removes spam from groups when it is an admin.",
        parse_mode="Markdown"
    )

WEBHOOK_PATH = "/bot2"
WEBHOOK_URL = WEBHOOK_BASE.rstrip("/") + WEBHOOK_PATH

@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "ok", 200

@flask_app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.data.decode('utf-8'))
        telebot_bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

@flask_app.route('/set_webhook', methods=['GET'])
def set_wh():
    try:
        telebot_bot.set_webhook(url=WEBHOOK_URL)
        return f"ok {WEBHOOK_URL}", 200
    except Exception as e:
        logging.exception(e)
        return "error", 500

@flask_app.route('/delete_webhook', methods=['GET'])
def del_wh():
    try:
        telebot_bot.delete_webhook()
        return "deleted", 200
    except Exception as e:
        logging.exception(e)
        return "error", 500

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

async def main_async():
    global queue, lock
    queue = asyncio.Queue()
    lock = asyncio.Lock()
    set_bot2_info()
    try:
        telebot_bot.set_webhook(url=WEBHOOK_URL)
    except Exception:
        logging.exception("Failed to set webhook on startup")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    await transcriber_client.start()
    await downloader_client.start()
    await asyncio.gather(transcriber_client.idle(), downloader_client.idle())

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    if not os.path.exists(COOKIES_TXT_PATH):
        open(COOKIES_TXT_PATH, "a").close()
    asyncio.run(main_async())
