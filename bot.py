import os
import json
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CONFIG_FILE = "config.json"

# ---------- إدارة الإعدادات ----------
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"api_key": None, "default_model": None}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# ---------- جلب قائمة النماذج من OpenRouter مباشرة ----------
def fetch_available_models(api_key):
    """
    تجلب قائمة النماذج المتاحة من OpenRouter API
    هذه القائمة محدثة تلقائياً بأحدث النماذج
    """
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # استخراج قائمة model IDs
        models = [model["id"] for model in data.get("data", [])]
        return models
    except Exception as e:
        print(f"⚠️ فشل في جلب النماذج: {e}")
        return None

# ---------- اكتشاف أفضل نموذج تلقائياً ----------
def auto_detect_best_model(api_key, user_input=None):
    """
    يكتشف تلقائياً أفضل نموذج مناسب بناءً على:
    1. نوع المفتاح (إذا كان خاصاً بمزود معين)
    2. إمكانية الوصول إلى OpenRouter (إذا كان مفتاح OR)
    3. طلب المستخدم (لتحسين الاختيار مستقبلاً)
    """
    # حالة 1: المفتاح يبدأ بـ AIza → Google Gemini
    if api_key.startswith("AIza"):
        return "google/gemini-2.0-flash-exp:free"
    
    # حالة 2: المفتاح يبدأ بـ gsk_ → Groq
    elif api_key.startswith("gsk_"):
        return "groq/llama-3.3-70b-versatile"
    
    # حالة 3: مفتاح OpenRouter → جلب القائمة واختيار الأفضل
    elif api_key.startswith("sk-or-v1"):
        models = fetch_available_models(api_key)
        if models:
            # ترتيب تفضيلات النماذج (الأحدث أولاً)
            preferences = [
                "gpt-4o", "claude-3", "gemini-2.0", "llama-4",
                "deepseek", "mistral", "qwen"
            ]
            for pref in preferences:
                for model in models:
                    if pref in model and ":free" in model:
                        return model
            # إذا لم يجد نموذجاً مجانياً، يرجع أول نموذج
            return models[0]
        return "openai/gpt-4o-mini"  # النموذج الافتراضي
    
    # حالة 4: مفتاح غير معروف → نحاول استخدام OpenRouter كوسيط
    else:
        return "openai/gpt-4o-mini"

# ---------- سؤال الذكاء الاصطناعي ----------
def ask_ai(prompt, api_key, model):
    if not api_key:
        return "⚠️ الرجاء تعيين مفتاح API أولاً باستخدام /setkey مفتاحك"
    
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
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"❌ خطأ في الاتصال: {str(e)}"
    except (KeyError, json.JSONDecodeError) as e:
        return f"❌ خطأ في استجابة API: {str(e)}"

# ---------- أوامر التليجرام ----------
async def set_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📌 **الاستخدام:** `/setkey مفتاح_API`\n\n"
            "يدعم البوت:\n"
            "• مفاتيح OpenRouter (تبدأ بـ sk-or-v1)\n"
            "• مفاتيح Google Gemini (تبدأ بـ AIza)\n"
            "• مفاتيح Groq (تبدأ بـ gsk_)\n"
            "• أي مفتاح آخر سيتم تمريره عبر OpenRouter",
            parse_mode="Markdown"
        )
        return
    
    api_key = context.args[0]
    model = auto_detect_best_model(api_key)
    
    config = load_config()
    config["api_key"] = api_key
    config["default_model"] = model
    save_config(config)
    
    await update.message.reply_text(
        f"✅ **تم تعيين المفتاح بنجاح!**\n\n"
        f"📡 **النموذك المختار:** `{model}`\n\n"
        f"✨ البوت جاهز للاستخدام. يمكنك الآن سؤالي أي شيء.",
        parse_mode="Markdown"
    )

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يسمح للمستخدم بتغيير النموذج يدوياً (للمتقدمين)"""
    if not context.args:
        await update.message.reply_text(
            "📌 **الاستخدام:** `/setmodel model_id`\n\n"
            "لعرض قائمة النماذج المتاحة، استخدم `/listmodels`",
            parse_mode="Markdown"
        )
        return
    
    config = load_config()
    if not config.get("api_key"):
        await update.message.reply_text("❌ يجب تعيين مفتاح API أولاً باستخدام /setkey")
        return
    
    new_model = context.args[0]
    config["default_model"] = new_model
    save_config(config)
    
    await update.message.reply_text(f"✅ تم تغيير النموذج إلى: `{new_model}`", parse_mode="Markdown")

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض قائمة النماذج المتاحة (محدثة تلقائياً)"""
    config = load_config()
    if not config.get("api_key"):
        await update.message.reply_text("❌ يجب تعيين مفتاح API أولاً باستخدام /setkey")
        return
    
    await update.message.reply_text("🔄 جاري جلب قائمة النماذج المتاحة...")
    
    models = fetch_available_models(config["api_key"])
    if models:
        # عرض أول 20 نموذج فقط (لتجنب الإغراق)
        preview = "\n".join(models[:20])
        await update.message.reply_text(
            f"📋 **النماذج المتاحة (أول 20 من {len(models)}):**\n\n"
            f"```\n{preview}\n```\n\n"
            f"لتغيير النموذج: `/setmodel model_id`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ تعذر جلب قائمة النماذج. تحقق من مفتاح API الخاص بك.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    if not config.get("api_key"):
        await update.message.reply_text(
            "⚠️ الرجاء تعيين مفتاح API أولاً باستخدام الأمر\n"
            "`/setkey YOUR_API_KEY`",
            parse_mode="Markdown"
        )
        return
    
    await update.message.reply_text("🤔 جاري التفكير...")
    reply = ask_ai(update.message.text, config["api_key"], config["default_model"])
    await update.message.reply_text(reply)

# ---------- تشغيل البوت ----------
def main():
    if not TELEGRAM_TOKEN:
        print("❌ خطأ: لم يتم تعيين TELEGRAM_TOKEN في متغيرات البيئة")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إضافة الأوامر
    app.add_handler(CommandHandler("setkey", set_key))
    app.add_handler(CommandHandler("setmodel", set_model))
    app.add_handler(CommandHandler("listmodels", list_models))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 البوت الذكي يعمل...")
    print("📌 الآن أي مفتاح ترسله سيتم التعرف عليه تلقائياً!")
    print("📋 استخدم /listmodels لعرض جميع النماذج المتاحة")
    
    app.run_polling()

if __name__ == "__main__":
    main()
