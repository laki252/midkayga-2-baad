import os
import io
import re
import time
import json
import asyncio
import threading
import requests
from flask import Flask, request
from collections import Counter
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatAction
import assemblyai as aai

flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = int(os.environ.get("API_ID", "29169428"))
API_HASH = os.environ.get("API_HASH", "55742b16a85aac494c7944568b5507e5")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7770743573:AAF9mwgq3efTrJ5iaXQu5VVfnFijUxPsAsg")
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "91f15c103dbd4b859466a29ee849e3ef")
GEMINI_API_KEYS = "AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"

aai.settings.api_key = ASSEMBLYAI_API_KEY

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

_LANGS_RAW = "🇬🇧 English:en,🇸🇦 العربية:ar,🇪🇸 Español:es,🇫🇷 Français:fr,🇷🇺 Русский:ru,🇩🇪 Deutsch:de,🇮🇳 हिन्दी:hi,🇮🇷 فارسی:fa,🇮🇩 Indonesia:id,🇺🇦 Українська:uk,🇦🇿 Azərbaycan:az,🇮🇹 Italiano:it,🇹🇷 Türkçe:tr,🇧🇬 Български:bg,🇷🇸 Srpski:sr,🇵🇰 اردو:ur,🇹🇭 ไทย:th,🇻🇳 Tiếng Việt:vi,🇯🇵 日本語:ja,🇰🇷 한국어:ko,🇨🇳 中文:zh,🇳🇱 Nederlands:nl,🇸🇪 Svenska:sv,🇳🇴 Norsk:no,🇮🇱 עברית:he,🇩🇰 Dansk:da,🇪🇹 አማርኛ:am,🇫🇮 Suomi:fi,🇧🇩 বাংলা:bn,🇰🇪 Kiswahili:sw,🇪🇹 Oromoo:om,🇳🇵 नेपाली:ne,🇵🇱 Polski:pl,🇬🇷 Ελληνικά:el,🇨🇿 Čeština:cs,🇮🇸 Íslenska:is,🇱🇹 Lietuvių:lt,🇱🇻 Latviešu:lv,🇭🇷 Hrvatski:hr,🇷🇸 Bosanski:bs,🇭🇺 Magyar:hu,🇷🇴 Română:ro,🇸🇴 Somali:so,🇲🇾 Melayu:ms,🇺🇿 O'zbekcha:uz,🇵🇭 Tagalog:tl,🇵🇹 Português:pt"
LANGS = [(p.split(":",1)[0].strip(), p.split(":",1)[1].strip()) for p in _LANGS_RAW.split(",")]
LABELS = [label for label, code in LANGS]
LABEL_TO_CODE = {label: code for label, code in LANGS}

user_lang = {}
user_mode = {}

user_transcriptions = {}
action_usage = {}
data_lock = threading.Lock()

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def download_media(message: Message, file_path: str) -> str:
    await message.download(file_path)
    return file_path

def transcribe_file(file_path: str, lang_code: str = "en") -> str:
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcript = transcriber.transcribe(file_path, config)
    if getattr(transcript, "error", None):
        return f"Error: {transcript.error}"
    return getattr(transcript, "text", "")

def normalize_text_offline(text):
    if not text:
        return text
    t = re.sub(r'\[.*?\]', ' ', text)
    t = re.sub(r'\buh\b|\bum\b|\bmm\b|\buhm\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'\s([?.!,;:])', r'\1', t)
    return t

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

def ask_gemini(text, instruction, timeout=300):
    if not GEMINI_API_KEYS:
        raise RuntimeError("GEMINI_API_KEYS not set")
    last_exception = None
    for api_key in GEMINI_API_KEYS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {"contents":[{"parts":[{"text":instruction},{"text":text}]}]}
            headers = {"Content-Type":"application/json"}
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()
            if "candidates" in result and isinstance(result["candidates"], list) and len(result["candidates"])>0:
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except:
                    return json.dumps(result['candidates'][0])
            raise RuntimeError("Gemini response lacks candidates")
        except Exception as e:
            last_exception = e
            continue
    raise RuntimeError(f"All Gemini API keys failed. Last error: {str(last_exception)}")

def build_lang_keyboard():
    buttons, row = [], []
    for i, label in enumerate(LABELS, 1):
        row.append(label)
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    keyboard = build_lang_keyboard()
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=lbl, callback_data=f"set_lang|{LABEL_TO_CODE[lbl]}")] for row in keyboard for lbl in row])
    await message.reply_text("Choose your language:", reply_markup=reply_markup)

