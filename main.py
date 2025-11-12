import os
import threading
import json
import requests
import logging
from flask import Flask, request, abort
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import assemblyai as aai

API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = os.environ.get("API_ID", "")
REQUEST_TIMEOUT_GEMINI = int(os.environ.get("REQUEST_TIMEOUT_GEMINI", "300"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "250"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024
DEFAULT_ASSEMBLY_KEYS = "e27f99e6c34e44a4af5e0934b34b3e6f,a6d887c307044ee4a918b868a770e8ef,0272c2f92b1e4b1a96fcec55975c5c2e,b77044ed989546c9ab3a064df4a46d8c,2b7533db7ec849668716b00cb64a9235,defa21f626764d71a1373437f6300d80,26293b7d8dbf43d883ce8a43d3c06f63"
DEFAULT_GEMINI_KEYS = "AIzaSyADfan-yL9WdrlVd3vzbCdJM7tXbA72dG,AIzaSyAKrnVxMMPIqSzovoUggXy5CQ_4Hi7I_NU,AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"
ASSEMBLYAI_API_KEYS = os.environ.get("ASSEMBLYAI_API_KEYS", DEFAULT_ASSEMBLY_KEYS)
GEMINI_API_KEYS = os.environ.get("GEMINI_API_KEYS", DEFAULT_GEMINI_KEYS)
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}"))
    if text_length > 1000:
        kb.row(InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}"))
    return kb

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

WELCOME_MESSAGE = "👋 **Salaam!**\n• Send me\n• **voice message**\n• **audio file**\n• **video**\n• to transcribe for free\n"
HELP_MESSAGE = f"/start - Show welcome message\n/lang  - Change language\n/mode  - Change result delivery mode\n/help  - This help message\n\nSend a voice/audio/video (up to {MAX_UPLOAD_MB}MB) and I will transcribe it Need help? Contact: @lakigithub"

bot = telebot.TeleBot(BOT_TOKEN)
flask_app = Flask(__name__)

def is_user_in_channel(user_id: int) -> bool:
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        status = getattr(member, "status", "")
        return status in ("member", "administrator", "creator", "restricted")
    except Exception:
        return False

def ensure_joined(user_id, reply_func):
    count = user_usage_count.get(user_id, 0)
    if count < 3:
        user_usage_count[user_id] = count + 1
        return True
    try:
        if is_user_in_channel(user_id):
            return True
    except Exception:
        pass
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}"))
    text = f"🚫 First join the channel {REQUIRED_CHANNEL} to use this bot"
    try:
        reply_func(text, reply_markup=kb)
    except Exception:
        try:
            bot.send_message(user_id, text, reply_markup=kb)
        except Exception:
            pass
    return False

def make_lang_keyboard(origin):
    kb = InlineKeyboardMarkup()
    row = []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|{origin}"))
        if i % 3 == 0:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb

@bot.message_handler(commands=['start'])
def start(message):
    if not ensure_joined(message.from_user.id, lambda txt, reply_markup=None: bot.reply_to(message, txt, reply_markup=reply_markup)):
        return
    kb = make_lang_keyboard("start")
    bot.reply_to(message, "**Choose your file language for transcription using the below buttons:**", reply_markup=kb)

@bot.message_handler(commands=['help'])
def help_command(message):
    if not ensure_joined(message.from_user.id, lambda txt, reply_markup=None: bot.reply_to(message, txt, reply_markup=reply_markup)):
        return
    bot.reply_to(message, HELP_MESSAGE)

@bot.message_handler(commands=['lang'])
def lang_command(message):
    if not ensure_joined(message.from_user.id, lambda txt, reply_markup=None: bot.reply_to(message, txt, reply_markup=reply_markup)):
        return
    kb = make_lang_keyboard("lang")
    bot.reply_to(message, "**Choose your file language for transcription using the below buttons:**", reply_markup=kb)

@bot.message_handler(commands=['mode'])
def choose_mode(message):
    if not ensure_joined(message.from_user.id, lambda txt, reply_markup=None: bot.reply_to(message, txt, reply_markup=reply_markup)):
        return
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("💬 Split messages", callback_data="mode|Split messages"))
    kb.row(InlineKeyboardButton("📄 Text File", callback_data="mode|Text File"))
    bot.reply_to(message, "Choose **output mode**:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang|"))
