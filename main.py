import os
import asyncio
import threading
import json
import logging
import requests
from flask import Flask, request, abort
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction, ChatMemberStatus
import assemblyai as aai
from pymongo import MongoClient
import telebot
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_USER = "lakicalinuur"
DB_PASSWORD = "DjReFoWZGbwjry8K"
DB_APPNAME = "SpeechBot"
MONGO_URI = f"mongodb+srv://{DB_USER}:{DB_PASSWORD}@cluster0.n4hdlxk.mongodb.net/?retryWrites=true&w=majority&appName={DB_APPNAME}"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_APPNAME]
users_collection = db.users

API_ID = int(os.environ.get("API_ID", "29169428"))
API_HASH = os.environ.get("API_HASH", "55742b16a85aac494c7944568b5507e5")
BOT1_TOKEN = os.environ.get("BOT_TOKEN", "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw")
BOT2_TOKEN = os.environ.get("BOT2_TOKEN", "7770743573:AAGovhDxwzYyn9vZhC-RBCtqe6OoT2a6ZHA")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://midkayga-2-baad-y8r7.onrender.com")
MEDIA_TO_TEXT_BOT_LINK = "https://t.me/MediaToTextBot"

DEFAULT_ASSEMBLY_KEYS = "e27f99e6c34e44a4af5e0934b34b3e6f,a6d887c307044ee4a918b868a770e8ef"
DEFAULT_GEMINI_KEYS = "AIzaSyADfan-yL9WdrlVd3vzbCdJM7tXbA72dG,AIzaSyAKrnVxMMPIqSzovoUggXy5CQ_4Hi7I_NU"

ASSEMBLYAI_API_KEYS = os.environ.get("ASSEMBLYAI_API_KEYS", DEFAULT_ASSEMBLY_KEYS)
GEMINI_API_KEYS = os.environ.get("GEMINI_API_KEYS", DEFAULT_GEMINI_KEYS)

REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@ok_fans")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "250"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024
MAX_MESSAGE_CHUNK = 4095
DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT1_TOKEN)

bot2 = telebot.TeleBot(BOT2_TOKEN, threaded=False)

flask_app = Flask(__name__)

def parse_keys(s):
    if not s: return []
    return [p.strip() for p in s.split(",") if p.strip()]

class KeyRotator:
    def __init__(self, keys):
        self.keys = list(keys)
        self.pos = 0
        self.lock = threading.Lock()
    def get_order(self):
        with self.lock:
            if not self.keys: return []
            return [self.keys[(self.pos + i) % len(self.keys)] for i in range(len(self.keys))]
    def mark_success(self, key):
        with self.lock:
            try:
                self.pos = self.keys.index(key)
            except: pass
    def mark_failure(self, key):
        with self.lock:
            if self.keys:
                try:
                    i = self.keys.index(key)
                    self.pos = (i + 1) % len(self.keys)
                except:
                    self.pos = (self.pos + 1) % len(self.keys)

assembly_rotator = KeyRotator(parse_keys(ASSEMBLYAI_API_KEYS))
gemini_rotator = KeyRotator(parse_keys(GEMINI_API_KEYS))

if assembly_rotator.keys:
    aai.settings.api_key = assembly_rotator.keys[0]

LANGS = [
("🇬🇧 English","en"), ("🇸🇦 العربية","ar"), ("🇪🇸 Español","es"), ("🇫🇷 Français","fr"),
("🇷🇺 Русский","ru"), ("🇩🇪 Deutsch","de"), ("🇮🇳 हिन्दी","hi"), ("🇮🇷 فارسی","fa"),
("🇮🇩 Indonesia","id"), ("🇺🇦 Українська","uk"), ("🇹🇷 Türkçe","tr"), ("🇸🇴 Somali","so")
]
LABEL_TO_CODE = {label: code for label,code in LANGS}
user_lang = {}
user_mode = {}
user_transcriptions = {}
action_usage = {}
user_usage_count = {}

def set_user_preferences(uid, lang=None, mode=None):
    update = {}
    if lang: update["lang"] = lang
    if mode: update["mode"] = mode
    if update:
        users_collection.update_one({"_id": uid}, {"$set": update}, upsert=True)
        if "lang" in update: user_lang[uid] = update["lang"]
        if "mode" in update: user_mode[uid] = update["mode"]

def get_user_lang(uid, default="en"):
    if uid in user_lang: return user_lang[uid]
    doc = users_collection.find_one({"_id": uid}) or {}
    l = doc.get("lang", default)
    user_lang[uid] = l
    return l

