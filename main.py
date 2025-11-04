import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup
import assemblyai as aai

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

@app.on_message(filters.private & filters.text)
async def set_language(client, message: Message):
    text = message.text
    uid = message.from_user.id
    if text in LABEL_TO_CODE:
        code = LABEL_TO_CODE[text]
        user_lang[uid] = code
        await message.reply_text(f"Language set to {code}")
        return

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
    await message.reply_text("Transcribing... please wait.")
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_file, file_path)
    except Exception as e:
        await message.reply_text(f"Transcription error: {e}")
        return
    await message.reply_text(f"{text}\n\nPowered by @MediaToTextBot")

if __name__ == "__main__":
    app.run()
