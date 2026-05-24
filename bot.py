import os
import json
import requests
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Tuple
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_FILE = "ultimate_bot.db"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, api_key TEXT, default_model TEXT, created_at TIMESTAMP, last_used TIMESTAMP, total_requests INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS requests_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, model TEXT, prompt_length INTEGER, response_time REAL, status TEXT, timestamp TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_user_config(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT api_key, default_model, total_requests FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"api_key": row[0], "default_model": row[1] or "google/gemini-2.0-flash-exp:free", "total_requests": row[2]}
    return {"api_key": None, "default_model": "google/gemini-2.0-flash-exp:free", "total_requests": 0}

def save_user_config(user_id: int, config: Dict):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO users (user_id, api_key, default_model, last_used, total_requests) VALUES (?, ?, ?, ?, ?)''', (user_id, config["api_key"], config["default_model"], datetime.now(), config.get("total_requests", 0)))
    conn.commit()
    conn.close()

def log_request(user_id: int, model: str, prompt_length: int, response_time: float, status: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO requests_log (user_id, model, prompt_length, response_time, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)''', (user_id, model, prompt_length, response_time, status, datetime.now()))
    conn.commit()
    conn.close()

class UniversalAPI:
    @staticmethod
    def detect_provider(api_key: str) -> str:
        if api_key.startswith("AIza"): return "google"
        elif api_key.startswith("gsk_"): return "groq"
        elif api_key.startswith("sk-ant"): return "anthropic"
        elif api_key.startswith("sk-or-v1"): return "openrouter"
        elif api_key.startswith("sk-") and len(api_key) > 30: return "openai"
        else: return "openrouter"
    
    @staticmethod
    def get_default_model(provider: str) -> str:
        defaults = {"google": "google/gemini-2.0-flash-exp:free", "groq": "groq/llama-3.3-70b-versatile", "openrouter": "openai/gpt-4o-mini", "openai": "openai/gpt-3.5-turbo"}
        return defaults.get(provider, "openai/gpt-4o-mini")
    
    @staticmethod
    async def ask(prompt: str, api_key: str, model: str) -> Tuple[str, float]:
        import time
        start_time = time.time()
        if not api_key:
            return "⚠️ الرجاء تعيين مفتاح API باستخدام /setkey", 0
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://t.me/ai_bot", "X-Title": "Ultimate Telegram AI Bot"}
        data = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 2000}
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            result = response.json()
            if "error" in result:
                return f"❌ خطأ: {result['error'].get('message', str(result['error']))}", 0
            if "choices" in result and len(result["choices"]) > 0:
                elapsed = time.time() - start_time
                return result["choices"][0]["message"]["content"], elapsed
            return f"⚠️ رد غير متوقع: {str(result)[:200]}", 0
        except Exception as e:
            return f"❌ خطأ: {str(e)[:100]}", 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""🌟 **مرحباً بك في البوت الخارق!** 🌟

أنا بوت ذكي يمكنه استخدام **أي نموذج ذكاء اصطناعي** تريده.

**📋 كيف تبدأ؟**
1️⃣ احصل على مفتاح مجاني من [OpenRouter](https://openrouter.ai/keys)
2️⃣ أرسل: `/setkey مفتاحك_هنا`
3️⃣ ابدأ المحادثة! 💬

**🔧 أوامر مفيدة:**
• `/setmodel اسم_النموذج` - تغيير النموذج
• `/status` - حالة حسابك
• `/reset` - إعادة تعيين""", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""📚 **الأوامر المتاحة:**
• `/start` - شرح البوت
• `/setkey مفتاحك` - تعيين مفتاح API
• `/setmodel اسم_النموذج` - تغيير النموذج
• `/status` - عرض حالتك
• `/reset` - حذف بياناتك

**💡 نماذج مجانية:**
• `google/gemini-2.0-flash-exp:free`
• `meta-llama/llama-3.2-3b-instruct:free`
• `microsoft/phi-3.5-mini-128k:free`

[جميع النماذج](https://openrouter.ai/models)""", parse_mode="Markdown", disable_web_page_preview=True)