@app.on_message(filters.command("mode") & filters.private)
async def choose_mode(client, message: Message):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Split messages", callback_data="set_mode|split"), InlineKeyboardButton("📄 Text File", callback_data="set_mode|file")]])
    await message.reply_text("Choose output mode:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^set_lang\|"))
async def set_lang_cb(client, callback):
    try:
        _, code = callback.data.split("|", 1)
        uid = callback.from_user.id
        user_lang[uid] = code
        await callback.answer(f"Language set to {code}")
    except:
        await callback.answer("Error")

@app.on_callback_query(filters.regex(r"^set_mode\|"))
async def set_mode_cb(client, callback):
    try:
        _, mode = callback.data.split("|", 1)
        uid = callback.from_user.id
        user_mode[uid] = "💬 Split messages" if mode == "split" else "📄 Text File"
        await callback.answer(f"Mode set to {user_mode[uid]}")
    except:
        await callback.answer("Error")

async def run_blocking(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)

def attach_action_buttons_py(client, chat_id, message_id, text):
    buttons = []
    buttons.append([InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{chat_id}|{message_id}")])
    if len(text) > 1000:
        buttons[0].append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{chat_id}|{message_id}"))
    markup = InlineKeyboardMarkup(buttons)
    try:
        asyncio.get_event_loop().create_task(client.edit_message_reply_markup(chat_id, message_id, reply_markup=markup))
    except Exception:
        pass
    with data_lock:
        action_usage[f"{chat_id}|{message_id}|clean_up"] = 0
        action_usage[f"{chat_id}|{message_id}|get_key_points"] = 0

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
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
        text = await run_blocking(transcribe_file, file_path, lang)
    except Exception as e:
        await message.reply_text(f"❌ Transcription error: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
    corrected_text = normalize_text_offline(text)
    reply_msg = None
    if len(corrected_text) > 4000:
        if mode == "💬 Split messages":
            parts = [corrected_text[i:i+4000] for i in range(0, len(corrected_text), 4000)]
            last = None
            for part in parts:
                last = await message.reply_text(part, reply_to_message_id=message.id)
            reply_msg = last
        else:
            file_name = f"transcript_{message.id}.txt"
            bio = io.BytesIO(corrected_text.encode("utf-8"))
            bio.name = file_name
            sent = await client.send_document(message.chat.id, bio, caption="Open this file and copy the text inside 👍", reply_to_message_id=message.id)
            reply_msg = sent
    else:
        reply_msg = await message.reply_text(corrected_text or "⚠️ Warning Make sure the voice is clear or speaking in the language you chose.", reply_to_message_id=message.id)
    if reply_msg:
        with data_lock:
            user_transcriptions.setdefault(str(reply_msg.chat.id), {})[reply_msg.message_id] = corrected_text
        attach_action_buttons_py(app, reply_msg.chat.id, reply_msg.message_id, corrected_text)

@app.on_callback_query(filters.regex(r"^get_key_points\|"))
async def get_key_points_cb(client, callback):
    parts = callback.data.split("|")
    if len(parts) == 3:
        _, chat_id_part, msg_id_part = parts
    else:
        await callback.answer("Invalid request", show_alert=True)
        return
    try:
        chat_id_val = int(chat_id_part)
        msg_id = int(msg_id_part)
    except:
        await callback.answer("Invalid ids", show_alert=True)
        return
    usage_key = f"{chat_id_val}|{msg_id}|get_key_points"
    with data_lock:
        usage = action_usage.get(usage_key, 0)
        if usage >= 1:
            await callback.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
            return
        action_usage[usage_key] = usage + 1
        stored = user_transcriptions.get(str(chat_id_val), {}).get(msg_id)
    if not stored:
        await callback.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
        return
    await callback.answer("Generating...")
    status = await client.send_message(callback.message.chat.id, "🔄 Processing...", reply_to_message_id=callback.message.message_id)
    try:
        lang = user_lang.get(chat_id_val, "en")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        try:
            summary = await run_blocking(ask_gemini, stored, instruction)
        except Exception:
            summary = extract_key_points_offline(stored, max_points=6)
        if not summary:
            await client.edit_message_text(callback.message.chat.id, "No Summary returned.", message_id=status.message_id)
        else:
            await client.edit_message_text(callback.message.chat.id, summary, message_id=status.message_id)
    except Exception:
        await client.edit_message_text(callback.message.chat.id, "Error generating summary.", message_id=status.message_id)

@app.on_callback_query(filters.regex(r"^clean_up\|"))
async def clean_up_cb(client, callback):
    parts = callback.data.split("|")
    if len(parts) == 3:
        _, chat_id_part, msg_id_part = parts
    else:
        await callback.answer("Invalid request", show_alert=True)
        return
    try:
        chat_id_val = int(chat_id_part)
        msg_id = int(msg_id_part)
    except:
        await callback.answer("Invalid ids", show_alert=True)
        return
    usage_key = f"{chat_id_val}|{msg_id}|clean_up"
    with data_lock:
        usage = action_usage.get(usage_key, 0)
        if usage >= 1:
            await callback.answer("Clean up unavailable (maybe expired)", show_alert=True)
            return
        action_usage[usage_key] = usage + 1
        stored = user_transcriptions.get(str(chat_id_val), {}).get(msg_id)
    if not stored:
        await callback.answer("Clean up unavailable (maybe expired)", show_alert=True)
        return
    await callback.answer("Cleaning up...")
    status = await client.send_message(callback.message.chat.id, "🔄 Processing...", reply_to_message_id=callback.message.message_id)
    try:
        lang = user_lang.get(chat_id_val, "en")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        try:
            cleaned = await run_blocking(ask_gemini, stored, instruction)
        except Exception:
            cleaned = normalize_text_offline(stored)
        if not cleaned:
            await client.edit_message_text(callback.message.chat.id, "No cleaned text returned.", message_id=status.message_id)
            return
        user_mode_val = user_mode.get(chat_id_val, "📄 Text File")
        if len(cleaned) > 4000:
            if user_mode_val == "📄 Text File":
                bio = io.BytesIO(cleaned.encode("utf-8"))
                bio.name = "cleaned.txt"
                try:
                    await status.delete()
                except:
                    pass
                sent = await client.send_document(callback.message.chat.id, bio, reply_to_message_id=callback.message.message_id)
                with data_lock:
                    user_transcriptions.setdefault(str(callback.message.chat.id), {})[sent.message_id] = cleaned
                    action_usage[f"{callback.message.chat.id}|{sent.message_id}|clean_up"] = 0
                    action_usage[f"{callback.message.chat.id}|{sent.message_id}|get_key_points"] = 0
            else:
                try:
                    await status.delete()
                except:
                    pass
                chunks = [cleaned[i:i+4000] for i in range(0, len(cleaned), 4000)]
                last = None
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        last = await client.send_message(callback.message.chat.id, chunk, reply_to_message_id=callback.message.message_id)
                    else:
                        last = await client.send_message(callback.message.chat.id, chunk)
                with data_lock:
                    user_transcriptions.setdefault(str(callback.message.chat.id), {})[last.message_id] = cleaned
                    action_usage[f"{callback.message.chat.id}|{last.message_id}|clean_up"] = 0
                    action_usage[f"{callback.message.chat.id}|{last.message_id}|get_key_points"] = 0
        else:
            try:
                await client.edit_message_text(callback.message.chat.id, cleaned, message_id=status.message_id)
                with data_lock:
                    user_transcriptions.setdefault(str(callback.message.chat.id), {})[status.message_id] = cleaned
                    action_usage[f"{callback.message.chat.id}|{status.message_id}|clean_up"] = 0
                    action_usage[f"{callback.message.chat.id}|{status.message_id}|get_key_points"] = 0
            except:
                pass
    except Exception:
        try:
            await client.edit_message_text(callback.message.chat.id, "Error cleaning text.", message_id=status.message_id)
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
