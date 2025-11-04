import os
import asyncio
import threading
import time
import re
from collections import Counter
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import assemblyai as aai
from flask import Flask, request

flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7920977306:AAHhFpv2ImMsiowjpm288ebRdxAjoJZwWec"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"

aai.settings.api_key = ASSEMBLYAI_API_KEY

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

LANGS = [
("🇬🇧 English","en"),
("🇸🇦 العربية","ar"),
("🇪🇸 Español","es"),
("🇫🇷 Français","fr"),
("🇷🇺 Русский","ru"),
("🇩🇪 Deutsch","de"),
("🇮🇳 हिन्दी","hi"),
("🇮🇷 فارسی","fa"),
("🇮🇩 Indonesia","id"),
("🇺🇦 Українська","uk"),
("🇦🇿 Azərbaycan","az"),
("🇮🇹 Italiano","it"),
("🇹🇷 Türkçe","tr"),
("🇧🇬 Български","bg"),
("🇷🇸 Srpski","sr"),
("🇵🇰 اردو","ur"),
("🇹🇭 ไทย","th"),
("🇻🇳 Tiếng Việt","vi"),
("🇯🇵 日本語","ja"),
("🇰🇷 한국어","ko"),
("🇨🇳 中文","zh"),
("🇳🇱 Nederlands","nl"),
("🇸🇪 Svenska","sv"),
("🇳🇴 Norsk","no"),
("🇮🇱 עברית","he"),
("🇩🇰 Dansk","da"),
("🇪🇹 አማርኛ","am"),
("🇫🇮 Suomi","fi"),
("🇧🇩 বাংলা","bn"),
("🇰🇪 Kiswahili","sw"),
("🇪🇹 Oromoo","om"),
("🇳🇵 नेपाली","ne"),
("🇵🇱 Polski","pl"),
("🇬🇷 Ελληνικά","el"),
("🇨🇿 Čeština","cs"),
("🇮🇸 Íslenska","is"),
("🇱🇹 Lietuvių","lt"),
("🇱🇻 Latviešu","lv"),
("🇭🇷 Hrvatski","hr"),
("🇷🇸 Bosanski","bs"),
("🇭🇺 Magyar","hu"),
("🇷🇴 Română","ro"),
("🇸🇴 Somali","so"),
("🇲🇾 Melayu","ms"),
("🇺🇿 O'zbekcha","uz"),
("🇵🇭 Tagalog","tl"),
("🇵🇹 Português","pt")
]

LABELS = [label for label,code in LANGS]
LABEL_TO_CODE = {label: code for label,code in LANGS}
user_lang = {}
user_mode = {}

user_transcriptions = {}
action_usage = {}

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def download_media(message: Message, file_path: str) -> str:
    await message.download(file_path)
    return file_path

def transcribe_file(file_path: str) -> str:
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(file_path)
    if getattr(transcript, "error", None):
        return f"Error: {transcript.error}"
    return getattr(transcript, "text", "") or ""

def normalize_text_offline(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\[.*?\]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s([,\.!?])', r'\1', text)
    return text

def extract_key_points_offline(text: str, max_points: int = 6) -> str:
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r'(?<=[\.\!\?])\s+', text) if s.strip()]
    if not sentences:
        return ""
    words = [w for w in re.findall(r'\w+', text.lower()) if len(w) > 3]
    if not words:
        return "\n".join(f"- {s}" for s in sentences[:max_points])
    freq = Counter(words)
    sentence_scores = [(sum(freq.get(w, 0) for w in re.findall(r'\w+', s.lower())), s) for s in sentences]
    sentence_scores.sort(key=lambda x: x[0], reverse=True)
    top_sentences = sorted(sentence_scores[:max_points], key=lambda x: sentences.index(x[1]))
    return "\n".join(f"- {s}" for _, s in top_sentences)

