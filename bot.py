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

user_drafts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 **سلام مدیر عزیز!**\n\n"
        "پوستر فیلم رو به همراه متن اطلاعات و لینک‌ها بفرست تا پست آماده بشه.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        
        photo_file_id = None
        if update.message.photo:
            photo_file_id = update.message.photo[-1].file_id

        user_text = update.message.caption or update.message.text
        if not user_text:
            await update.message.reply_text("❌ لطفا متن اطلاعات فیلم را همراه با پوستر بفرستید.")
            return

        lines = [line.strip() for line in user_text.split('\n') if line.strip()]
        title_input = lines[0] if lines else "عنوان نامشخص"
        
        # استخراج دقیق لینک‌ها بدون خراب شدن https://
        download_links = {}
        for line in lines[1:]:
            lower_line = line.lower()
            
            # پیدا کردن لینک صحیح در خط
            link = ""
            if "http" in line:
                # استخراج بخش بعد از اولین کلیدواژه یا جدا کردن با اسپیس/دوهفته
                parts = line.split("http", 1)
                link = "http" + parts[1].strip().split()[0]

            if not link:
                continue

            if "1080" in lower_line:
                download_links["1080p"] = link
            elif "720" in lower_line:
                download_links["720p"] = link
            elif "480" in lower_line:
                download_links["480p"] = link
            else:
                if "1080p" not in download_links:
                    download_links["1080p"] = link
                elif "720p" not in download_links:
                    download_links["720p"] = link
                elif "480p" not in download_links:
                    download_links["480p"] = link

        is_series = "سریال" in title_input or "season" in title_input.lower() or "فصل" in title_input
        media_type = "سریال" if is_series else "فیلم"
        header_emoji = "📺" if is_series else "🎬"
        tag = "#سریال" if is_series else "#فیلم"

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

        user_drafts[user_id] = {
            "photo": photo_file_id,
            "text": post_text,
            "links": download_links
        }

        keyboard = []
        for quality, link in download_links.items():
            keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
        
        keyboard.append([
            InlineKeyboardButton("🚀 انتشار همین الان در کانال", callback_data="pub_now"),
            InlineKeyboardButton("⏰ تنظیم زمان انتشار", callback_data="pub_later")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

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
    except Exception as e:
        await update.message.reply_text(f"خطا در پردازش: {e}")

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

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & (~filters.COMMAND)), handle_message))
    
    print("🤖 ربات با موفقیت روشن شد و آماده به کار است...")
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    main()
