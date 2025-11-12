import os
import threading
import json
import requests
import io
import logging
from flask import Flask, request
import telebot
from telebot import types
import assemblyai as aai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://midkayga-2-baad-1ggd.onrender.com")
PORT = int(os.environ.get("PORT", "8443"))
REQUEST_TIMEOUT_GEMINI = int(os.environ.get("REQUEST_TIMEOUT_GEMINI", "300"))

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "250"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024

DEFAULT_ASSEMBLY_KEYS = os.environ.get("DEFAULT_ASSEMBLY_KEYS", "e27f99e6c34e44a4af5e0934b34b3e6f")
DEFAULT_GEMINI_KEYS = os.environ.get("DEFAULT_GEMINI_KEYS", "")

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

if assembly_rotator.keys:
    aai.settings.api_key = assembly_rotator.keys[0]

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@laaaaaaaaalaaaaaa")
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

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')
flask_app = Flask(__name__)

WELCOME_MESSAGE = """👋 *Salaam!*
• Send me
• *voice message*
• *audio file*
• *video*
• to transcribe for free
"""

HELP_MESSAGE = f"""Commands supported:
/start - Show welcome message
/lang  - Change language
/mode  - Change result delivery mode
/help  - This help message

Send a voice/audio/video (up to {MAX_UPLOAD_MB}MB) and I will transcribe it Need help? Contact: @lakigithub
"""

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
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}"))
    if text_length > 1000:
        keyboard.add(types.InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}"))
    return keyboard

def download_media_file(message):
    file_info = None
    file_id = None
    if message.voice:
        file_id = message.voice.file_id
    elif message.audio:
        file_id = message.audio.file_id
    elif message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id
    if not file_id:
        return None
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    filename = os.path.join(DOWNLOADS_DIR, os.path.basename(file_info.file_path))
    with open(filename, 'wb') as f:
        f.write(downloaded)
    return filename

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

def is_user_in_channel(user_id: int) -> bool:
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        status = getattr(member, 'status', None)
        return status in ("member", "administrator", "creator", "restricted", "owner")
    except Exception:
        return False

def ensure_joined_and_count(message_or_user_id):
    uid = message_or_user_id
    if hasattr(message_or_user_id, 'from_user'):
        uid = message_or_user_id.from_user.id
    count = user_usage_count.get(uid, 0)
    if count < 3:
        user_usage_count[uid] = count + 1
        return True
    if is_user_in_channel(uid):
        return True
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}"))
    try:
        if hasattr(message_or_user_id, 'message_id'):
            bot.send_message(uid, "🚫 First join the channel " + REQUIRED_CHANNEL, reply_markup=kb)
        else:
            bot.send_message(uid, "🚫 First join the channel " + REQUIRED_CHANNEL, reply_markup=kb)
    except Exception:
        pass
    return False