def build_inline_actions(chat_id: int, message_id: int, include_summarize: bool):
    buttons = []
    buttons.append([InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{chat_id}|{message_id}")])
    if include_summarize:
        buttons[0].append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{chat_id}|{message_id}"))
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    buttons = []
    row = []
    for i, label in enumerate(LABELS, 1):
        row.append(label)
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text("Choose your language from the keyboard below", reply_markup=keyboard)

@app.on_message(filters.command("mode") & filters.private)
async def choose_mode(client, message: Message):
    buttons = [["💬 Split messages", "📄 Text File"]]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text("Choose output mode:", reply_markup=keyboard)

@app.on_message(filters.private & filters.text)
async def handle_text(client, message: Message):
    text = message.text
    uid = message.from_user.id
    if text in LABEL_TO_CODE:
        code = LABEL_TO_CODE[text]
        user_lang[uid] = code
        await message.reply_text(f"Language set to {code}")
        return
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        await message.reply_text(f"Output mode set to: {text}")
        return

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message: Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "en")
    mode = user_mode.get(uid, "📄 Text File")
    status = await message.reply_text("Downloading...", reply_to_message_id=message.id)
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
        await status.delete()
        await message.reply_text(f"Download error: {e}")
        return
    await status.edit_text("Transcribing... please wait.")
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_file, file_path)
    except Exception as e:
        await status.delete()
        await message.reply_text(f"Transcription error: {e}")
        return
    await status.delete()
    cleaned_text = text or ""
    cleaned_text = normalize_text_offline(cleaned_text)
    chat_id = message.chat.id
    if len(cleaned_text) > 4000:
        if mode == "💬 Split messages":
            parts = [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]
            last_sent = None
            for part in parts:
                last_sent = await message.reply_text(part)
            try:
                include_summarize = len(cleaned_text) > 1000
                await app.edit_message_reply_markup(chat_id, last_sent.message_id, reply_markup=build_inline_actions(chat_id, last_sent.message_id, include_summarize))
            except:
                pass
            try:
                user_transcriptions.setdefault(str(chat_id), {})[last_sent.message_id] = cleaned_text
                action_usage[f"{chat_id}|{last_sent.message_id}|clean_up"] = 0
                action_usage[f"{chat_id}|{last_sent.message_id}|get_key_points"] = 0
            except:
                pass
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{message.id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            sent = await message.reply_document(file_name, caption="Transcription saved as .txt file", reply_to_message_id=message.id)
            try:
                include_summarize = len(cleaned_text) > 1000
                await app.edit_message_reply_markup(chat_id, sent.message_id, reply_markup=build_inline_actions(chat_id, sent.message_id, include_summarize))
            except:
                pass
            try:
                user_transcriptions.setdefault(str(chat_id), {})[sent.message_id] = cleaned_text
                action_usage[f"{chat_id}|{sent.message_id}|clean_up"] = 0
                action_usage[f"{chat_id}|{sent.message_id}|get_key_points"] = 0
            except:
                pass
            os.remove(file_name)
    else:
        sent_msg = await message.reply_text(f"{cleaned_text}\n\nPowered by @MediaToTextBot", reply_to_message_id=message.id)
        try:
            include_summarize = len(cleaned_text) > 1000
            await app.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=build_inline_actions(chat_id, sent_msg.message_id, include_summarize))
        except:
            pass
        try:
            user_transcriptions.setdefault(str(chat_id), {})[sent_msg.message_id] = cleaned_text
            action_usage[f"{chat_id}|{sent_msg.message_id}|clean_up"] = 0
            action_usage[f"{chat_id}|{sent_msg.message_id}|get_key_points"] = 0
        except:
            pass

@app.on_callback_query(filters.create(lambda _, __, query: query.data and query.data.startswith("get_key_points")))
async def get_key_points_cb(client: Client, callback_query: CallbackQuery):
    data = callback_query.data or ""
    parts = data.split("|")
    if len(parts) == 3:
        _, chat_part, msg_part = parts
    elif len(parts) == 2:
        _, msg_part = parts
        chat_part = str(callback_query.message.chat.id)
    else:
        await callback_query.answer("Invalid request", show_alert=True)
        return
    try:
        chat_id_val = int(chat_part)
        msg_id = int(msg_part)
    except:
        await callback_query.answer("Invalid message id", show_alert=True)
        return
    usage_key = f"{chat_id_val}|{msg_id}|get_key_points"
    usage = action_usage.get(usage_key, 0)
    if usage >= 1:
        await callback_query.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
        return
    action_usage[usage_key] = usage + 1
    uid_key = str(chat_id_val)
    stored = user_transcriptions.get(uid_key, {}).get(msg_id)
    if not stored:
        await callback_query.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
        return
    await callback_query.answer("Generating...")
    status = await app.send_message(callback_query.message.chat.id, "🔄 Processing...", reply_to_message_id=callback_query.message.message_id)
    try:
        summary = extract_key_points_offline(stored, max_points=6)
    except:
        summary = ""
    if not summary:
        try:
            await app.edit_message_text("No Summary returned.", chat_id=callback_query.message.chat.id, message_id=status.message_id)
        except:
            pass
    else:
        try:
            if len(summary) > 4000:
                mode = user_mode.get(callback_query.from_user.id, "📄 Text File")
                if mode == "📄 Text File":
                    fname = os.path.join(DOWNLOADS_DIR, f"summary_{msg_id}.txt")
                    with open(fname, "w", encoding="utf-8") as f:
                        f.write(summary)
                    await app.delete_messages(callback_query.message.chat.id, status.message_id)
                    await app.send_document(callback_query.message.chat.id, fname, reply_to_message_id=callback_query.message.message_id)
                    os.remove(fname)
                else:
                    chunks = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
                    for chunk in chunks:
                        await app.send_message(callback_query.message.chat.id, chunk)
                    try:
                        last_sent = await app.send_message(callback_query.message.chat.id, "Summary delivered.")
                        user_transcriptions.setdefault(str(callback_query.message.chat.id), {})[last_sent.message_id] = summary
                    except:
                        pass
            else:
                await app.edit_message_text(summary, chat_id=callback_query.message.chat.id, message_id=status.message_id)
                user_transcriptions.setdefault(str(callback_query.message.chat.id), {})[status.message_id] = summary
        except:
            pass

