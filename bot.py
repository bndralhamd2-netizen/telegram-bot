import os
import json
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"api_key": None, "model": "openai/gpt-4o-mini"}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def ask_ai(prompt, config):
    if not config["api_key"]:
        return "⚠️ الرجاء تعيين مفتاح API أولاً باستخدام الأمر /setkey YOUR_API_KEY"
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    data = {
        "model": config["model"],
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=data, timeout=30)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ خطأ: {str(e)}"

async def set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("الاستخدام: /setkey YOUR_API_KEY")
        return
    
    config = load_config()
    config["api_key"] = context.args[0]
    save_config(config)
    await update.message.reply_text("✅ تم تعيين مفتاح API بنجاح!")

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("الاستخدام: /setmodel MODEL_NAME\nمثال: /setmodel anthropic/claude-3-haiku")
        return
    
    config = load_config()
    config["model"] = context.args[0]
    save_config(config)
    await update.message.reply_text(f"✅ تم تعيين النموذج إلى: {context.args[0]}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    reply = ask_ai(update.message.text, config)
    await update.message.reply_text(reply)

app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("setkey", set_key))
app.add_handler(CommandHandler("setmodel", set_model))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("🚀 البوت يعمل...")
app.run_polling()