async def set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("🔑 **الاستخدام:** `/setkey مفتاحك`\n\nاحصل على مفتاح من [OpenRouter](https://openrouter.ai/keys)", parse_mode="Markdown", disable_web_page_preview=True)
        return
    
    api_key = context.args[0]
    provider = UniversalAPI.detect_provider(api_key)
    default_model = UniversalAPI.get_default_model(provider)
    
    config = get_user_config(user_id)
    config["api_key"] = api_key
    config["default_model"] = default_model
    save_user_config(user_id, config)
    
    await update.message.reply_text(f"✅ **تم تعيين المفتاح بنجاح!**\n\n🔍 **المزود:** `{provider.upper()}`\n🤖 **النموذج:** `{default_model}`\n\n✨ البوت جاهز!", parse_mode="Markdown")

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    
    if not config.get("api_key"):
        await update.message.reply_text("❌ أرسل `/setkey مفتاحك` أولاً", parse_mode="Markdown")
        return
    
    if not context.args:
        await update.message.reply_text("""🎯 **نماذج مجانية مقترحة:**
• `google/gemini-2.0-flash-exp:free`
• `meta-llama/llama-3.2-3b-instruct:free`
• `microsoft/phi-3.5-mini-128k:free`

**للتغيير:** `/setmodel اسم_النموذج`""", parse_mode="Markdown")
        return
    
    new_model = context.args[0]
    old_model = config["default_model"]
    config["default_model"] = new_model
    save_user_config(user_id, config)
    
    await update.message.reply_text(f"✅ **تم تغيير النموذج!**\n\n📦 من: `{old_model}`\n🚀 إلى: `{new_model}`", parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    
    if not config.get("api_key"):
        await update.message.reply_text("ℹ️ البوت غير نشط. أرسل `/setkey مفتاحك`", parse_mode="Markdown")
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), AVG(response_time) FROM requests_log WHERE user_id = ? AND status = 'success'", (user_id,))
    stats = c.fetchone()
    conn.close()
    
    total_requests = stats[0] if stats[0] else 0
    avg_time = stats[1] if stats[1] else 0
    provider = UniversalAPI.detect_provider(config["api_key"])
    
    await update.message.reply_text(f"""📊 **حالة حسابك**
🔑 **المفتاح:** موجود ✅
📡 **المزود:** `{provider.upper()}`
🤖 **النموذج:** `{config['default_model']}`
📈 **الطلبات:** {total_requests}
⚡ **متوسط الوقت:** {avg_time:.1f} ثانية""", parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🔄 **تم حذف بياناتك بالكامل!**\nأرسل `/setkey مفتاحك` للبدء من جديد", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    
    if not config.get("api_key"):
        await update.message.reply_text("🔑 **لم تقم بتعيين مفتاح!**\nأرسل `/setkey مفتاحك`\n\n💡 احصل على مفتاح مجاني: [OpenRouter](https://openrouter.ai/keys)", parse_mode="Markdown", disable_web_page_preview=True)
        return
    
    thinking_msg = await update.message.reply_text("🧠 **جاري التفكير...**", parse_mode="Markdown")
    response, elapsed = await UniversalAPI.ask(update.message.text, config["api_key"], config["default_model"])
    log_request(user_id, config["default_model"], len(update.message.text), elapsed, "success" if "❌" not in response else "error")
    config["total_requests"] += 1
    save_user_config(user_id, config)
    await thinking_msg.edit_text(f"{response}\n\n_⏱️ {elapsed:.1f} ثانية_", parse_mode="Markdown")

def main():
    if not TELEGRAM_TOKEN:
        logger.error("❌ خطأ: لم يتم تعيين TELEGRAM_TOKEN في متغيرات البيئة!")
        return
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setkey", set_key))
    app.add_handler(CommandHandler("setmodel", set_model))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 البوت الخارق يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
