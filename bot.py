import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# المفاتيح من Render Environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

# 👇 هذا أهم تعديل (نموذج مضمون)
model = genai.GenerativeModel("gemini-1.5-flash")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text

        response = model.generate_content(user_message)

        await update.message.reply_text(response.text)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


app = Application.builder().token(TELEGRAM_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot is running...")
app.run_polling()
