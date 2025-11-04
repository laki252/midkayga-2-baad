import os
import asyncio
import threading
import io
import re
import time
from collections import Counter
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import assemblyai as aai
from flask import Flask, request

# -------------------- Keep-alive Flask --------------------
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# -------------------- Config (same values from your code1) --------------------
API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7920977306:AAHhFpv2ImMsiowjpm288ebRdxAjoJZwWec"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"

aai.settings.api_key = ASSEMBLYAI_API_KEY

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# -------------------- Languages --------------------
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

# -------------------- In-memory stores --------------------
user_lang = {}                   # user_id -> lang code
user_send_mode = {}              # user_id -> "file" or "split" (default file)
user_transcriptions = {}         # chat_id -> {message_id: text}
action_usage = {}                # "chat|msg|action" -> int (usage count)

# -------------------- Pyrogram app --------------------
app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------- Utilities --------------------
async def download_media(message: Message, file_path: str) -> str:
    await message.download(file_path)
    return file_path

def transcribe_file(file_path: str) -> str:
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(file_path)
    if transcript.error:
        return f"Error: {transcript.error}"
    return transcript.text

def normalize_text_offline(text: str) -> str:
    if not text:
        return text
    # Basic cleanup: collapse whitespace, remove common ASR artifacts
    t = re.sub(r'\[.*?\]', ' ', text)  # remove bracketed tokens
    t = re.sub(r'\s+', ' ', t).strip()
    # Fix spaced punctuation issues (basic)
    t = re.sub(r'\s+([,\.!?;:])', r'\1', t)
    return t

def extract_key_points_offline(text: str, max_points: int = 6) -> str:
    if not text:
        return ""
    # split into sentences
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

def split_text_into_chunks(text: str, limit: int = 4096):
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

def build_lang_keyboard():
    buttons = []
    row = []
    for i, (label, code) in enumerate(LANGS, 1):
        row.append(label)
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

def build_result_mode_keyboard_inline():
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 .txt file", callback_data="result_mode|file"),
         InlineKeyboardButton("💬 Split messages", callback_data="result_mode|split")]
    ])
    return kb