def get_user_mode(uid, default="📄 Text File"):
    if uid in user_mode: return user_mode[uid]
    doc = users_collection.find_one({"_id": uid}) or {}
    m = doc.get("mode", default)
    user_mode[uid] = m
    return m

def ask_gemini(text, instruction):
    if not gemini_rotator.keys:
        raise RuntimeError("No GEMINI keys available")
    last_exc = None
    for key in gemini_rotator.get_order():
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{instruction}\n\nInput Text:\n{text}"
            )
            if response.text:
                gemini_rotator.mark_success(key)
                return response.text
            else:
                raise RuntimeError("Empty response from Gemini")
        except Exception as e:
            logging.warning(f"Gemini key failed: {e}")
            gemini_rotator.mark_failure(key)
            last_exc = e
            continue
    raise RuntimeError(f"All Gemini keys failed. Last error: {last_exc}")

def transcribe_file(file_path, lang_code="en"):
    if not assembly_rotator.keys: raise RuntimeError("No AssemblyAI keys")
    last_exc = None
    for key in assembly_rotator.get_order():
        try:
            aai.settings.api_key = key
            transcriber = aai.Transcriber()
            config = aai.TranscriptionConfig(language_code=lang_code)
            transcript = transcriber.transcribe(file_path, config)
            if transcript.error: raise RuntimeError(transcript.error)
            assembly_rotator.mark_success(key)
            return transcript.text
        except Exception as e:
            assembly_rotator.mark_failure(key)
            last_exc = e
            continue
    raise RuntimeError(f"All AssemblyAI keys failed: {last_exc}")

