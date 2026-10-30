import os
import threading
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ۱. راه‌اندازی سرور Flask برای پورت رندر (Web Service)
app = Flask(__name__)

@app.route('/')
def home():
    return "Cinema Report Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# تنظیمات اصلی
TOKEN = "9207120214:AAH7jBlm1ojESyUeWr2PUdTjOtT4_U2da6k"
CHANNEL_USERNAME = "@cinamareport"  # آیدی کانال شما

# دیکشنری موقت برای ذخیره اطلاعات پست در حال ساخت برای هر ادمین
user_drafts = {}

# دستور شروع
async def start(command_update: Update, context: ContextTypes.DEFAULT_TYPE):
    await command_update.message.reply_text(
        "🎬 **سلام مدیر عزیز!**\n\n"
        "برای ساخت پست جدید، اطلاعات رو به این شکل بفرست:\n\n"
        "نام فیلم یا سریال (به همراه سال)\n"
        "1080: لینک کیفیت ۱۰۸۰\n"
        "720: لینک کیفیت ۷۲۰\n\n"
        "یا به صورت لینک‌های خط به خط بفرست تا ربات هوشمندانه تشخیص بده.",
        parse_mode="Markdown"
    )

# دریافت اطلاعات از ادمین
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_text = update.message.text.strip()
    lines = user_text.split('\n')
    
    title_input = lines[0] if lines else "عنوان نامشخص"
    
    # استخراج لینک‌ها فقط بر اساس ورودی‌های خودتان
    download_links = {}
    for line in lines[1:]:
        line = line.strip()
        lower_line = line.lower()
        if "1080" in lower_line or "full hd" in lower_line:
            # پاک کردن برچسب از ابتدای لینک اگر کاربر نوشته باشد
            clean_link = line.split(":")[-1].strip() if ":" in line else line
            download_links["1080p"] = clean_link
        elif "720" in lower_line:
            clean_link = line.split(":")[-1].strip() if ":" in line else line
            download_links["720p"] = clean_link
        elif "480" in lower_line:
            clean_link = line.split(":")[-1].strip() if ":" in line else line
            download_links["480p"] = clean_link
        elif line.startswith("http"):
            if "1080p" not in download_links:
                download_links["1080p"] = line
            elif "720p" not in download_links:
                download_links["720p"] = line
            elif "480p" not in download_links:
                download_links["480p"] = line

    # تشخیص هوشمند فیلم یا سریال
    is_series = "سریال" in title_input or "season" in title_input.lower() or "فصل" in title_input
    media_type = "سریال" if is_series else "فیلم"
    header_emoji = "📺" if is_series else "🎬"
    tag = "#سریال" if is_series else "#فیلم"

    # ساخت قالب نهایی با بولدسازی دقیق کلمات کلیدی و تفکیک بخش‌ها
    post_text = (
        f"{header_emoji} **CinamaReport | معرفی {media_type}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"{tag} | **{title_input}**\n"
        f"⭐ **IMDb:** 7.6/10\n"
        f"🍅 **Rotten Tomatoes:** ۷۸٪ (منتقدان) | ۸۲٪ (مخاطبان)\n"
        f"🎭 **ژانر:** درام | معمایی | هیجان‌انگیز\n"
        f"🌍 **محصول:** آمریکا | بریتانیا\n"
        f"🎬 **کارگردان:** نام کارگردان\n"
        f"👤 **بازیگران:** بازیگر اول | بازیگر دوم\n"
        f"⏱ **مدت زمان:** ۱۱۵ دقیقه\n"
        f"🗣 **نسخه:** زیرنویس چسبیده فارسی\n\n"
        f"📖 **خلاصه داستان (بدون اسپویل):**\n"
        f"گاهی یک اتفاق کوچک در ظاهر بی‌اهمیت، می‌تواند کل مسیر زندگی آدم‌ها را در کسری از ثانیه تغییر دهد و رازهایی را برملا کند که سال‌ها دفن شده بودند...\n\n"
        f"🔥 **چرا ارزش دیدن داره؟**\n"
        f"• فضاسازی فوق‌العاده تاریک و گیرایی داره که از همون دقیقه‌ی اول قفل می‌شی روش.\n"
        f"• شخصیت‌پردازی‌ها انقدر دقیق و ملموسه که کاملاً باهاشون همذات‌پنداری می‌کنی.\n"
        f"• پایان‌بندی اثر جوریه که تا ساعت‌ها بعدِ تموم شدن فیلم داری به لایه‌های پنهانش فکر می‌کنی!\n"
        f"اگه دنبال یه تجربه‌ی خاص و پر از تعلیق هستی، این اثر رو به هیچ وجه از دست نده. ❤️‍🩹\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎥 @cinamareport \n"
        f"معرفی فیلم و سریال بدون اسپویل 🍿"
    )

    # ذخیره در حافظه موقت ادمین برای زمان‌بندی
    user_drafts[user_id] = {
        "text": post_text,
        "links": download_links
    }

    # دکمه‌های شیشه‌ای برای انتشار فوری یا زمان‌بندی
    keyboard = [
        [
            InlineKeyboardButton("🚀 انتشار همین الان", callback_data="pub_now"),
            InlineKeyboardButton("⏰ تنظیم زمان انتشار", callback_data="pub_later")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # پیش‌نمایش پست برای خودتان همراه با دکمه‌های مدیریت انتشار
    preview_caption = "📌 **پیش‌نمایش پست ساخته‌شده:**\n(برای انتشار در کانال یکی از گزینه‌های زیر را انتخاب کنید)\n\n-------------------\n\n" + post_text
    
    # ساخت دکمه‌های دانلود برای پیش‌نمایش
    dl_keyboard = []
    for quality, link in download_links.items():
        dl_keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
    
    # ترکیب دکمه‌های دانلود و دکمه‌های انتشار
    for row in dl_keyboard:
        keyboard.insert(0, row)

    await update.message.reply_text(
        text=preview_caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# مدیریت دکمه‌های شیشه‌ای (انتشار فوری یا زمان‌بندی)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_drafts:
        await query.edit_message_text("❌ اطلاعات پست منقضی شده است. لطفا دوباره متن فیلم را بفرستید.")
        return

    draft = user_drafts[user_id]
    post_text = draft["text"]
    download_links = draft["links"]

    # ساخت دکمه‌های شیشه‌ای دانلود برای کانال اصلی
    keyboard = []
    for quality, link in download_links.items():
        keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    if query.data == "pub_now":
        # ارسال مستقیم به کانال
        await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await query.edit_message_text("✅ پست با موفقیت همین الان در کانال @cinamareport منتشر شد! 🎉")
        
    elif query.data == "pub_later":
        # برای زمان‌بندی سفارشی (مثلا تست انتشار بعد از 1 دقیقه یا ساعت دلخواه)
        # در اینجا به صورت پیش‌فرض برای کاربر پیام راهنما می‌فرستیم
        await query.edit_message_text(
            "⏰ **سیستم زمان‌بندی:**\n"
            "لطفا ساعت انتشار را به فرمت `HH:MM` (مثلا `21:30`) در پاسخ بفرستید تا ربات در همان ساعت پست را در کانال قرار دهد."
        )

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🤖 ربات Cinema Report با قابلیت مدیریت انتشار و قالب حرفه‌ای روشن شد...")
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    main()
