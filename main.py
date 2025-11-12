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

flask_app = Flask(__name__)

API_ID = int(os.environ.get("API_ID", "29169428"))
API_HASH = os.environ.get("API_HASH", "55742b16a85aac494c7944568b5507e5")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw")
WEBHOOK_URL = os.environ.get("https://midkayga-2-baad-1ggd.onrender.com")

REQUEST_TIMEOUT_GEMINI = int(os.environ.get("REQUEST_TIMEOUT_GEMINI", "300"))

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "250"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024

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

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200

@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Invalid request', 400

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
    buttons.append([types.InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}")])
    if text_length > 1000:
        buttons.append([types.InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")])
    return types.InlineKeyboardMarkup(buttons)

def download_media(message: types.Message) -> str:
    file_id = None
    file_name = None
    
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.audio:
        file_id = message.audio.file_id
        file_name = f"{message.audio.file_unique_id}.ogg"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"{message.video.file_unique_id}.mp4"
    elif message.voice:
        file_id = message.voice.file_id
        file_name = f"{message.voice.file_unique_id}.ogg"
    
    if file_id is None:
        raise Exception("Could not find file_id in message")
    
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    file_path = os.path.join(DOWNLOADS_DIR, file_name or file_info.file_path.split('/')[-1])
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
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

Send a voice/audio/video (up to {MAX_UPLOAD_MB}MB) and I will transcribe it Need help? Contact: @lakigithub
"""

def is_user_in_channel(user_id: int) -> bool:
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ('member', 'administrator', 'creator', 'restricted')
    except Exception:
        return False

def ensure_joined(obj) -> bool:
    is_callback = False
    if isinstance(obj, types.CallbackQuery):
        uid = obj.from_user.id
        reply_target = obj.message
        is_callback = True
    else:
        uid = obj.from_user.id
        reply_target = obj
    
    count = user_usage_count.get(uid, 0)
    if count < 3:
        user_usage_count[uid] = count + 1
        return True
    
    try:
        if is_user_in_channel(uid):
            return True
    except Exception:
        pass
    
    kb = types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]])
    text = f"🚫 First join the channel {REQUIRED_CHANNEL} to use this bot"
    
    try:
        if is_callback:
            try:
                bot.answer_callback_query(obj.id, "🚫 First join the channel", show_alert=True)
            except Exception:
                pass
        
        if hasattr(reply_target, 'chat') and hasattr(reply_target, 'message_id'):
            bot.send_message(reply_target.chat.id, text, reply_markup=kb, reply_to_message_id=reply_target.message_id)
        else:
            bot.send_message(uid, text, reply_markup=kb)
            
    except Exception:
        try:
            bot.send_message(uid, text, reply_markup=kb)
        except Exception:
            pass
    return False

@bot.message_handler(commands=['start'], private=True)
def start(message: types.Message):
    if not ensure_joined(message):
        return
    buttons, row = [], []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(types.InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = types.InlineKeyboardMarkup(buttons)
    bot.reply_to(message, "**Choose your file language for transcription using the below buttons:**", reply_markup=keyboard)

@bot.message_handler(commands=['help'], private=True)
def help_command(message: types.Message):
    if not ensure_joined(message):
        return
    bot.reply_to(message, HELP_MESSAGE)

@bot.message_handler(commands=['lang'], private=True)
def lang_command(message: types.Message):
    if not ensure_joined(message):
        return
    buttons, row = [], []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(types.InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|lang"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = types.InlineKeyboardMarkup(buttons)
    bot.reply_to(message, "**Choose your file language for transcription using the below buttons:**", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang|'))
def language_callback_query(callback_query: types.CallbackQuery):
    if not ensure_joined(callback_query):
        return
    try:
        parts = callback_query.data.split("|")
        _, code, label = parts[:3]
        origin = parts[3] if len(parts) > 3 else "unknown"
    except Exception:
        bot.answer_callback_query(callback_query.id, "Invalid language selection data.", show_alert=True)
        return
    
    uid = callback_query.from_user.id
    user_lang[uid] = code
    
    try:
        if origin == "start":
            bot.edit_message_text(WELCOME_MESSAGE, chat_id=callback_query.message.chat.id, message_id=callback_query.message.id, reply_markup=None)
        elif origin == "lang":
            bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.id)
    except Exception as e:
        logging.error(f"Error editing/deleting message in lang callback: {e}")

    bot.answer_callback_query(callback_query.id, f"Language set to: {label}", show_alert=False)

@bot.message_handler(commands=['mode'], private=True)
def choose_mode(message: types.Message):
    if not ensure_joined(message):
        return
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("💬 Split messages", callback_data="mode|Split messages")],
        [types.InlineKeyboardButton("📄 Text File", callback_data="mode|Text File")]
    ])
    bot.reply_to(message, "Choose **output mode**:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mode|'))
def mode_callback_query(callback_query: types.CallbackQuery):
    if not ensure_joined(callback_query):
        return
    try:
        _, mode_name = callback_query.data.split("|")
    except Exception:
        bot.answer_callback_query(callback_query.id, "Invalid mode selection data.", show_alert=True)
        return
    
    uid = callback_query.from_user.id
    user_mode[uid] = mode_name
    bot.answer_callback_query(callback_query.id, f"Mode set to: {mode_name}", show_alert=False)
    
    try:
        bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.id)
    except Exception:
        pass

@bot.message_handler(content_types=['text'], private=True)
def handle_text(message: types.Message):
    if not ensure_joined(message):
        return
    uid = message.from_user.id
    text = message.text
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        bot.reply_to(message, f"Output mode set to: **{text}**")
        return

@bot.message_handler(content_types=['audio', 'voice', 'video', 'document'], private=True)
def handle_media(message: types.Message):
    if not ensure_joined(message):
        return
    uid = message.from_user.id
    if uid not in user_lang:
        buttons, row = [], []
        for i, (label, code) in enumerate(LANGS, 1):
            row.append(types.InlineKeyboardButton(label, callback_data=f"lang|{code}|{label}|start"))
            if i % 3 == 0:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        keyboard = types.InlineKeyboardMarkup(buttons)
        bot.reply_to(message, "**Please choose your file language first:**", reply_markup=keyboard)
        return
    
    size = None
    try:
        if message.document:
            size = message.document.file_size
        elif message.audio:
            size = message.audio.file_size
        elif message.video:
            size = message.video.file_size
        elif message.voice:
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
        file_path = download_media(message)
    except Exception as e:
        bot.reply_to(message, f"⚠️ Download error: {e}")
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    text = ""
    try:
        text = transcribe_file(file_path, lang)
    except Exception as e:
        bot.reply_to(message, f"❌ Transcription error: {e}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    
    if not text or text.startswith("Error:"):
        bot.reply_to(message, text or "⚠️ Warning Make sure the voice is clear or speaking in the language you Choosed.")
        return
    
    reply_msg_id = message.message_id
    sent_message = None
    
    if len(text) > 4000:
        if mode == "💬 Split messages":
            for part in [text[i:i+4000] for i in range(0, len(text), 4000)]:
                bot.send_chat_action(message.chat.id, 'typing')
                sent_message = bot.send_message(message.chat.id, part, reply_to_message_id=reply_msg_id)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, "Transcript.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            bot.send_chat_action(message.chat.id, 'upload_document')
            try:
                with open(file_name, "rb") as f_doc:
                    sent_message = bot.send_document(message.chat.id, f_doc, caption="Open this file and copy the text inside 👍", reply_to_message_id=reply_msg_id)
            except Exception as e:
                bot.reply_to(message, f"Error sending file: {e}")
            finally:
                if os.path.exists(file_name):
                    os.remove(file_name)
    else:
        bot.send_chat_action(message.chat.id, 'typing')
        sent_message = bot.send_message(message.chat.id, text, reply_to_message_id=reply_msg_id)
    
    if sent_message:
        try:
            keyboard = build_action_keyboard(sent_message.chat.id, sent_message.message_id, len(text))
            user_transcriptions.setdefault(sent_message.chat.id, {})[sent_message.message_id] = {"text": text, "origin": reply_msg_id}
            action_usage[f"{sent_message.chat.id}|{sent_message.message_id}|clean"] = 0
            if len(text) > 1000:
                action_usage[f"{sent_message.chat.id}|{sent_message.message_id}|summarize"] = 0
            bot.edit_message_reply_markup(chat_id=sent_message.chat.id, message_id=sent_message.message_id, reply_markup=keyboard)
        except Exception as e:
            logging.error(f"Failed to attach keyboard or init usage: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('clean|'))
def clean_up_callback(callback_query: types.CallbackQuery):
    if not ensure_joined(callback_query):
        return
    try:
        _, chat_id_str, msg_id_str = callback_query.data.split("|")
        chat_id = int(chat_id_str)
        msg_id = int(msg_id_str)
    except Exception:
        bot.answer_callback_query(callback_query.id, "Invalid callback data.", show_alert=True)
        return
    
    usage_key = f"{chat_id}|{msg_id}|clean"
    usage = action_usage.get(usage_key, 0)
    if usage >= 1:
        bot.answer_callback_query(callback_query.id, "Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    action_usage[usage_key] = usage + 1
    
    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        bot.answer_callback_query(callback_query.id, "Clean up unavailable (maybe expired or not found).", show_alert=True)
        return
    
    stored_text = stored.get("text")
    orig_msg_id = stored.get("origin")
    bot.answer_callback_query(callback_query.id, "Cleaning up...", show_alert=False)
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        uid = callback_query.from_user.id
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
                bot.send_chat_action(chat_id, 'upload_document')
                try:
                    with open(file_name, "rb") as f_doc:
                        bot.send_document(chat_id, f_doc, caption="Cleaned Transcript", reply_to_message_id=orig_msg_id)
                finally:
                    if os.path.exists(file_name):
                        os.remove(file_name)
        else:
            bot.send_message(chat_id, cleaned_text, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in clean_up_callback")
        bot.send_message(chat_id, f"❌ Error during cleanup: {e}", reply_to_message_id=orig_msg_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('summarize|'))
def get_key_points_callback(callback_query: types.CallbackQuery):
    if not ensure_joined(callback_query):
        return
    try:
        _, chat_id_str, msg_id_str = callback_query.data.split("|")
        chat_id = int(chat_id_str)
        msg_id = int(msg_id_str)
    except Exception:
        bot.answer_callback_query(callback_query.id, "Invalid callback data.", show_alert=True)
        return

    usage_key = f"{chat_id}|{msg_id}|summarize"
    usage = action_usage.get(usage_key, 0)
    if usage >= 1:
        bot.answer_callback_query(callback_query.id, "Summarize unavailable (maybe expired or not found).", show_alert=True)
        return
    action_usage[usage_key] = usage + 1
    
    stored = user_transcriptions.get(chat_id, {}).get(msg_id)
    if not stored:
        bot.answer_callback_query(callback_query.id, "Summarize unavailable (maybe expired or not found).", show_alert=True)
        return

    stored_text = stored.get("text")
    orig_msg_id = stored.get("origin")
    bot.answer_callback_query(callback_query.id, "Generating summary...", show_alert=False)
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        uid = callback_query.from_user.id
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
                bot.send_chat_action(chat_id, 'upload_document')
                try:
                    with open(file_name, "rb") as f_doc:
                        bot.send_document(chat_id, f_doc, caption="Summary", reply_to_message_id=orig_msg_id)
                finally:
                    if os.path.exists(file_name):
                        os.remove(file_name)
        else:
            bot.send_message(chat_id, summary, reply_to_message_id=orig_msg_id)
    except Exception as e:
        logging.exception("Error in get_key_points_callback")
        bot.send_message(chat_id, f"❌ Error during summary: {e}", reply_to_message_id=orig_msg_id)

if __name__ == "__main__":
    if not WEBHOOK_URL:
        logging.error("WEBHOOK_URL environment variable not set. Exiting.")
    else:
        try:
            bot.remove_webhook()
            bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
            logging.info(f"Webhook set to {WEBHOOK_URL}/{BOT_TOKEN}")
            port = int(os.environ.get("PORT", 8080))
            flask_app.run(host="0.0.0.0", port=port)
        except Exception as e:
            logging.error(f"Error starting bot or setting webhook: {e}")
