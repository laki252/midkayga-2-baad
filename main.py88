import os
import asyncio
import threading
import json
import requests
from flask import Flask, request
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatAction
import assemblyai as aai

flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "POST", "HEAD"])
def keep_alive():
    return "Bot is alive ✅", 200
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

API_ID = 29169428
API_HASH = "55742b16a85aac494c7944568b5507e5"
BOT_TOKEN = "7770743573:AAF9mwgq3efTrJ5iaXQu5VVfnFijUxPsAsg"
ASSEMBLYAI_API_KEY = "91f15c103dbd4b859466a29ee849e3ef"
GEMINI_API_KEY = "AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"
REQUEST_TIMEOUT_GEMINI = 300

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
memory_lock = threading.Lock()

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

def normalize_text_offline(text):
    import re
    return re.sub(r'\s+',' ',text).strip() if text else text

def ask_gemini(text, instruction, timeout=REQUEST_TIMEOUT_GEMINI):
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        raise RuntimeError("GEMINI_API_KEY not set. Cannot use Gemini features.")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload={"contents":[{"parts":[{"text":instruction},{"text":text}]}]}
    headers={"Content-Type":"application/json"}
    resp=requests.post(url,headers=headers,json=payload,timeout=timeout)
    resp.raise_for_status()
    result=resp.json()
    if "candidates" in result and isinstance(result["candidates"],list) and len(result["candidates"])>0:
        try: return result['candidates'][0]['content']['parts'][0]['text']
        except: return json.dumps(result['candidates'][0])
    raise RuntimeError(f"Gemini response lacks candidates: {json.dumps(result)}")

def build_action_keyboard(text, chat_id, message_id):
    include_summarize = len(text) > 1000 if text else False
    m = InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{chat_id}|{message_id}")
    ]])
    if include_summarize:
        m.inline_keyboard.append([
            InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{chat_id}|{message_id}")
        ])
    return m

def split_text_into_chunks(text, limit=4000):
    if not text: return []
    chunks=[]; start=0; n=len(text)
    while start<n:
        end=min(start+limit,n)
        if end<n:
            last_space=text.rfind(" ",start,end)
            if last_space>start: end=last_space
        chunk=text[start:end].strip()
        if not chunk:
            end=start+limit
            chunk=text[start:end].strip()
        chunks.append(chunk); start=end
    return chunks

async def send_transcript_output(client, chat_id, reply_msg_id, text, mode, original_msg_id):
    
    keyboard = build_action_keyboard(text, chat_id, reply_msg_id)
    
    if len(text) > 4000:
        if mode == "💬 Split messages":
            chunks = split_text_into_chunks(text, limit=4000)
            last_sent = None
            for part in chunks:
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                if last_sent is None:
                    last_sent = await client.send_message(chat_id, part, reply_to_message_id=original_msg_id)
                else:
                    last_sent = await client.send_message(chat_id, part)
            
            # Keydso kaliya farriinta u dambaysa oo wadata buttons
            with memory_lock:
                user_transcriptions.setdefault(chat_id, {})[last_sent.id] = text
                action_usage[f"{chat_id}|{last_sent.id}|clean_up"] = 0
                action_usage[f"{chat_id}|{last_sent.id}|get_key_points"] = 0
            
            if last_sent:
                new_keyboard = build_action_keyboard(text, chat_id, last_sent.id)
                await last_sent.edit_reply_markup(new_keyboard)
                
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{original_msg_id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            doc_msg = await client.send_document(chat_id, file_name, caption="Open this file and copy the text inside 👍", reply_to_message_id=original_msg_id, reply_markup=keyboard)
            os.remove(file_name)
            
            # Keydi ID-ga farriinta dukumiintiga
            with memory_lock:
                user_transcriptions.setdefault(chat_id, {})[doc_msg.id] = text
                action_usage[f"{chat_id}|{doc_msg.id}|clean_up"] = 0
                action_usage[f"{chat_id}|{doc_msg.id}|get_key_points"] = 0
    else:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        sent_msg = await client.send_message(chat_id, text, reply_to_message_id=original_msg_id, reply_markup=keyboard)
        
        # Keydi ID-ga farriinta qoraalka ah
        with memory_lock:
            user_transcriptions.setdefault(chat_id, {})[sent_msg.id] = text
            action_usage[f"{chat_id}|{sent_msg.id}|clean_up"] = 0
            action_usage[f"{chat_id}|{sent_msg.id}|get_key_points"] = 0


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
    await message.reply_text("Choose your **language**:", reply_markup=keyboard)

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
        await message.reply_text(f"Language set to: **{code}**")
        return
    if text in ["💬 Split messages", "📄 Text File"]:
        user_mode[uid] = text
        await message.reply_text(f"Output mode set to: **{text}**")
        return

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video | filters.document))
async def handle_media(client, message: Message):
    uid = message.from_user.id
    chat_id = message.chat.id
    lang = user_lang.get(uid, "en")
    mode = user_mode.get(uid, "📄 Text File")
    
    status_msg = await message.reply_text("🔄 Processing...")
    
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
        await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        await download_media(message, file_path)
    except Exception as e:
        await status_msg.edit_text(f"⚠️ Download error: {e}")
        return
    
    try:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_file, file_path, lang)
        
        if text.startswith("Error:"):
            raise Exception(text)
        
        corrected_text = normalize_text_offline(text)
        
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        await send_transcript_output(client, chat_id, status_msg.id, corrected_text, mode, message.id)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Transcription error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        try:
            await status_msg.delete()
        except:
            pass

