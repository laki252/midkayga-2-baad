import os
import asyncio
import threading
import io
import time
import re
import requests
from collections import Counter
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
import assemblyai as aai
from flask import Flask

flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = int(os.environ.get("API_ID", "29169428"))
API_HASH = os.environ.get("API_HASH", "55742b16a85aac494c7944568b5507e5")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7920977306:AAHhFpv2ImMsiowjpm288ebRdxAjoJZwWec")
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "91f15c103dbd4b859466a29ee849e3ef")
GEMINI_API_KEYS = [k.strip() for k in os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY", "")).split(",") if k.strip()]

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

user_prefs = {}
user_transcriptions = {}

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def download_media(message: Message, file_path: str) -> str:
    await message.download(file_path)
    return file_path

def transcribe_file(file_path: str) -> str:
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(file_path)
    if getattr(transcript, "error", None):
        return f"Error: {transcript.error}"
    return getattr(transcript, "text", "")

def normalize_text_offline(text):
    return re.sub(r'\s+', ' ', text).strip() if text else text

def extract_key_points_offline(text, max_points=6):
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

def split_text_into_chunks(text, limit=4096):
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + limit, n)
        if end < n:
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunk = text[start:end].strip()
        if not chunk:
            end = start + limit
            chunk = text[start:end].strip()
        chunks.append(chunk)
        start = end
    return chunks

def ask_gemini(text, instruction, timeout=300):
    if not GEMINI_API_KEYS:
        raise RuntimeError("GEMINI_API_KEYS not set")
    last_exception = None
    for api_key in GEMINI_API_KEYS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": instruction}, {"text": text}]}]}
            headers = {"Content-Type": "application/json"}
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()
            if "candidates" in result and isinstance(result["candidates"], list) and len(result["candidates"]) > 0:
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except:
                    return str(result['candidates'][0])
            raise RuntimeError("Gemini response lacks candidates")
        except Exception as e:
            last_exception = e
            continue
    raise RuntimeError(f"All Gemini API keys failed. Last error: {str(last_exception)}")

def build_action_keyboard(chat_id, message_id, text):
    include_summarize = len(text) > 1000 if text else False
    buttons = []
    buttons.append([InlineKeyboardButton("⭐️ Clean transcript", callback_data=f"clean|{chat_id}|{message_id}")])
    if include_summarize:
        buttons.append([InlineKeyboardButton("📝 Get Summarize", callback_data=f"summarize|{chat_id}|{message_id}")])
    buttons.append([InlineKeyboardButton("📤 Result Mode", callback_data=f"mode_menu|{chat_id}|{message_id}")])
    kb = InlineKeyboardMarkup(buttons)
    return kb

def build_mode_keyboard(chat_id, message_id):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📄 .txt file", callback_data=f"set_mode|{chat_id}|{message_id}|file"), InlineKeyboardButton("💬 Split messages", callback_data=f"set_mode|{chat_id}|{message_id}|split")]])
    return kb

async def send_transcription_result(chat_id, reply_to_message_id, text):
    prefs = user_prefs.get(str(chat_id), {})
    mode = prefs.get("mode", "file")
    if not text:
        await app.send_message(chat_id, "⚠️ Warning Make sure the voice is clear or speaking in the language you chose.", reply_to_message_id=reply_to_message_id)
        return None
    if len(text) > 4000:
        if mode == "file":
            f = io.BytesIO(text.encode("utf-8"))
            f.name = "transcript.txt"
            m = await app.send_document(chat_id, f, reply_to_message_id=reply_to_message_id)
            mid = m.message_id
        else:
            chunks = split_text_into_chunks(text, limit=4096)
            last = None
            for idx, chunk in enumerate(chunks):
                if idx == 0:
                    last = await app.send_message(chat_id, chunk, reply_to_message_id=reply_to_message_id)
                else:
                    last = await app.send_message(chat_id, chunk)
            mid = last.message_id if last else None
    else:
        m = await app.send_message(chat_id, text, reply_to_message_id=reply_to_message_id)
        mid = m.message_id
    if mid:
        user_transcriptions.setdefault(str(chat_id), {})[mid] = text
        try:
            kb = build_action_keyboard(chat_id, mid, text)
            await app.edit_message_reply_markup(chat_id, mid, reply_markup=kb)
        except:
            pass
    return mid

@app.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
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
    uid = str(message.from_user.id)
    user_prefs.setdefault(uid, {"lang": "en", "mode": "file"})

@app.on_message(filters.private & filters.text)
async def set_language(_, message: Message):
    text = message.text
    uid = str(message.from_user.id)
    if text in LABEL_TO_CODE:
        code = LABEL_TO_CODE[text]
        prefs = user_prefs.setdefault(uid, {})
        prefs["lang"] = code
        await message.reply_text(f"Language set to {code}")

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(_, message: Message):
    uid = str(message.from_user.id)
    prefs = user_prefs.setdefault(uid, {"lang": "en", "mode": "file"})
    lang = prefs.get("lang", "en")
    await message.reply_text("Downloading...")
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
        await message.reply_text(f"Download error: {e}")
        return
    await message.reply_text("Transcribing... please wait.")
    loop = asyncio.get_event_loop()
    try:
        text = await loop.run_in_executor(None, transcribe_file, file_path)
    except Exception as e:
        await message.reply_text(f"Transcription error: {e}")
        return
    corrected_text = normalize_text_offline(text)
    mid = await send_transcription_result(message.chat.id, message.message_id, corrected_text)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
    try:
        await app.send_message(message.chat.id, "Powered by @MediaToTextBot")
    except:
        pass

