import os
import json
import requests
import sqlite3
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_FILE = "users.db"

# ========== إعداد قاعدة البيانات ==========
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT,
            default_model TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user_config(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT api_key, default_model FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {"api_key": row[0], "default_model": row[1]}
    return {"api_key": None, "default_model": None}

def save_user_config(user_id, config):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (user_id, api_key, default_model)
        VALUES (?, ?, ?)
    ''', (user_id, config["api_key"], config["default_model"]))
    conn.commit()
    conn.close()

# ========== باقي الدوال كما هي ==========
def fetch_available_models(api_key):
    url = "https://openrouter.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        return [model["id"] for model in data.get("data", [])]
    except:
        return None

def auto_detect_best_model(api_key):
    if api_key.startswith("AIza"):
        return "google/gemini-2.0-flash-exp:free"
    elif api_key.startswith("gsk_"):
        return "groq/llama-3.3-70b-versatile"
    elif api_key.startswith("sk-or-v1"):
        models = fetch_available_models(api_key)
        if models:
            for pref in ["gpt-4o", "claude-3", "gemini-2.0", "llama-4"]:
                for model in models:
                    if pref in model and ":free" in model:
                        return model
            return models[0]
        return "openai/gpt-4o-mini"
    else:
        return "openai/gpt-4o-mini"

def ask_ai(prompt, api_key, model):
    if not api_key:
        return "⚠️ الرجاء تعيين مفتاح API أولاً باستخدام /setkey"
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=45)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ خطأ: {str(e)}"

async def set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "📌 **الاستخدام:** `/setkey مفتاح_API`\n\n"
            "🔑 هذا المفتاح خاص بك فقط، ولن يراه المستخدمون الآخرون.",
            parse_mode="Markdown"
        )
        return
    
    api_key = context.args[0]
    model = auto_detect_best_model(api_key)
    
    config = get_user_config(user_id)
    config["api_key"] = api_key
    config["default_model"] = model
    save_user_config(user_id, config)
    
    await update.message.reply_text(
        f"✅ **تم تعيين مفتاحك بنجاح!**\n\n"
        f"📡 **النموذج المختار:** `{model}`\n\n"
        f"✨ الآن يمكنك سؤالي أي شيء.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    
    if not config.get("api_key"):
        await update.message.reply_text(
            "⚠️ **لم تقم بتعيين مفتاح API بعد!**\n\n"
            "أرسل `/setkey مفتاحك` لبدء المحادثة.\n\n"
            "💡 مفتاح OpenRouter المجاني: https://openrouter.ai/keys",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return
    
    await update.message.reply_text("🤔 جاري التفكير...")
    reply = ask_ai(update.message.text, config["api_key"], config["default_model"])
    await update.message.reply_text(reply)

# ========== تشغيل البوت ==========
init_db()

app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("setkey", set_key))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("🚀 البوت يعمل على Render...")
print("💾 قاعدة بيانات SQLite - البيانات لا تختفي عند إعادة التشغيل")
app.run_polling()
