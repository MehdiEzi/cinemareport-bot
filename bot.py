import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ۱. راه‌اندازی سرور Flask برای رفع خطای پورت در Render (Web Service)
app = Flask(__name__)

@app.route('/')
def home():
    return "Cinema Report Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ۲. توکن ربات شما
TOKEN = "9207120214:AAH7jBlm1ojESyUeWr2PUdTjOtT4_U2da6k"

# ۳. تابع ساخت دکمه‌های شیشه‌ای برای لینک‌های دانلود
def get_download_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 دانلود کیفیت 1080p Full HD", url="https://t.me/cinamareport")],
        [InlineKeyboardButton("📥 دانلود کیفیت 720p", url="https://t.me/cinamareport")],
        [InlineKeyboardButton("📥 دانلود کیفیت 480p", url="https://t.me/cinamareport")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ۴. پردازنده پیام‌های دریافتی (قالب استاندارد CinemaReport)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # نمونه قالب ثابت و حرفه‌ای که تایید کرده بودید
    post_text = (
        "🎬 **CinamaReport | معرفی فیلم**\n"
        "━━━━━━━━━━━━━━\n"
        "#فیلم | Revolutionary Road (2008)\n"
        "⭐ IMDb: 7.3/10\n"
        "🍅 Rotten Tomatoes: 67% (منتقدان) | 70% (مخاطبان)\n"
        "🎭 ژانر: درام | عاشقانه\n"
        "🌍 محصول: آمریکا | بریتانیا\n"
        "🎬 کارگردان: سام مندس\n"
        "👤 بازیگران: لئوناردو دیکاپریو | کیت وینسلت\n"
        "📝 معرفی:\n"
        "اگه فکر می‌کنی زندگی مشترک قراره همیشه توی چرخ‌دنده‌های روزمرگی و تکرار گم بشه، این فیلم مثل یک سیلی محکم آدم رو بیدار میکنه!\n"
        "داستان زوج جوانی که در حومه شهر زندگی آرامی دارند اما زیر پوست این ظاهر، از روزمرگی خفه شدن و تلاش می‌کنن رویاهاشون رو نجات بدن.\n"
        "بازی دیکاپریو و وینسلت طوریه که انگار دارن دعواهای واقعی زن و شوهرها رو روی پرده میارن. تماشای این فیلم یه تراپیِ تلخ ولی کاملاً الزامیه! ❤️‍🩹\n"
        "━━━━━━━━━━━━━━\n"
        "🎥 @cinamareport \n"
        "معرفی فیلم و سریال بدون اسپویل 🍿"
    )

    # ارسال پست همراه با دکمه‌های شیشه‌ای
    await update.message.reply_text(
        text=post_text,
        parse_mode="Markdown",
        reply_markup=get_download_keyboard()
    )

# ۵. تابع اصلی اجرای ربات تلگرام
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    # اضافه کردن هندلر برای دریافت متن‌ها یا لینک‌ها از شما
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🤖 ربات Cinema Report با موفقیت روشن شد و آماده به کار است...")
    application.run_polling()

if __name__ == '__main__':
    # اجرای وب‌سایت Flask در یک ترد (Thread) جداگانه برای رندر
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # اجرای ربات تلگرام
    main()