def language_callback_query(call):
    parts = call.data.split("|")
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "Invalid language selection data.", show_alert=True)
        return
    _, code, label = parts[:3]
    origin = parts[3] if len(parts) > 3 else "unknown"
    uid = call.from_user.id
    user_lang[uid] = code
    if origin == "start":
        try:
            bot.edit_message_text(WELCOME_MESSAGE, call.message.chat.id, call.message.message_id)
        except Exception:
            pass
    elif origin == "lang":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
    bot.answer_callback_query(call.id, f"Language set to: {label}", show_alert=False)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode|"))
def mode_callback_query(call):
    parts = call.data.split("|")
    if len(parts) < 2:
        bot.answer_callback_query(call.id, "Invalid mode selection data.", show_alert=True)
        return
    _, mode_name = parts[:2]
    uid = call.from_user.id
    user_mode[uid] = mode_name
    bot.answer_callback_query(call.id, f"Mode set to: {mode_name}", show_alert=False)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

@bot.message_handler(func=lambda m: m.content_type == 'text' and m.chat.type == 'private')
def handle_text(message):
    if not ensure_joined(message.from_user.id, lambda txt, reply_markup=None: bot.reply_to(message, txt, reply_markup=reply_markup)):
        return
    uid = message.from_user.id
    text = message.text
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        bot.reply_to(message, f"Output mode set to: **{text}**")

def download_media_file(file_id, file_name_hint=None):
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    local_path = os.path.join(DOWNLOADS_DIR, file_info.file_path.replace('/', '_'))
    with open(local_path, 'wb') as f:
        f.write(downloaded)
    return local_path