def build_action_keyboard(chat_id, message_id, text_length):
    buttons = [[InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}")]]
    if text_length > 1000:
        buttons.append([InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")])
    return InlineKeyboardMarkup(buttons)

async def ensure_joined(client, obj):
    if isinstance(obj, CallbackQuery):
        uid, reply_target = obj.from_user.id, obj.message
    else:
        uid, reply_target = obj.from_user.id, obj

    count = user_usage_count.get(uid, 0)
    if count < 3:
        user_usage_count[uid] = count + 1
        return True

    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, uid)
        if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except: pass

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")],[InlineKeyboardButton("✅ Joined", callback_data="check_join")]])
    text = f"🚫 First join {REQUIRED_CHANNEL} to use this bot"
    try:
        await reply_target.reply_text(text, reply_markup=kb)
    except: pass
    return False

@flask_app.route("/", methods=["GET", "HEAD", "POST"])
def webhook_handler():
    if request.method in ("GET", "HEAD"):
        return "Bot is alive ✅", 200

    if request.method == "POST":
        if request.headers.get("Content-Type") == "application/json":
            json_string = request.get_data().decode("utf-8")
            update = telebot.types.Update.de_json(json_string)
            bot2.process_new_updates([update])
            return "", 200
        else:
            abort(403)

def run_flask():
    try:
        bot2.remove_webhook()
        bot2.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Bot2 Webhook set to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")

    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

@bot2.message_handler(func=lambda message: True, content_types=["text", "photo", "audio", "voice", "video", "sticker", "document", "animation"])
def bot2_handle_all(message):
    reply = (
        f"[Use our new bot]({MEDIA_TO_TEXT_BOT_LINK})\n"
        f"[استخدم بوتنا الجديد]({MEDIA_TO_TEXT_BOT_LINK})\n"
        f"[👇🏻👇🏻👇🏻👇🏻👇🏻👇🏻👇🏻]({MEDIA_TO_TEXT_BOT_LINK})"
    )
    bot2.reply_to(message, reply, parse_mode="Markdown")

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if not await ensure_joined(client, message): return
    buttons = []
    for i in range(0, len(LANGS), 3):
        row = [InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start") for label, code in LANGS[i:i+3]]
        buttons.append(row)
    await message.reply_text("**Choose your file language:**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    await message.reply_text(f"Send audio/video/voice. Max: {MAX_UPLOAD_MB}MB.")

@app.on_message(filters.command("mode") & filters.private)
async def mode_command(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Split messages", callback_data="mode|Split messages")],
        [InlineKeyboardButton("📄 Text File", callback_data="mode|Text File")]
    ])
    await message.reply_text("Choose output mode:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^lang\|"))
async def lang_callback(client, cb):
    _, code, label, origin = cb.data.split("|")
    set_user_preferences(cb.from_user.id, lang=code)
    if origin == "start":
        await cb.message.edit_text(f"👋 **Salaam!** Send me a file to transcribe ({label}).")
    else:
        await cb.answer(f"Language: {label}")
        await cb.message.delete()

@app.on_callback_query(filters.regex(r"^mode\|"))
async def mode_callback(client, cb):
    mode = cb.data.split("|")[1]
    set_user_preferences(cb.from_user.id, mode=mode)
    await cb.answer(f"Mode: {mode}")
    await cb.message.delete()
    await cb.message.reply_text(f"Mode set to: **{mode}**")

@app.on_callback_query(filters.regex(r"^check_join"))
async def check_join_cb(client, cb):
    if await ensure_joined(client, cb):
        await cb.message.delete()
        await cb.message.reply_text("Thanks! You can now use the bot.")

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message):
    if not await ensure_joined(client, message): return
    uid = message.from_user.id

    size = 0
    if message.document: size = message.document.file_size
    elif message.audio: size = message.audio.file_size
    elif message.video: size = message.video.file_size
    elif message.voice: size = message.voice.file_size

    if size > MAX_UPLOAD_SIZE:
        await message.reply_text(f"File too big. Max {MAX_UPLOAD_MB}MB.")
        return

    if not get_user_lang(uid, None):
        await start_command(client, message)
        return

    lang = get_user_lang(uid)
    mode = get_user_mode(uid)

    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        file_path = await message.download(file_name=os.path.join(DOWNLOADS_DIR, ""))
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_file, file_path, lang)
    except Exception as e:
        await message.reply_text(f"Error: {e}")
        return
    finally:
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

    if not text:
        await message.reply_text("Could not transcribe audio.")
        return

    reply_msg_id = message.id
    sent_msg = None

    if len(text) > MAX_MESSAGE_CHUNK:
        if mode == "💬 Split messages":
            for i in range(0, len(text), MAX_MESSAGE_CHUNK):
                sent_msg = await message.reply_text(text[i:i+MAX_MESSAGE_CHUNK], reply_to_message_id=reply_msg_id)
        else:
            fn = "Transcript.txt"
            with open(fn, "w", encoding="utf-8") as f: f.write(text)
            sent_msg = await client.send_document(message.chat.id, fn, caption="Transcript", reply_to_message_id=reply_msg_id)
            os.remove(fn)
    else:
        sent_msg = await message.reply_text(text, reply_to_message_id=reply_msg_id)

    if sent_msg:
        kb = build_action_keyboard(sent_msg.chat.id, sent_msg.id, len(text))
        user_transcriptions.setdefault(sent_msg.chat.id, {})[sent_msg.id] = {"text": text, "origin": reply_msg_id}
        await sent_msg.edit_reply_markup(kb)

@app.on_callback_query(filters.regex(r"^(clean|summarize)\|"))
async def ai_action_callback(client, cb):
    action, chat_id, msg_id = cb.data.split("|")
    chat_id, msg_id = int(chat_id), int(msg_id)

    key = f"{chat_id}|{msg_id}|{action}"
    if action_usage.get(key, 0) >= 1:
        await cb.answer("Already used.", show_alert=True)
        return

    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        await cb.answer("Data expired.", show_alert=True)
        return

    action_usage[key] = 1
    await cb.answer("Processing...", show_alert=False)
    await client.send_chat_action(chat_id, ChatAction.TYPING)

    lang = get_user_lang(cb.from_user.id)
    orig_id = stored["origin"]
    text = stored["text"]

    if action == "clean":
        prompt = f"Clean and normalize this transcription (lang={lang}). Remove artifacts, filler words, timestamps. Output only clean text."
        fname = "Cleaned.txt"
    else:
        prompt = f"Summarize this text in (lang={lang}) bullet points."
        fname = "Summary.txt"

    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, ask_gemini, text, prompt)

        if len(res) > MAX_MESSAGE_CHUNK:
             with open(fname, "w", encoding="utf-8") as f: f.write(res)
             await client.send_document(chat_id, fname, caption=f"{action.title()} Result", reply_to_message_id=orig_id)
             os.remove(fname)
        else:
            await client.send_message(chat_id, res, reply_to_message_id=orig_id)

    except Exception as e:
        await client.send_message(chat_id, f"AI Error: {e}", reply_to_message_id=orig_id)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    print("🤖 Bots Started...")
    app.run()
