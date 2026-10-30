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

# ذخیره موقت اطلاعات پست و وضعیت زمان‌بندی ادمین‌ها
user_drafts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *سلام مدیر عزیز!*\n\n"
        "پوستر فیلم را به همراه متن اطلاعات و لینک‌ها بفرست تا پست آماده شود.",
        parse_mode="Markdown"
    )

# تابع ارسال پست به کانال (برای انتشار فوری یا زمان‌بندی‌شده)
async def send_to_channel(bot, user_id):
    if user_id not in user_drafts:
        return
    draft = user_drafts[user_id]
    photo_file_id = draft["photo"]
    post_text = draft["text"]
    download_links = draft["links"]

    keyboard = []
    for quality, link in download_links.items():
        keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    if photo_file_id:
        await bot.send_photo(
            chat_id=CHANNEL_USERNAME,
            photo=photo_file_id,
            caption=post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_text = update.message.caption or update.message.text
        
        if not user_text:
            await update.message.reply_text("❌ لطفا متن اطلاعات فیلم را همراه با پوستر بفرستید.")
            return

        # بررسی اینکه آیا کاربر در حال تنظیم زمان انتشار است؟
        if user_id in user_drafts and user_drafts[user_id].get("waiting_for_time"):
            time_str = user_text.strip() # مثلاً 21:30
            try:
                now = datetime.now()
                target_hour, target_minute = map(int, time_str.split(':'))
                target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                
                if target_time <= now:
                    # اگر ساعتی که داده گذشته است، یعنی برای فرداست
                    target_time += timedelta(days=1)
                
                delay = (target_time - now).total_seconds()
                
                # تنظیم تایمر برای ارسال پست در زمان مشخص‌شده
                threading.Timer(delay, lambda: asyncio_run_coroutine(send_to_channel(context.bot, user_id))).start()
                
                user_drafts[user_id]["waiting_for_time"] = False
                await update.message.reply_text(
                    f"⏰ *زمان‌بندی با موفقیت انجام شد!*\n"
                    f"پست شما امشب در ساعت *{time_str}* به‌طور خودکار در کانال @cinamareport منتشر خواهد شد. 🚀",
                    parse_mode="Markdown"
                )
                return
            except Exception as ex:
                await update.message.reply_text("❌ فرمت ساعت نامعتبر است. لطفاً ساعت را به شکل درست (مثلاً 21:30) بفرستید.")
                return

        # پردازش معمولی پست جدید (پوستر + متن اطلاعات)
        photo_file_id = None
        if update.message.photo:
            photo_file_id = update.message.photo[-1].file_id

        lines = [line.strip() for line in user_text.split('\n') if line.strip()]
        title_input = lines[0] if lines else "عنوان نامشخص"
        
        download_links = {}
        for line in lines[1:]:
            lower_line = line.lower()
            link = ""
            if "http" in line:
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

        # اصلاح فرمت بولدسازی با تک ستاره (*) برای تلگرام
        post_text = (
            f"{header_emoji} *CinamaReport | معرفی {media_type}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"{tag} | *{title_input}*\n"
            f"⭐ *IMDb:* 7.6/10\n"
            f"🍅 *Rotten Tomatoes:* ۷۸٪ (منتقدان) | ۸۲٪ (مخاطبان)\n"
            f"🎭 *ژانر:* درام | معمایی | هیجان‌انگیز\n"
            f"🌍 *محصول:* آمریکا | بریتانیا\n"
            f"🎬 *کارگردان:* نام کارگردان\n"
            f"👤 *بازیگران:* بازیگر اول | بازیگر دوم\n"
            f"⏱ *مدت زمان:* ۱۱۵ دقیقه\n"
            f"🗣 *نسخه:* زیرنویس چسبیده فارسی\n\n"
            f"📖 *خلاصه داستان (بدون اسپویل):*\n"
            f"گاهی یک اتفاق کوچک در ظاهر بی‌اهمیت، می‌تواند کل مسیر زندگی آدم‌ها را در کسری از ثانیه تغییر دهد و رازهایی را برملا کند که سال‌ها دفن شده بودند...\n\n"
            f"🔥 *چرا ارزش دیدن داره؟*\n"
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
            "links": download_links,
            "waiting_for_time": False
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
                caption="📌 *پیش‌نمایش پست با پوستر:*\n\n" + post_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text="📌 *پیش‌نمایش پست (بدون پوستر):*\n\n" + post_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except Exception as e:
        await update.message.reply_text(f"خطا در پردازش: {e}")

# تابع کمکی برای اجرای coroutine در ترد تایمر
def asyncio_run_coroutine(coro):
    import asyncio
    asyncio.run(coro)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_drafts:
        await query.edit_message_text("❌ اطلاعات پست منقضی شده است. لطفا دوباره پوستر و اطلاعات را بفرستید.")
        return

    if query.data == "pub_now":
        await send_to_channel(context.bot, user_id)
        await query.edit_message_text("✅ پست همراه با پوستر با موفقیت در کانال @cinamareport منتشر شد! 🎉")
        
    elif query.data == "pub_later":
        user_drafts[user_id]["waiting_for_time"] = True
        await query.edit_message_text(
            "⏰ *سیستم زمان‌بندی فعال شد*\n\n"
            "لطفاً ساعت انتشار پست را به فرمت `HH:MM` (مثلاً `21:30`) در قالب یک پیام به ربات بفرستید تا در همان ساعت پست منتشر شود.",
            parse_mode="Markdown"
        )

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