@bot.message_handler(content_types=['voice','audio','video','document'])
def handle_media(message):
    if not ensure_joined(message.from_user.id, lambda txt, reply_markup=None: bot.reply_to(message, txt, reply_markup=reply_markup)):
        return
    uid = message.from_user.id
    if uid not in user_lang:
        kb = make_lang_keyboard("start")
        bot.reply_to(message, "**Please choose your file language first:**", reply_markup=kb)
        return
    size = None
    try:
        if message.document and getattr(message.document, "file_size", None):
            size = message.document.file_size
        elif message.audio and getattr(message.audio, "file_size", None):
            size = message.audio.file_size
        elif message.video and getattr(message.video, "file_size", None):
            size = message.video.file_size
        elif message.voice and getattr(message.voice, "file_size", None):
            size = message.voice.file_size
    except Exception:
        size = None
    if size is not None and size > MAX_UPLOAD_SIZE:
        bot.reply_to(message, f"Just Send me a file less than {MAX_UPLOAD_MB}MB 😎")
        return
    lang = user_lang[uid]
    mode = user_mode.get(uid, "📄 Text File")
    bot.send_chat_action(message.chat.id, 'typing')
    file_path = None
    try:
        if message.voice:
            file_path = download_media_file(message.voice.file_id)
        elif message.audio:
            file_path = download_media_file(message.audio.file_id)
        elif message.video:
            file_path = download_media_file(message.video.file_id)
        elif message.document:
            file_path = download_media_file(message.document.file_id)
    except Exception as e:
        bot.reply_to(message, f"⚠️ Download error: {e}")
        return
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        text = transcribe_file(file_path, lang)
    except Exception as e:
        bot.reply_to(message, f"❌ Transcription error: {e}")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
    if not text or text.startswith("Error:"):
        bot.reply_to(message, text or "⚠️ Warning Make sure the voice is clear or speaking in the language you Choosed.", reply_to_message_id=message.message_id)
        return
    reply_msg_id = message.message_id
    sent_message = None
    if len(text) > 4095:
        if mode == "💬 Split messages":
            for part in [text[i:i+4095] for i in range(0, len(text), 4095)]:
                bot.send_chat_action(message.chat.id, 'typing')
                sent = bot.reply_to(message, part, reply_to_message_id=reply_msg_id)
                sent_message = sent
        else:
            file_name = os.path.join(DOWNLOADS_DIR, "Transcript.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            bot.send_chat_action(message.chat.id, 'upload_document')
            with open(file_name, 'rb') as doc:
                sent_message = bot.send_document(message.chat.id, doc, caption="Open this file and copy the text inside 👍", reply_to_message_id=reply_msg_id)
            try:
                os.remove(file_name)
            except Exception:
                pass
    else:
        bot.send_chat_action(message.chat.id, 'typing')
        sent_message = bot.reply_to(message, text, reply_to_message_id=reply_msg_id)
    if sent_message:
        try:
            chat_id = sent_message.chat.id
            msg_id = sent_message.message_id
            keyboard = build_action_keyboard(chat_id, msg_id, len(text))
            user_transcriptions.setdefault(chat_id, {})[msg_id] = {"text": text, "origin": reply_msg_id}
            action_usage[f"{chat_id}|{msg_id}|clean"] = 0
            if len(text) > 1000:
                action_usage[f"{chat_id}|{msg_id}|summarize"] = 0
            bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=keyboard)
        except Exception as e:
            logging.error(f"Failed to attach keyboard or init usage: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("clean|"))
def clean_up_callback(call):
    parts = call.data.split("|")
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "Invalid callback data.", show_alert=True)
        return
    chat_id = int(parts[1])
    msg_id = int(parts[2])
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
    bot.answer_callback_query(call.id, "Cleaning up...", show_alert=False)
    bot.send_chat_action(chat_id, 'typing')
    try:
        instruction = f"Clean and normalize this transcription (lang={user_lang.get(call.from_user.id,'en')}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        cleaned_text = ask_gemini(stored_text, instruction)
        if not cleaned_text:
            bot.send_message(chat_id, "No cleaned text returned.", reply_to_message_id=orig_msg_id)
            return
        mode = user_mode.get(call.from_user.id, "📄 Text File")
        if len(cleaned_text) > 4095:
            if mode == "💬 Split messages":
                for part in [cleaned_text[i:i+4095] for i in range(0, len(cleaned_text), 4095)]:
                    bot.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, "Cleaned.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(cleaned_text)
                bot.send_chat_action(chat_id, 'upload_document')
                with open(file_name, 'rb') as doc:
                    bot.send_document(chat_id, doc, caption="Cleaned Transcript", reply_to_message_id=orig_msg_id)
                try:
                    os.remove(file_name)
                except Exception:
                    pass
        else:
            bot.send_message(chat_id, cleaned_text, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in clean_up_callback")
        bot.send_message(chat_id, f"❌ Error during cleanup: {e}", reply_to_message_id=orig_msg_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("summarize|"))
def get_key_points_callback(call):
    parts = call.data.split("|")
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "Invalid callback data.", show_alert=True)
        return
    chat_id = int(parts[1])
    msg_id = int(parts[2])
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
    bot.answer_callback_query(call.id, "Generating summary...", show_alert=False)
    bot.send_chat_action(chat_id, 'typing')
    try:
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={user_lang.get(call.from_user.id,'en')}) without adding any introductions, notes, or extra phrases."
        summary = ask_gemini(stored_text, instruction)
        if not summary:
            bot.send_message(chat_id, "No Summary returned.", reply_to_message_id=orig_msg_id)
            return
        mode = user_mode.get(call.from_user.id, "📄 Text File")
        if len(summary) > 4095:
            if mode == "💬 Split messages":
                for part in [summary[i:i+4095] for i in range(0, len(summary), 4095)]:
                    bot.send_message(chat_id, part, reply_to_message_id=orig_msg_id)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, "Summary.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(summary)
                bot.send_chat_action(chat_id, 'upload_document')
                with open(file_name, 'rb') as doc:
                    bot.send_document(chat_id, doc, caption="Summary", reply_to_message_id=orig_msg_id)
                try:
                    os.remove(file_name)
                except Exception:
                    pass
        else:
            bot.send_message(chat_id, summary, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in get_key_points_callback")
        bot.send_message(chat_id, f"❌ Error during summary: {e}", reply_to_message_id=orig_msg_id)

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return "", 200
    else:
        abort(403)

if __name__ == "__main__":
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    PORT = int(os.environ.get("PORT", "8443"))
    if not WEBHOOK_URL:
        raise SystemExit("WEBHOOK_URL environment variable is required")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.set_webhook(url=WEBHOOK_URL)
    flask_app.run(host="0.0.0.0", port=PORT)