@app.on_callback_query(filters.regex(r"get_key_points\|"))
async def get_key_points_callback(client, callback_query):
    data = callback_query.data.split("|")
    if len(data) != 3:
        await callback_query.answer("Invalid request", show_alert=True)
        return
    
    _, chat_id_part, msg_id_part = data
    chat_id = int(chat_id_part)
    msg_id = int(msg_id_part)
    user_id = callback_query.from_user.id
    
    usage_key = f"{chat_id}|{msg_id}|get_key_points"
    with memory_lock:
        usage = action_usage.get(usage_key, 0)
        if usage >= 1:
            await callback_query.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
            return
        action_usage[usage_key] = usage + 1
        stored = user_transcriptions.get(chat_id, {}).get(msg_id)
        
    if not stored:
        await callback_query.answer("Get Summarize unavailable (maybe expired)", show_alert=True)
        return
        
    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await callback_query.answer("Generating Summary...")
    status_msg = await client.send_message(chat_id, "🔄 Generating Summary...", reply_to_message_id=msg_id)
    
    try:
        lang = user_lang.get(user_id, "en")
        instruction = f"What is this report and what is it about? Please summarize them for me into (lang={lang}) without adding any introductions, notes, or extra phrases."
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, ask_gemini, stored, instruction)
    except Exception as e:
        summary = f"❌ Error generating summary: {e}"
        
    reply_to_id = callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else msg_id
    
    await status_msg.delete() 
    await client.send_message(chat_id, summary or "No Summary returned.", reply_to_message_id=reply_to_id)
    
@app.on_callback_query(filters.regex(r"clean_up\|"))
async def clean_up_callback(client, callback_query):
    data = callback_query.data.split("|")
    if len(data) != 3:
        await callback_query.answer("Invalid request", show_alert=True)
        return
    
    _, chat_id_part, msg_id_part = data
    chat_id = int(chat_id_part)
    msg_id = int(msg_id_part)
    user_id = callback_query.from_user.id
    
    usage_key = f"{chat_id}|{msg_id}|clean_up"
    with memory_lock:
        usage = action_usage.get(usage_key, 0)
        if usage >= 1:
            await callback_query.answer("Clean up unavailable (maybe expired)", show_alert=True)
            return
        action_usage[usage_key] = usage + 1
        stored = user_transcriptions.get(chat_id, {}).get(msg_id)
        
    if not stored:
        await callback_query.answer("Clean up unavailable (maybe expired)", show_alert=True)
        return
        
    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await callback_query.answer("Cleaning up Transcript...")
    status_msg = await client.send_message(chat_id, "🔄 Cleaning up Transcript...", reply_to_message_id=msg_id)
    
    try:
        lang = user_lang.get(user_id, "en")
        instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
        loop = asyncio.get_event_loop()
        cleaned = await loop.run_in_executor(None, ask_gemini, stored, instruction)
        
        if not cleaned:
            await status_msg.edit_text("No cleaned text returned.")
            return

        with memory_lock:
            user_mode_val = user_mode.get(user_id, "📄 Text File")

        await status_msg.delete()
        
        # Sidoo kale waa in aan u dirnaa farriinta cusub sidii jawaab
        reply_to_id = callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else msg_id

        # Halkan waxaa la dirayaa farriin cusub oo leh buttons cusub oo ku xiran ID-ga farriinta cusub
        await send_transcript_output(client, chat_id, reply_to_id, cleaned, user_mode_val, reply_to_id)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error cleaning up: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