@app.on_callback_query(filters.create(lambda _, __, query: query.data and query.data.startswith("clean_up")))
async def clean_up_cb(client: Client, callback_query: CallbackQuery):
    data = callback_query.data or ""
    parts = data.split("|")
    if len(parts) == 3:
        _, chat_part, msg_part = parts
    elif len(parts) == 2:
        _, msg_part = parts
        chat_part = str(callback_query.message.chat.id)
    else:
        await callback_query.answer("Invalid request", show_alert=True)
        return
    try:
        chat_id_val = int(chat_part)
        msg_id = int(msg_part)
    except:
        await callback_query.answer("Invalid message id", show_alert=True)
        return
    usage_key = f"{chat_id_val}|{msg_id}|clean_up"
    usage = action_usage.get(usage_key, 0)
    if usage >= 1:
        await callback_query.answer("Clean up unavailable (maybe expired)", show_alert=True)
        return
    action_usage[usage_key] = usage + 1
    uid_key = str(chat_id_val)
    stored = user_transcriptions.get(uid_key, {}).get(msg_id)
    if not stored:
        await callback_query.answer("Clean up unavailable (maybe expired)", show_alert=True)
        return
    await callback_query.answer("Cleaning up...")
    status = await app.send_message(callback_query.message.chat.id, "🔄 Processing...", reply_to_message_id=callback_query.message.message_id)
    try:
        cleaned = normalize_text_offline(stored)
    except:
        cleaned = ""
    if not cleaned:
        try:
            await app.edit_message_text("No cleaned text returned.", chat_id=callback_query.message.chat.id, message_id=status.message_id)
        except:
            pass
        return
    mode = user_mode.get(callback_query.from_user.id, "📄 Text File")
    try:
        if len(cleaned) > 4000:
            if mode == "📄 Text File":
                fname = os.path.join(DOWNLOADS_DIR, f"cleaned_{msg_id}.txt")
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(cleaned)
                await app.delete_messages(callback_query.message.chat.id, status.message_id)
                sent = await app.send_document(callback_query.message.chat.id, fname, reply_to_message_id=callback_query.message.message_id)
                os.remove(fname)
                user_transcriptions.setdefault(str(callback_query.message.chat.id), {})[sent.message_id] = cleaned
                action_usage[f"{callback_query.message.chat.id}|{sent.message_id}|clean_up"] = 0
                action_usage[f"{callback_query.message.chat.id}|{sent.message_id}|get_key_points"] = 0
            else:
                await app.delete_messages(callback_query.message.chat.id, status.message_id)
                chunks = [cleaned[i:i+4000] for i in range(0, len(cleaned), 4000)]
                last_sent = None
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        last_sent = await app.send_message(callback_query.message.chat.id, chunk, reply_to_message_id=callback_query.message.message_id)
                    else:
                        last_sent = await app.send_message(callback_query.message.chat.id, chunk)
                user_transcriptions.setdefault(str(callback_query.message.chat.id), {})[last_sent.message_id] = cleaned
                action_usage[f"{callback_query.message.chat.id}|{last_sent.message_id}|clean_up"] = 0
                action_usage[f"{callback_query.message.chat.id}|{last_sent.message_id}|get_key_points"] = 0
        else:
            await app.edit_message_text(cleaned, chat_id=callback_query.message.chat.id, message_id=status.message_id)
            user_transcriptions.setdefault(str(callback_query.message.chat.id), {})[status.message_id] = cleaned
            action_usage[f"{callback_query.message.chat.id}|{status.message_id}|clean_up"] = 0
            action_usage[f"{callback_query.message.chat.id}|{status.message_id}|get_key_points"] = 0
    except:
        pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app.run()
