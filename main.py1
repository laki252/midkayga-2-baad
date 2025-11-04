import os
import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import assemblyai as aai
import requests
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
GEMINI_API_KEY = "AIzaSyD0sYw4zzlXhbSV3HLY9wM4zCqX8ytR8zQ"

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

app = Client("media_transcriber", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def download_media(message: Message, file_path: str) -> str:
    await message.download(file_path)
    return file_path

def transcribe_file(file_path: str) -> str:
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(file_path)
    if transcript.error:
        return f"Error: {transcript.error}"
    return transcript.text

def ask_gemini(text, instruction):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents":[{"parts":[{"text":instruction},{"text":text}]}]}
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    if "candidates" in result and len(result["candidates"]) > 0:
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except:
            return str(result['candidates'][0])
    return ""

def normalize_text_offline(text):
    import re
    return re.sub(r'\s+', ' ', text).strip() if text else text

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
    user_transcriptions[uid] = text
    buttons = [
        [InlineKeyboardButton("🧹 Clean transcript", callback_data=f"clean|{uid}"),
         InlineKeyboardButton("🧾 Summarize", callback_data=f"summarize|{uid}")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    if len(text) > 4000:
        if mode == "💬 Split messages":
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.reply_text(part, reply_to_message_id=message.id)
            await message.reply_text("Actions:", reply_markup=markup)
        else:
            file_name = os.path.join(DOWNLOADS_DIR, f"transcript_{message.id}.txt")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            await message.reply_document(file_name, caption="Transcription saved as .txt file", reply_to_message_id=message.id)
            await message.reply_text("Actions:", reply_markup=markup)
            os.remove(file_name)
    else:
        await message.reply_text(f"{text}\n\nPowered by @MediaToTextBot", reply_to_message_id=message.id, reply_markup=markup)

@app.on_callback_query()
async def callbacks(client, callback):
    data = callback.data
    uid = int(data.split("|")[1])
    text = user_transcriptions.get(uid, "")
    if not text:
        await callback.answer("Text expired or unavailable", show_alert=True)
        return
    await callback.answer()
    if data.startswith("clean"):
        instruction = f"Clean and normalize this transcription (lang={user_lang.get(uid,'en')}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language."
        try:
            cleaned = ask_gemini(text, instruction)
        except:
            cleaned = normalize_text_offline(text)
        await callback.message.reply_text(cleaned or "No cleaned text returned.")
    elif data.startswith("summarize"):
        instruction = f"Summarize this text (lang={user_lang.get(uid,'en')}) into key points without introductions or extra phrases."
        try:
            summary = ask_gemini(text, instruction)
        except:
            import re
            sentences = [s.strip() for s in re.split(r'(?<=[\.\!\?])\s+', text) if s.strip()]
            freq = {}
            for word in re.findall(r'\w+', text.lower()):
                if len(word) > 3:
                    freq[word] = freq.get(word, 0) + 1
            sentence_scores = [(sum(freq.get(w,0) for w in re.findall(r'\w+', s.lower())), s) for s in sentences]
            sentence_scores.sort(key=lambda x: x[0], reverse=True)
            top_sentences = [s for _,s in sentence_scores[:6]]
            summary = "\n".join(f"- {s}" for s in top_sentences)
        await callback.message.reply_text(summary or "No summary returned.")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    app.run()
