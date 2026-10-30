import os
import threading
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

# ۱. راه‌اندازی سرور Flask برای پورت رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Cinema Report Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

TOKEN = "9207120214:AAH7jBlm1ojESyUeWr2PUdTjOtT4_U2da6k"
CHANNEL_USERNAME = "@cinamareport"

# ذخیره موقت پست‌ها برای ادمین
user_drafts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 **سلام مدیر عزیز!**\n\n"
        "برای ساخت پست، **پوستر فیلم (عکس)** رو به همراه متن اطلاعات و لینک‌های دانلود در کپشنِ همون عکس برای ربات بفرست تا دقیقاً برات پست حرفه‌ای رو بسازه! ✨",
        parse_mode="Markdown"
    )

# دریافت عکس (پوستر) و متن از ادمین
async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # گرفتن فایل آیدی پوستر (اگر عکس فرستاده باشد)
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id

    # گرفتن متن یا کپشن ارسال شده توسط شما
    user_text = update.message.caption or update.message.text
    
    if not user_text:
        await update.message.reply_text("❌ لطفا همراه با پوستر، اطلاعات فیلم و لینک‌ها رو هم بفرستید.")
        return

    lines = [line.strip() for line in user_text.split('\n') if line.strip()]
    title_input = lines[0] if lines else "عنوان نامشخص"
    
    # استخراج لینک‌های دانلود از متن ارسالی شما
    download_links = {}
    for line in lines[1:]:
        lower_line = line.lower()
        if "1080" in lower_line or "full hd" in lower_line:
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

    # ساخت قالب حرفه‌ای با تفکیک دقیق بخش‌ها و بولدسازی کلمات کلیدی
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

    # ذخیره در حافظه موقت همراه با عکس
    user_drafts[user_id] = {
        "photo": photo_file_id,
        "text": post_text,
        "links": download_links
    }

    # ساخت دکمه‌های شیشه‌ای دانلود
    keyboard = []
    for quality, link in download_links.items():
        keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
    
    # دکمه‌های مدیریت انتشار
    keyboard.append([
        InlineKeyboardButton("🚀 انتشار همین الان در کانال", callback_data="pub_now"),
        InlineKeyboardButton("⏰ تنظیم زمان انتشار", callback_data="pub_later")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ارسال پیش‌نمایش به خود شما (همراه با عکس و متن)
    if photo_file_id:
        await update.message.reply_photo(
            photo=photo_file_id,
            caption="📌 **پیش‌نمایش پست با پوستر:**\n\n" + post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text="📌 **پیش‌نمایش پست (بدون پوستر):**\n\n" + post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# مدیریت کلیدهای انتشار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_drafts:
        await query.edit_message_text("❌ اطلاعات پست منقضی شده است. لطفا دوباره پوستر و اطلاعات را بفرستید.")
        return

    draft = user_drafts[user_id]
    photo_file_id = draft["photo"]
    post_text = draft["text"]
    download_links = draft["links"]

    # ساخت دکمه‌های شیشه‌ای برای کانال
    keyboard = []
    for quality, link in download_links.items():
        keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    if query.data == "pub_now":
        if photo_file_id:
            await context.bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=photo_file_id,
                caption=post_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=post_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        await query.edit_message_text("✅ پست همراه با پوستر با موفقیت در کانال @cinamareport منتشر شد! 🎉")
        
    elif query.data == "pub_later":
        await query.edit_message_text("⏰ بخش زمان‌بندی فعال شد. لطفا ساعت انتشار را بفرستید.")

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    # پذیرش عکس همراه با کپشن یا متن ساده
    application.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & (~filters.COMMAND)), handle_media_message))
    
    print("🤖 ربات با قابلیت دریافت پوستر و انتشار حرفه‌ای روشن شد...")
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    main()