def attach_action_buttons_to_message(text: str, chat_id: int, message_id: int):
    """
    Attach inline buttons to a message (clean & summarize). We set usage counters.
    """
    try:
        include_summarize = len(text) > 1000 if text else False
        buttons = []
        buttons.append([InlineKeyboardButton("⭐️ Clean transcript", callback_data=f"clean_up|{chat_id}|{message_id}")])
        if include_summarize:
            buttons.append([InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{chat_id}|{message_id}")])
        kb = InlineKeyboardMarkup(buttons)
        # edit reply markup (async)
        asyncio.create_task(app.edit_message_reply_markup(chat_id, message_id, reply_markup=kb))
        # init usage counters
        action_usage[f"{chat_id}|{message_id}|clean_up"] = 0
        action_usage[f"{chat_id}|{message_id}|get_key_points"] = 0
    except Exception:
        pass

def get_user_send_mode(uid: int) -> str:
    return user_send_mode.get(str(uid), "file")

def set_user_send_mode(uid: int, mode: str):
    if mode not in ("file", "split"):
        mode = "file"
    user_send_mode[str(uid)] = mode

def delete_transcription_later(user_id: str, message_id: int, delay: int = 86400):
    # run in background thread
    time.sleep(delay)
    try:
        if user_id in user_transcriptions and message_id in user_transcriptions[user_id]:
            del user_transcriptions[user_id][message_id]
    except Exception:
        pass

# -------------------- Bot handlers --------------------
@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    keyboard = build_lang_keyboard()
    await message.reply_text("Choose your language from the keyboard below", reply_markup=keyboard)

@app.on_message(filters.private & filters.text)
async def set_language(client, message: Message):
    text = message.text
    uid = message.from_user.id
    if text in LABEL_TO_CODE:
        code = LABEL_TO_CODE[text]
        user_lang[uid] = code
        await message.reply_text(f"Language set to {code}")
        return
    # keep /mode command hint
    if text and text.strip().lower() == "/mode":
        kb = build_result_mode_keyboard_inline()
        await message.reply_text("Choose result delivery mode:", reply_markup=kb)
        return

@app.on_message(filters.private & filters.command("mode"))
async def show_mode_cmd(client, message: Message):
    kb = build_result_mode_keyboard_inline()
    await message.reply_text("Choose result delivery mode:", reply_markup=kb)

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message: Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "en")
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

    status_msg = await message.reply_text("Transcribing... please wait.")
    try:
        loop = asyncio.get_event_loop()
        # Use thread executor for blocking transcribe
        text = await loop.run_in_executor(None, transcribe_file, file_path)
    except Exception as e:
        await status_msg.edit_text(f"Transcription error: {e}")
        try:
            os.remove(file_path)
        except:
            pass
        return

    corrected_text = normalize_text_offline(text)
    # send result according to user mode (file/split)
    try:
        uid_key = str(message.chat.id)
        send_mode = get_user_send_mode(uid)
        sent_msg = None
        if len(corrected_text) > 4000:
            if send_mode == "file":
                bio = io.BytesIO(corrected_text.encode("utf-8"))
                bio.name = "Transcript.txt"
                sent = await client.send_document(message.chat.id, bio, reply_to_message_id=message.message_id)
                sent_msg = sent
                # store transcription
                user_transcriptions.setdefault(uid_key, {})[sent.message_id] = corrected_text
                threading.Thread(target=delete_transcription_later, args=(uid_key, sent.message_id), daemon=True).start()
            else:
                chunks = split_text_into_chunks(corrected_text, limit=4096)
                last_sent = None
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        last_sent = await client.send_message(message.chat.id, chunk, reply_to_message_id=message.message_id)
                    else:
                        last_sent = await client.send_message(message.chat.id, chunk)
                sent_msg = last_sent
                if last_sent:
                    user_transcriptions.setdefault(uid_key, {})[last_sent.message_id] = corrected_text
                    threading.Thread(target=delete_transcription_later, args=(uid_key, last_sent.message_id), daemon=True).start()
        else:
            sent_msg = await client.send_message(message.chat.id, corrected_text or "⚠️ Warning: Make sure the voice is clear or speaking in the chosen language.", reply_to_message_id=message.message_id)
            if sent_msg:
                user_transcriptions.setdefault(uid_key, {})[sent_msg.message_id] = corrected_text
                threading.Thread(target=delete_transcription_later, args=(uid_key, sent_msg.message_id), daemon=True).start()

        # attach action buttons to the message (clean / summarize)
        if sent_msg:
            attach_action_buttons_to_message(corrected_text, sent_msg.chat.id, sent_msg.message_id)

    except Exception as e:
        await status_msg.edit_text(f"Error sending transcript: {e}")
    finally:
        try:
            await status_msg.delete()
        except:
            pass
        try:
            os.remove(file_path)
        except:
            pass

# -------------------- Callback query handler (buttons) --------------------
@app.on_callback_query()
async def callback_router(client: Client, query: CallbackQuery):
    data = query.data or ""
    # result_mode selection
    if data.startswith("result_mode|"):
        try:
            _, mode = data.split("|", 1)
            uid = query.from_user.id
            set_user_send_mode(uid, mode)
            mode_text = "📄 .txt file" if mode == "file" else "💬 Split messages"
            try:
                await query.message.delete()
            except:
                pass
            await query.answer(f"✅ Result mode set: {mode_text}")
        except Exception:
            await query.answer("Error setting result mode", show_alert=True)
        return

    # clean_up or get_key_points
    if data.startswith("clean_up|") or data.startswith("get_key_points|"):
        parts = data.split("|")
        if len(parts) == 3:
            action, chat_part, msg_part = parts
        elif len(parts) == 2:
            action, msg_part = parts
            chat_part = str(query.message.chat.id)
        else:
            await query.answer("Invalid request", show_alert=True)
            return

        try:
            chat_id_val = int(chat_part)
            msg_id = int(msg_part)
        except:
            await query.answer("Invalid message id", show_alert=True)
            return

        usage_key = f"{chat_id_val}|{msg_id}|{action}"
        usage = action_usage.get(usage_key, 0)
        if usage >= 1:
            await query.answer(f"{'Clean up' if action=='clean_up' else 'Get Summarize'} unavailable (maybe expired)", show_alert=True)
            return
        action_usage[usage_key] = usage + 1

        # fetch stored transcription
        stored = user_transcriptions.get(str(chat_id_val), {}).get(msg_id)
        if not stored:
            await query.answer("Unavailable (maybe expired)", show_alert=True)
            return

        await query.answer("Processing...")
        status = await client.send_message(query.message.chat.id, "🔄 Processing...", reply_to_message_id=query.message.message_id)
        try:
            if action == "get_key_points":
                # try external LLM here if you want; fallback to offline
                summary = extract_key_points_offline(stored, max_points=6)
                if not summary:
                    summary = "No summary could be generated."
                # edit status message to summary
                try:
                    await client.edit_message_text(query.message.chat.id, status.message_id, summary)
                except:
                    await client.send_message(query.message.chat.id, summary)
            else:  # clean_up
                cleaned = normalize_text_offline(stored)
                if not cleaned:
                    cleaned = "No cleaned text returned."
                # send according to user's result mode
                uid_key = str(chat_id_val)
                # get the requester's stored mode (use the caller's preference)
                caller_mode = get_user_send_mode(query.from_user.id)
                if len(cleaned) > 4000:
                    if caller_mode == "file":
                        bio = io.BytesIO(cleaned.encode("utf-8"))
                        bio.name = "cleaned.txt"
                        try:
                            await status.delete()
                        except:
                            pass
                        sent = await client.send_document(query.message.chat.id, bio, reply_to_message_id=query.message.message_id)
                        user_transcriptions.setdefault(uid_key, {})[sent.message_id] = cleaned
                        threading.Thread(target=delete_transcription_later, args=(uid_key, sent.message_id), daemon=True).start()
                        attach_action_buttons_to_message(cleaned, sent.chat.id, sent.message_id)
                    else:
                        try:
                            await status.delete()
                        except:
                            pass
                        chunks = split_text_into_chunks(cleaned, limit=4096)
                        last_sent = None
                        for idx, chunk in enumerate(chunks):
                            if idx == 0:
                                last_sent = await client.send_message(query.message.chat.id, chunk, reply_to_message_id=query.message.message_id)
                            else:
                                last_sent = await client.send_message(query.message.chat.id, chunk)
                        if last_sent:
                            user_transcriptions.setdefault(uid_key, {})[last_sent.message_id] = cleaned
                            threading.Thread(target=delete_transcription_later, args=(uid_key, last_sent.message_id), daemon=True).start()
                            attach_action_buttons_to_message(cleaned, last_sent.chat.id, last_sent.message_id)
                else:
                    try:
                        await client.edit_message_text(query.message.chat.id, status.message_id, cleaned)
                        user_transcriptions.setdefault(uid_key, {})[status.message_id] = cleaned
                        threading.Thread(target=delete_transcription_later, args=(uid_key, status.message_id), daemon=True).start()
                        attach_action_buttons_to_message(cleaned, status.chat.id, status.message_id)
                    except Exception:
                        # fallback: send new message
                        sent = await client.send_message(query.message.chat.id, cleaned, reply_to_message_id=query.message.message_id)
                        if sent:
                            user_transcriptions.setdefault(uid_key, {})[sent.message_id] = cleaned
                            threading.Thread(target=delete_transcription_later, args=(uid_key, sent.message_id), daemon=True).start()
                            attach_action_buttons_to_message(cleaned, sent.chat.id, sent.message_id)

        except Exception as e:
            try:
                await client.edit_message_text(query.message.chat.id, status.message_id, f"Error: {e}")
            except:
                pass
        finally:
            # no matter what, ensure status removed if still there (when replaced by edit we may ignore)
            try:
                await status.delete()
            except:
                pass

# -------------------- Run --------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app.run()
