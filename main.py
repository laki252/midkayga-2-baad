import os
import asyncio
import threading
import json
import time
from flask import Flask, request
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatAction
import assemblyai as aai
import requests

# --- FLASK SETUP ---
flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200
def run_flask():
    # Use 0.0.0.0 for deployment, and port from environment or 8080
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- CONFIGURATION ---
API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7770743573:AAF9mwg3efTrJ5iaXQu5VVfnFijUxPsAsg"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"
GEMINI_API_KEY = "AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ" # Updated GEMINI key
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TIMEOUT = 300

aai.settings.api_key = ASSEMBLYAI_API_KEY

DOWNLOADS_DIR = "./downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# --- LANGUAGE CONFIG ---
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
user_transcriptions = {} # Store transcription text: {chat_id: {message_id: "text"}}
action_usage = {} # Track usage of Clean/Summarize: {"chat_id|message_id|action": count}

# --- UTILITY FUNCTIONS ---
def build_action_keyboard(message_id: int, text: str) -> InlineKeyboardMarkup:
    """Builds the inline keyboard for Clean and Summarize actions."""
    buttons = []
    # Clean transcript is always available
    buttons.append(InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{message_id}"))
    # Summarize is only available if text is long enough (e.g., > 1000 chars)
    if text and len(text) > 1000:
        buttons.append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{message_id}"))
    
    # Arrange in one row
    keyboard = InlineKeyboardMarkup([buttons])
    return keyboard

def split_text_into_chunks(text: str, limit: int = 4000) -> list:
    """Splits text into chunks respecting word boundaries for Telegram message limit."""
    if not text: return []
    chunks = []; start = 0; n = len(text)
    while start < n:
        end = min(start + limit, n)
        if end < n:
            last_space = text.rfind(" ", start, end)
            if last_space > start: end = last_space
        chunk = text[start:end].strip()
        if not chunk:
            end = start + limit
            chunk = text[start:end].strip()
        chunks.append(chunk); start = end
    return chunks

async def download_media(message: Message, file_path: str) -> str:
    """Asynchronously downloads media from a Pyrogram message."""
    await message.download(file_path)
    return file_path

def transcribe_file_sync(file_path: str, lang_code: str = "en") -> str:
    """Synchronous transcription using AssemblyAI."""
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcript = transcriber.transcribe(file_path, config)
    if transcript.error:
        raise Exception(f"Transcription Error: {transcript.error}")
    return transcript.text

def normalize_text_offline(text: str) -> str:
    """A simple offline text normalization (used as a fallback)."""
    import re
    return re.sub(r'\s+',' ',text).strip() if text else text

def extract_key_points_offline(text: str, max_points: int = 6) -> str:
    """A simple offline key point extraction (used as a fallback)."""
    if not text: return ""
    import re
    from collections import Counter
    sentences=[s.strip() for s in re.split(r'(?<=[\.\!\?])\s+',text) if s.strip()]
    if not sentences: return "\n".join(f"- {s}" for s in sentences[:max_points])
    words=[w for w in re.findall(r'\w+',text.lower()) if len(w)>3]
    if not words: return "\n".join(f"- {s}" for s in sentences[:max_points])
    freq=Counter(words)
    sentence_scores=[(sum(freq.get(w,0) for w in re.findall(r'\w+',s.lower())),s) for s in sentences]
    sentence_scores.sort(key=lambda x:x[0],reverse=True)
    top_sentences=sorted(sentence_scores[:max_points],key=lambda x:sentences.index(x[1]))
    return "\n".join(f"- {s}" for _,s in top_sentences)

def ask_gemini_sync(text: str, instruction: str) -> str:
    """Synchronous call to Gemini API for processing text."""
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY not set")
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[{"text":instruction},{"text":text}]}]}
        headers = {"Content-Type": "application/json"}
        
        # Use requests for synchronous call
        resp = requests.post(url, headers=headers, json=payload, timeout=GEMINI_TIMEOUT)
        resp.raise_for_status()
        result = resp.json()
        
        if "candidates" in result and isinstance(result["candidates"], list) and len(result["candidates"]) > 0:
            return result['candidates'][0]['content']['parts'][0]['text']
        
        raise RuntimeError(f"Gemini response lacks candidates or is incomplete: {json.dumps(result)}")
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {e}")

# --- BOT CLIENT ---
app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- HANDLERS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    buttons, row = [], []
    for i, label in enumerate(LABELS, 1):
        row.append(label)
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text("Choose your **language** for transcription:", reply_markup=keyboard)