@bot.message_handler(commands=['start'])
def start_handler(message):
    if not ensure_joined_and_count(message):
        return
    keyboard = types.InlineKeyboardMarkup()
    row = []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(types.InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start"))
        if i % 3 == 0:
            keyboard.row(*row)
            row = []
    if row:
        keyboard.row(*row)
    bot.send_message(message.chat.id, "*Choose your file language for transcription using the below buttons:*", reply_markup=keyboard)

@bot.message_handler(commands=['help'])
def help_handler(message):
    if not ensure_joined_and_count(message):
        return
    bot.send_message(message.chat.id, HELP_MESSAGE)

@bot.message_handler(commands=['lang'])
def lang_handler(message):
    if not ensure_joined_and_count(message):
        return
    keyboard = types.InlineKeyboardMarkup()
    row = []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(types.InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|lang"))
        if i % 3 == 0:
            keyboard.row(*row)
            row = []
    if row:
        keyboard.row(*row)
    bot.send_message(message.chat.id, "*Choose your file language for transcription using the below buttons:*", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("lang|"))
def language_callback(call):
    if not ensure_joined_and_count(call.from_user.id):
        return
    try:
        parts = call.data.split("|")
        _, code, label = parts[:3]
        origin = parts[3] if len(parts) > 3 else "unknown"
    except Exception:
        bot.answer_callback_query(call.id, "Invalid language selection data.")
        return
    uid = call.from_user.id
    user_lang[uid] = code
    if origin == "start":
        bot.edit_message_text(WELCOME_MESSAGE, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    elif origin == "lang":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
    bot.answer_callback_query(call.id, f"Language set to: {label}")

@bot.message_handler(commands=['mode'])
def choose_mode(message):
    if not ensure_joined_and_count(message):
        return
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("💬 Split messages", callback_data="mode|Split messages"))
    keyboard.add(types.InlineKeyboardButton("📄 Text File", callback_data="mode|Text File"))
    bot.send_message(message.chat.id, "Choose *output mode*:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("mode|"))
def mode_callback(call):
    if not ensure_joined_and_count(call.from_user.id):
        return
    try:
        _, mode_name = call.data.split("|", 1)
    except Exception:
        bot.answer_callback_query(call.id, "Invalid mode selection data.")
        return
    uid = call.from_user.id
    user_mode[uid] = mode_name
    bot.answer_callback_query(call.id, f"Mode set to: {mode_name}")
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

@bot.message_handler(func=lambda m: m.content_type == 'text' and m.chat.type == 'private')
def handle_text(message):
    if not ensure_joined_and_count(message):
        return
    uid = message.from_user.id
    text = message.text
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        bot.send_message(message.chat.id, f"Output mode set to: *{text}*")

def process_transcription_and_send(chat_id, orig_msg_id, file_path, uid):
    try:
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        text = transcribe_file(file_path, lang)
    except Exception as e:
        try:
            bot.send_message(chat_id, f"❌ Transcription error: {e}", reply_to_message_id=orig_msg_id)
        except Exception:
            pass
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        return
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    if not text or str(text).startswith("Error:"):
        bot.send_message(chat_id, text or "⚠️ Warning Make sure the voice is clear or speaking in the language you Choosed.", reply_to_message_id=orig_msg_id)
        return
    sent_message = None
    if len(text) > 4000:
        if mode == "💬 Split messages":
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                sent = bot.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
                sent_message = sent
        else:
            file_name = os.path.join(DOWNLOADS_DIR, "Transcript.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                bot.send_document(chat_id, open(file_name, "rb"), caption="Open this file and copy the text inside 👍", reply_to_message_id=orig_msg_id)
            except Exception:
                pass
            try:
                os.remove(file_name)
            except Exception:
                pass
    else:
        sent_message = bot.send_message(chat_id, text, reply_to_message_id=orig_msg_id)
    if sent_message:
        try:
            keyboard = build_action_keyboard(sent_message.chat.id, sent_message.message_id, len(text))
            user_transcriptions.setdefault(sent_message.chat.id, {})[sent_message.message_id] = {"text": text, "origin": orig_msg_id}
            action_usage[f"{sent_message.chat.id}|{sent_message.message_id}|clean"] = 0
            if len(text) > 1000:
                action_usage[f"{sent_message.chat.id}|{sent_message.message_id}|summarize"] = 0
            bot.edit_message_reply_markup(sent_message.chat.id, sent_message.message_id, reply_markup=keyboard)
        except Exception as e:
            logging.error(f"Failed to attach keyboard or init usage: {e}")

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_media(message):
    if not ensure_joined_and_count(message):
        return
    uid = message.from_user.id
    if uid not in user_lang:
        keyboard = types.InlineKeyboardMarkup()
        row = []
        for i, (label, code) in enumerate(LANGS, 1):
            row.append(types.InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start"))
            if i % 3 == 0:
                keyboard.row(*row)
                row = []
        if row:
            keyboard.row(*row)
        bot.send_message(message.chat.id, "*Please choose your file language first:*", reply_markup=keyboard)
        return
    size = None
    try:
        if message.document and message.document.file_size:
            size = message.document.file_size
        elif message.audio and message.audio.file_size:
            size = message.audio.file_size
        elif message.video and message.video.file_size:
            size = message.video.file_size
        elif message.voice and message.voice.file_size:
            size = message.voice.file_size
    except Exception:
        size = None
    if size is not None and size > MAX_UPLOAD_SIZE:
        bot.send_message(message.chat.id, f"Just Send me a file less than {MAX_UPLOAD_MB}MB 😎")
        return
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        file_path = download_media_file(message)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Download error: {e}")
        return
    threading.Thread(target=process_transcription_and_send, args=(message.chat.id, message.message_id, file_path, uid)).start()

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("clean|"))
def clean_up_callback(call):
    if not ensure_joined_and_count(call):
        return
    try:
        _, chat_id_str, msg_id_str = call.data.split("|")
        chat_id = int(chat_id_str)
        msg_id = int(msg_id_str)
    except Exception:
        bot.answer_callback_query(call.id, "Invalid callback data.", show_alert=True)
        return
    usage_key = f"{chat_id}|{msg_id}|clean"
    usage = action_usage.get(usage_key, 0)
    if usage >= 1:
        bot.answer_callback_query(call.id, "Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    action_usage[usage_key] = usage + 1
    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        bot.answer_callback_query(call.id, "Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    stored_text = stored.get("text")
    orig_msg_id = stored.get("origin")
    bot.answer_callback_query(call.id, "Cleaning up...")
    bot.send_chat_action(chat_id, 'typing')
    try:
        uid = call.from_user.id
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        cleaned_text = ask_gemini(stored_text, instruction)
        if not cleaned_text:
            bot.send_message(chat_id, "No cleaned text returned.", reply_to_message_id=orig_msg_id)
            return
        if len(cleaned_text) > 4000:
            if mode == "💬 Split messages":
                for part in [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]:
                    bot.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, "Cleaned.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(cleaned_text)
                bot.send_document(chat_id, open(file_name, "rb"), caption="Cleaned Transcript", reply_to_message_id=orig_msg_id)
                try:
                    os.remove(file_name)
                except Exception:
                    pass
        else:
            bot.send_message(chat_id, cleaned_text, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in clean_up_callback")
        bot.send_message(chat_id, f"❌ Error during cleanup: {e}", reply_to_message_id=orig_msg_id)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("summarize|"))
def summarize_callback(call):
    if not ensure_joined_and_count(call):
        return
    try:
        _, chat_id_str, msg_id_str = call.data.split("|")
        chat_id = int(chat_id_str)
        msg_id = int(msg_id_str)
    except Exception:
        bot.answer_callback_query(call.id, "Invalid callback data.", show_alert=True)
        return
    usage_key = f"{chat_id}|{msg_id}|summarize"
    usage = action_usage.get(usage_key, 0)
    if usage >= 1:
        bot.answer_callback_query(call.id, "Summarize unavailable (maybe expired or not found).", show_alert=True)
        return
    action_usage[usage_key] = usage + 1
    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        bot.answer_callback_query(call.id, "Summarize unavailable (maybe expired or not found).", show_alert=True)
        return
    stored_text = stored.get("text")
    orig_msg_id = stored.get("origin")
    bot.answer_callback_query(call.id, "Generating summary...")
    bot.send_chat_action(chat_id, 'typing')
    try:
        uid = call.from_user.id
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        summary = ask_gemini(stored_text, instruction)
        if not summary:
            bot.send_message(chat_id, "No Summary returned.", reply_to_message_id=orig_msg_id)
            return
        if len(summary) > 4000:
            if mode == "💬 Split messages":
                for part in [summary[i:i+4000] for i in range(0, len(summary), 4000)]:
                    bot.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, "Summary.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(summary)
                bot.send_document(chat_id, open(file_name, "rb"), caption="Summary", reply_to_message_id=orig_msg_id)
                try:
                    os.remove(file_name)
                except Exception:
                    pass
        else:
            bot.send_message(chat_id, summary, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in summarize_callback")
        bot.send_message(chat_id, f"❌ Error during summary: {e}", reply_to_message_id=orig_msg_id)

@flask_app.route("/", methods=["GET"])
def keep_alive():
    return "Bot is alive ✅", 200

@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_json())
    bot.process_new_updates([update])
    return "", 200

def set_webhook():
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL + "/" + BOT_TOKEN)
    else:
        bot.remove_webhook()

if __name__ == "__main__":
    set_webhook()
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=PORT)).start()
