import os
import asyncio
import threading
import json
import requests
import io
import logging
from flask import Flask, request
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction
import assemblyai as aai
from functools import wraps  # Lagu daray

flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7757263177:AAEJy_de-IOP11BOrgY0HMj-cvhy_CezGDU"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"
GEMINI_API_KEY = "AIzaSyDCOMrP8YYSr5t8N7WZoMLQnKOQR4ByTvo"
REQUEST_TIMEOUT_GEMINI = 300

# ❗️❗️ BEDEL HALKAN: Ku qor username-ka channel-kaaga (tusaale: "@MagacaChannelKaaga")
# Bot-kaagu waa inuu Admin ka yahay channel-kan.
REQUIRED_CHANNEL = "@laaaaaaaaalaaaaaa" 

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

# --- Shaqada Hubinta Xubinnimada (Force Subscribe) ---

def membership_required(func):
    """
    Decorator-kani wuxuu hubinayaa haddii isticmaalaha uu xubin ka yahay REQUIRED_CHANNEL
    ka hor inta uusan fulin amarka.
    """
    @wraps(func)
    async def wrapper(client, update, *args, **kwargs):
        if not REQUIRED_CHANNEL:
            # Haddii REQUIRED_CHANNEL aan la dejin, si caadi ah u wad
            return await func(client, update, *args, **kwargs)

        # Soo saar user_id iyo nooca chat-ka
        if isinstance(update, Message):
            user_id = update.from_user.id
            message_object = update
            chat_type = update.chat.type
        elif isinstance(update, CallbackQuery):
            user_id = update.from_user.id
            message_object = update
            chat_type = update.message.chat.type
        else:
            # Nooc update ah oo aan la garanayn, iska daa
            return await func(client, update, *args, **kwargs)

        # Ka bood check-ga haddii aysan ahayn 'private' chat
        if chat_type != "private":
            return await func(client, update, *args, **kwargs)

        try:
            # Hubi xubinnimada
            await client.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            # User waa xubin, sii wad
            return await func(client, update, *args, **kwargs)
        
        except Exception as e:
            # User maaha xubin (ama cilad kale ayaa dhacday)
            logging.warning(f"User {user_id} is not a member of {REQUIRED_CHANNEL}. Error: {e}")
            
            channel_username = REQUIRED_CHANNEL.lstrip('@')
            join_text = (
                f"👋 **Waa inaad ku biirtaa Channel-ka!**\n\n"
                f"Si aad u isticmaasho bot-kan, fadlan marka hore ku biir channel-kayaga.\n\n"
                f"Markaad ku biirto, ku soo noqo oo mar kale isku day."
            )
            join_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Join Channel 📢", url=f"https://t.me/{channel_username}")]]
            )

            if isinstance(message_object, Message):
                await message_object.reply_text(join_text, reply_markup=join_keyboard, quote=True)
            elif isinstance(message_object, CallbackQuery):
                # Ugu jawaab callback-ga si uu u joojiyo 'loading'
                await message_object.answer("Fadlan ku biir channel-ka si aad u sii wadato!", show_alert=True)
                # U dir fariin cusub (maadaama mararka qaarkood aysan fiicnayn in la edit-gareeyo fariintii hore)
                await client.send_message(message_object.message.chat.id, join_text, reply_markup=join_keyboard)
        
    return wrapper

# --- Shaqadii Bot-ka ---

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
    buttons.append([InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean|{chat_id}|{message_id}")])
    if text_length > 1000:
        buttons.append([InlineKeyboardButton("Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")])
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

WELCOME_MESSAGE = """👋 **Salaam!**
• Send me
• **voice message**
• **audio file**
• **video**
• to transcribe for free
"""

@app.on_message(filters.command("start") & filters.private)
@membership_required
async def start(client, message: Message):
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

@app.on_message(filters.command("lang") & filters.private)
@membership_required
async def lang_command(client, message: Message):
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

@app.on_callback_query(filters.regex(r"^lang\|"))
@membership_required
async def language_callback_query(client, callback_query: CallbackQuery):
    try:
        parts = callback_query.data.split("|")
        _, code, label = parts[:3]
        origin = parts[3] if len(parts) > 3 else "unknown"
    except ValueError:
        await callback_query.answer("Invalid language selection data.", show_alert=True)
        return
    
    uid = callback_query.from_user.id
    user_lang[uid] = code
    
    # Haddii asalka uu yahay '/start', fariinta la dooranayo waa in la bedelo midda soo dhaweynta
    if origin == "start":
        await callback_query.message.edit_text(WELCOME_MESSAGE, reply_markup=None)
    # Haddii asalka uu yahay '/lang', waa in la tirtiro fariinta badhamada wadata
    elif origin == "lang":
        await callback_query.message.delete()
    
    await callback_query.answer(f"Language set to: {label}", show_alert=False)

@app.on_message(filters.command("mode") & filters.private)
@membership_required
async def choose_mode(client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Split messages", callback_data="mode|Split messages")],
        [InlineKeyboardButton("📄 Text File", callback_data="mode|Text File")]
    ])
    await message.reply_text("Choose **output mode**:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^mode\|"))
@membership_required
async def mode_callback_query(client, callback_query: CallbackQuery):
    try:
        _, mode_name = callback_query.data.split("|")
    except ValueError:
        await callback_query.answer("Invalid mode selection data.", show_alert=True)
        return
    uid = callback_query.from_user.id
    user_mode[uid] = mode_name
    await callback_query.answer(f"Mode set to: {mode_name}", show_alert=False)
    await callback_query.message.delete()

@app.on_message(filters.private & filters.text)
@membership_required
async def handle_text(client, message: Message):
    text = message.text
    uid = message.from_user.id
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        await message.reply_text(f"Output mode set to: **{text}**")
        return

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
@membership_required
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

@app.on_callback_query(filters.regex(r"^clean\|"))
@membership_required
async def clean_up_callback(client, callback_query: CallbackQuery):
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
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."

        cleaned_text = await loop.run_in_executor(None, ask_gemini, stored_text, instruction)

        if not cleaned_text:
            await client.send_message(chat_id, "No cleaned text returned.", reply_to_message_id=orig_msg_id)
            return

        if len(cleaned_text) > 4000:
            if mode == "💬 Split messages":
                for part in [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]:
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

@app.on_callback_query(filters.regex(r"^summarize\|"))
@membership_required
async def get_key_points_callback(client, callback_query: CallbackQuery):
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
        lang = user_lang.get(uid, "en")
        mode = user_mode.get(uid, "📄 Text File")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."

        summary = await loop.run_in_executor(None, ask_gemini, stored_text, instruction)

        if not summary:
            await client.send_message(chat_id, "No Summary returned.", reply_to_message_id=orig_msg_id)
            return

        if len(summary) > 4000:
            if mode == "💬 Split messages":
                for part in [summary[i:i+4000] for i in range(0, len(summary), 4000)]:
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

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