@app.on_message(filters.command("mode") & filters.private)
async def choose_mode(client, message: Message):
    keyboard = ReplyKeyboardMarkup([["💬 Split messages", "📄 Text File"]], resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text("Choose **output mode**:", reply_markup=keyboard)

@app.on_message(filters.private & filters.text)
async def handle_text(client, message: Message):
    text = message.text
    uid = message.from_user.id
    if text in LABEL_TO_CODE:
        code = LABEL_TO_CODE[text]
        user_lang[uid] = code
        await message.reply_text(f"Language set to: **{text}** (`{code}`)")
        return
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        await message.reply_text(f"Output mode set to: **{text}**")
        return
    
    # Fallback/Help message
    await message.reply_text("Please use /start to set language, /mode to set output, or send an audio/video file to transcribe.")

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message: Message):
    uid = message.from_user.id
    chat_id = message.chat.id
    lang = user_lang.get(uid, "en")
    mode = user_mode.get(uid, "📄 Text File")
    
    # 1. Download Media
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    ext = ""
    if message.audio:
        ext = os.path.splitext(message.audio.file_name or "")[1] or ".mp3"
    elif message.voice:
        ext = ".ogg"
    elif message.video:
        ext = os.path.splitext(message.video.file_name or "")[1] or ".mp4"
    elif message.document:
        ext = os.path.splitext(message.document.file_name or "")[1] or ""
        mime = message.document.mime_type or ""
        if not any(e in ext.lower() for e in [".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".mp4", ".mkv", ".avi"]) and not any(m in mime for m in ["audio", "video"]):
            await message.reply_text("⚠️ Unsupported file type. Please send an audio or video file.")
            return

    file_path = os.path.join(DOWNLOADS_DIR, f"{message.id}{ext}")
    
    try:
        await download_media(message, file_path)
    except Exception as e:
        await message.reply_text(f"⚠️ Download error: {e}")
        return
    
    # 2. Transcribe
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    
    try:
        loop = asyncio.get_event_loop()
        # Use sync function in a thread pool executor
        text = await loop.run_in_executor(None, transcribe_file_sync, file_path, lang)
    except Exception as e:
        await message.reply_text(f"❌ Transcription error: {e}")
        return
    finally:
        # 3. Cleanup: Remove local file
        if os.path.exists(file_path):
            os.remove(file_path)
            
    # 4. Handle Result Delivery
    reply_msg_id = message.id
    sent_msg = None
    
    if len(text) > 4000:
        if mode == "💬 Split messages":
            chunks = split_text_into_chunks(text, limit=4000)
            for part in chunks:
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                if part == chunks[0]:
                    sent_msg = await message.reply_text(part, reply_to_message_id=reply_msg_id)
                else:
                    sent_msg = await client.send_message(chat_id, part)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{message.id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            sent_msg = await message.reply_document(
                file_name, 
                caption="Open this file and copy the text inside 👍", 
                reply_to_message_id=reply_msg_id
            )
            os.remove(file_name)
    else:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        sent_msg = await message.reply_text(text, reply_to_message_id=reply_msg_id)

    # 5. Store Transcription and Add Buttons
    if sent_msg:
        # Store transcription in memory
        user_transcriptions.setdefault(chat_id, {})[sent_msg.id] = text
        # Add action buttons
        keyboard = build_action_keyboard(sent_msg.id, text)
        await sent_msg.edit_reply_markup(keyboard)

# --- CALLBACK HANDLERS FOR CLEAN/SUMMARIZE ---

@app.on_callback_query(filters.regex(r"clean_up\|\d+"))
async def clean_up_callback(client, callback_query):
    parts = callback_query.data.split("|")
    message_id = int(parts[1])
    chat_id = callback_query.message.chat.id
    uid = callback_query.from_user.id
    
    # 1. Check/Restrict Usage (simple in-memory check)
    usage_key = f"{chat_id}|{message_id}|clean_up"
    usage = action_usage.get(usage_key, 0)
    
    if usage >= 1:
        await callback_query.answer("Clean up only available once per message.", show_alert=True)
        return
    
    # 2. Retrieve Stored Text
    stored_text = user_transcriptions.get(chat_id, {}).get(message_id)
    if not stored_text:
        await callback_query.answer("Clean up unavailable (maybe expired or not found).", show_alert=True)
        return

    await callback_query.answer("Cleaning up...")
    
    # 3. Send/Update Status Message
    original_reply_id = callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else message_id
    status_msg = await client.send_message(chat_id, "🔄 Processing Clean Up...", reply_to_message_id=original_reply_id)
    
    try:
        # 4. Gemini/Offline Processing
        lang = user_lang.get(uid, "en")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        
        loop = asyncio.get_event_loop()
        try:
            # Run sync function in a thread pool executor
            cleaned_text = await loop.run_in_executor(None, ask_gemini_sync, stored_text, instruction)
        except Exception:
            # Fallback to offline normalization
            cleaned_text = normalize_text_offline(stored_text)
            
        if not cleaned_text:
            await client.edit_message_text(chat_id, status_msg.id, "❌ No cleaned text returned.")
            return

        # 5. Handle Result Delivery (Same logic as handle_media)
        user_mode_setting = user_mode.get(uid, "📄 Text File")
        sent_msg = None
        
        # Increment usage counter
        action_usage[usage_key] = usage + 1
        
        if len(cleaned_text) > 4000:
            await client.delete_messages(chat_id, status_msg.id)
            if user_mode_setting == "💬 Split messages":
                chunks = split_text_into_chunks(cleaned_text, limit=4000)
                for part in chunks:
                    if part == chunks[0]:
                        sent_msg = await client.send_message(chat_id, part, reply_to_message_id=original_reply_id)
                    else:
                        sent_msg = await client.send_message(chat_id, part)
            else:
                file_name = os.path.join(DOWNLOADS_DIR, f"cleaned_{message_id}.txt")
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(cleaned_text)
                await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
                sent_msg = await client.send_document(
                    chat_id, 
                    file_name, 
                    caption="Cleaned Transcript 👍", 
                    reply_to_message_id=original_reply_id
                )
                os.remove(file_name)
        else:
            await client.edit_message_text(chat_id, status_msg.id, cleaned_text)
            sent_msg = status_msg # Use the status message as the final message
            
        # 6. Store New Text and Add Buttons to New Message
        if sent_msg:
            user_transcriptions.setdefault(chat_id, {})[sent_msg.id] = cleaned_text
            new_keyboard = build_action_keyboard(sent_msg.id, cleaned_text)
            await sent_msg.edit_reply_markup(new_keyboard)
            
            # Reset actions for the new message
            action_usage[f"{chat_id}|{sent_msg.id}|clean_up"] = 0
            action_usage[f"{chat_id}|{sent_msg.id}|get_key_points"] = 0

    except Exception as e:
        await client.edit_message_text(chat_id, status_msg.id, f"❌ An error occurred during clean-up: {e}")

@app.on_callback_query(filters.regex(r"get_key_points\|\d+"))
async def get_key_points_callback(client, callback_query):
    parts = callback_query.data.split("|")
    message_id = int(parts[1])
    chat_id = callback_query.message.chat.id
    uid = callback_query.from_user.id
    
    # 1. Check/Restrict Usage
    usage_key = f"{chat_id}|{message_id}|get_key_points"
    usage = action_usage.get(usage_key, 0)
    
    if usage >= 1:
        await callback_query.answer("Get Summarize only available once per message.", show_alert=True)
        return
        
    # 2. Retrieve Stored Text
    stored_text = user_transcriptions.get(chat_id, {}).get(message_id)
    if not stored_text:
        await callback_query.answer("Summarize unavailable (maybe expired or not found).", show_alert=True)
        return
    if len(stored_text) <= 1000:
        await callback_query.answer("Text is too short to summarize.", show_alert=True)
        return
        
    await callback_query.answer("Generating Summary...")
    
    # 3. Send Status Message
    original_reply_id = callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else message_id
    status_msg = await client.send_message(chat_id, "🔄 Processing Summarize...", reply_to_message_id=original_reply_id)
    
    try:
        # 4. Gemini/Offline Processing
        lang = user_lang.get(uid, "en")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        
        loop = asyncio.get_event_loop()
        try:
            # Run sync function in a thread pool executor
            summary = await loop.run_in_executor(None, ask_gemini_sync, stored_text, instruction)
        except Exception:
            # Fallback to offline extraction
            summary = extract_key_points_offline(stored_text, max_points=6)
            
        if not summary:
            await client.edit_message_text(chat_id, status_msg.id, "❌ No Summary returned.")
            return
            
        # 5. Display Result
        action_usage[usage_key] = usage + 1 # Increment usage counter
        await client.edit_message_text(chat_id, status_msg.id, f"**Summary:**\n{summary}")
        
        # Remove buttons from the original message if it's the one we're processing
        # Note: We don't add new buttons to the summary message, as it's a derived result.
        # We also don't remove buttons from the *original* transcription message, as that's often in a different format.
        
    except Exception as e:
        await client.edit_message_text(chat_id, status_msg.id, f"❌ An error occurred during summarization: {e}")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Start the Flask web server in a separate thread
    threading.Thread(target=run_flask).start()
    # Start the Pyrogram bot client (blocking call)
    app.run()