@app.on_callback_query()
async def callback_handler(_, cq):
    data = cq.data or ""
    parts = data.split("|")
    if not parts:
        await cq.answer("Invalid action", show_alert=True)
        return
    action = parts[0]
    try:
        if action == "clean" and len(parts) >= 3:
            chat_id = parts[1]
            msg_id = int(parts[2])
            stored = user_transcriptions.get(str(chat_id), {}).get(msg_id)
            if not stored:
                await cq.answer("Clean up unavailable (maybe expired)", show_alert=True)
                return
            await cq.answer("Cleaning up...")
            status = await app.send_message(cq.message.chat.id, "🔄 Processing...", reply_to_message_id=cq.message.message_id)
            try:
                lang = user_prefs.get(str(chat_id), {}).get("lang", "en")
                instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
                try:
                    cleaned = ask_gemini(stored, instruction)
                except:
                    cleaned = normalize_text_offline(stored)
                if not cleaned:
                    await app.edit_message_text("No cleaned text returned.", cq.message.chat.id, status.message_id)
                    return
                prefs = user_prefs.get(str(chat_id), {})
                mode = prefs.get("mode", "file")
                if len(cleaned) > 4000:
                    if mode == "file":
                        f = io.BytesIO(cleaned.encode("utf-8"))
                        f.name = "cleaned.txt"
                        try:
                            await app.delete_messages(cq.message.chat.id, status.message_id)
                        except:
                            pass
                        sent = await app.send_document(cq.message.chat.id, f, reply_to_message_id=cq.message.message_id)
                        user_transcriptions.setdefault(str(chat_id), {})[sent.message_id] = cleaned
                    else:
                        try:
                            await app.delete_messages(cq.message.chat.id, status.message_id)
                        except:
                            pass
                        chunks = split_text_into_chunks(cleaned, limit=4096)
                        last = None
                        for idx, chunk in enumerate(chunks):
                            if idx == 0:
                                last = await app.send_message(cq.message.chat.id, chunk, reply_to_message_id=cq.message.message_id)
                            else:
                                last = await app.send_message(cq.message.chat.id, chunk)
                        if last:
                            user_transcriptions.setdefault(str(chat_id), {})[last.message_id] = cleaned
                else:
                    try:
                        await app.edit_message_text(cleaned, cq.message.chat.id, status.message_id)
                        user_transcriptions.setdefault(str(chat_id), {})[status.message_id] = cleaned
                    except:
                        pass
            finally:
                try:
                    await cq.answer()
                except:
                    pass

        elif action == "summarize" and len(parts) >= 3:
            chat_id = parts[1]
            msg_id = int(parts[2])
            stored = user_transcriptions.get(str(chat_id), {}).get(msg_id)
            if not stored:
                await cq.answer("Summarize unavailable (maybe expired)", show_alert=True)
                return
            await cq.answer("Generating summary...")
            status = await app.send_message(cq.message.chat.id, "🔄 Processing...", reply_to_message_id=cq.message.message_id)
            try:
                lang = user_prefs.get(str(chat_id), {}).get("lang", "en")
                instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
                try:
                    summary = ask_gemini(stored, instruction)
                except:
                    summary = extract_key_points_offline(stored, max_points=6)
                if not summary:
                    try:
                        await app.edit_message_text("No Summary returned.", cq.message.chat.id, status.message_id)
                    except:
                        pass
                else:
                    try:
                        await app.edit_message_text(summary, cq.message.chat.id, status.message_id)
                    except:
                        pass
            finally:
                try:
                    await cq.answer()
                except:
                    pass

        elif action == "mode_menu" and len(parts) >= 3:
            chat_id = parts[1]
            msg_id = parts[2]
            kb = build_mode_keyboard(chat_id, msg_id)
            try:
                await app.answer_callback_query(cq.id)
            except:
                pass
            try:
                await app.edit_message_reply_markup(cq.message.chat.id, cq.message.message_id, reply_markup=kb)
            except:
                pass

        elif action == "set_mode" and len(parts) >= 4:
            chat_id = parts[1]
            msg_id = int(parts[2])
            mode = parts[3]
            prefs = user_prefs.setdefault(str(chat_id), {"lang": "en", "mode": "file"})
            prefs["mode"] = mode if mode in ("file", "split") else "file"
            try:
                await app.answer_callback_query(cq.id, text=f"Result mode set to {'file' if mode=='file' else 'split'}")
            except:
                pass

        else:
            await cq.answer("Unknown action", show_alert=True)
    except Exception as e:
        try:
            await cq.answer("Error processing action", show_alert=True)
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app.run()
