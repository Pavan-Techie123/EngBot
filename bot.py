import os
import uuid

import requests
LT_API_URL = "https://api.languagetool.org/v2/check"
from telegram import InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from deep_translator import GoogleTranslator
import speech_recognition as sr
from pydub import AudioSegment
from gtts import gTTS

# ====== CONFIG ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")
LT_API_URL = "https://api.languagetool.org/v2/check"
TMP_DIR = "/tmp"  # or any writable temp folder

# ====== Helpers ======
def is_telugu(text: str) -> bool:
    """Return True if the text contains any Telugu characters."""
    return any("\u0C00" <= ch <= "\u0C7F" for ch in text)

def correct_english(text):
    try:
        data = {"text": text, "language": "en-US"}
        resp = requests.post(LT_API_URL, data=data, timeout=5).json()
        corrections = []
        for match in resp.get("matches", [])[:3]:
            if match.get("replacements"):
                suggestion = match["replacements"][0]["value"]
                corrections.append(f"❌ {match['message']} → ✅ {suggestion}")
        return "\n".join(corrections) if corrections else "✅ Your English looks good!"
    except Exception:
        return "⚠️ Grammar check not available right now."
    except Exception as e:
        print("LanguageTool error:", e)
        return ""

async def process_text(user_text: str, update, context):
    """Main processing for any recognized text (from typed message or voice)."""
    user_text = user_text.strip()
    if not user_text:
        await update.message.reply_text("⚠️ I didn't get any text.")
        return

    # If input looks like Telugu script -> translate to English
    if is_telugu(user_text):
        try:
            translated_en = GoogleTranslator(source="te", target="en").translate(user_text)
            await update.message.reply_text(f"🗣 Telugu: {user_text}\n➡️ English: {translated_en}")
            # speak the translation (small audio)
            fname = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.mp3")
            gTTS(translated_en, lang="en").save(fname)
            await update.message.reply_voice(voice=InputFile(fname))
            os.remove(fname)
        except Exception as e:
            print("Telugu->English error:", e)
            await update.message.reply_text("⚠️ Could not translate Telugu right now.")
        return

    # Otherwise treat as English: grammar check + translate to Telugu
    try:
        correction = correct_english(user_text)
        # translate EN -> TE (may fail; handle gracefully)
        translated_te = ""
        try:
            translated_te = GoogleTranslator(source="en", target="te").translate(user_text)
        except Exception as e:
            print("EN->TE translation error:", e)

        reply_lines = []
        if correction:
            reply_lines.append("🔍 Grammar suggestions:\n" + correction)
        else:
            reply_lines.append("✅ Your English looks good!")

        if translated_te:
            reply_lines.append(f"➡️ Telugu: {translated_te}")

        await update.message.reply_text("\n\n".join(reply_lines))

        # speak the English sentence (original) for pronunciation practice
        fname = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.mp3")
        gTTS(user_text, lang="en").save(fname)
        await update.message.reply_voice(voice=InputFile(fname))
        os.remove(fname)

    except Exception as e:
        print("process_text error:", e)
        await update.message.reply_text("⚠️ Sorry, I couldn't process that text right now.")

# ====== Handlers ======
async def start(update, context):
    await update.message.reply_text(
        "👋 Hi — send Telugu or English text or a voice note.\n"
        "• Telugu -> I'll translate to English.\n"
        "• English -> I'll check grammar and translate to Telugu.\n"
        "• I also return a short spoken reply to help pronunciation."
    )

async def handle_text(update, context):
    # Some updates may have no text (stickers, etc.); ignore those
    if not update.message or not update.message.text:
        return
    await process_text(update.message.text, update, context)

async def handle_voice(update, context):
    # Download voice (OGG), convert to WAV, run STT, then process text
    tmp_ogg = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.ogg")
    tmp_wav = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.wav")
    try:
        file = await update.message.voice.get_file()
        await file.download_to_drive(tmp_ogg)

        # convert to wav (pydub uses ffmpeg)
        AudioSegment.from_file(tmp_ogg).export(tmp_wav, format="wav")

        r = sr.Recognizer()
        with sr.AudioFile(tmp_wav) as src:
            audio = r.record(src)

        text = None
        # Try Telugu first
        try:
            text = r.recognize_google(audio, language="te-IN")
        except Exception:
            try:
                text = r.recognize_google(audio, language="en-US")
            except Exception:
                text = None

        if not text:
            await update.message.reply_text("⚠️ Sorry, I couldn't understand the voice.")
            return

        await update.message.reply_text(f"🎙️ Recognized: {text}")
        await process_text(text, update, context)

    except Exception as e:
        print("voice handler error:", e)
        await update.message.reply_text("⚠️ Error processing voice.")
    finally:
        # cleanup temp files if they exist
        for p in (tmp_ogg, tmp_wav):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

# ====== Main ======
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("🤖 English Tutor Bot with voice started...")
    app.run_polling()

if __name__ == "__main__":
    main()

