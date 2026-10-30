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

# حافظه موقت برای ذخیره پیام‌های چندگانه ادمین‌ها
user_sessions = {}
user_drafts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_sessions[user_id] = {"texts": [], "photo": None}
    await update.message.reply_text(
        "🎬 *سلام مدیر عزیز!*\n\n"
        "برای ساخت پست (به‌خصوص سریال‌های طولانی):\n"
        "۱. ابتدا **پوستر سریال** رو به همراه نام سریال در کپشن بفرست.\n"
        "۲. لینک‌های فصل‌ها و کیفیت‌ها رو در **چند پیام پیاپی** بفرست.\n"
        "۳. در انتهای پیام آخر، عبارت **«پست رو آماده کن»** رو بنویس تا ربات فوراً پست رو برات بسازه! 🍿",
        parse_mode="Markdown"
    )

# تابع پردازش نهایی و ساخت پست
async def generate_post(update, context, user_id):
    session = user_sessions[user_id]
    all_text = "\n".join(session["texts"])
    photo_file_id = session["photo"]

    lines = [line.strip() for line in all_text.split('\n') if line.strip()]
    title_input = lines[0] if lines else "عنوان سریال"

    # پردازش هوشمند فصل‌ها و قسمت‌ها
    keyboard = []
    current_label = "لینک دانلود"

    for line in lines[1:]:
        # اگر کاربر عبارت اتمام را نوشته بود، در لینک‌ها لحاظ نکنیم
        if "پست رو آماده کن" in line:
            continue

        lower_line = line.lower()
        link = ""
        if "http" in line:
            parts = line.split("http", 1)
            link = "http" + parts[1].strip().split()[0]

        if not link:
            current_label = line
            continue

        ep_name = "لینک دانلود"
        for part in link.split('/'):
            if 'e' in part.lower() and any(char.isdigit() for char in part):
                ep_name = part.split('.')[-1] if '.' in part else part
                break

        button_text = f"📥 {current_label} ({ep_name})"
        keyboard.append([InlineKeyboardButton(button_text, url=link)])

    # دکمه‌های انتشار
    publish_buttons = [
        InlineKeyboardButton("🚀 انتشار همین الان", callback_data="pub_now"),
        InlineKeyboardButton("⏰ تنظیم زمان", callback_data="pub_later")
    ]
    keyboard.append(publish_buttons)

    post_text = (
        f"📺 *CinamaReport | معرفی سریال*\n"
        f"━━━━━━━━━━━━━━\n"
        f"#سریال | *{title_input}*\n"
        f"⭐ *IMDb:* 8.2/10\n"
        f"🍅 *Rotten Tomatoes:* ۸۵٪ (منتقدان)\n"
        f"🎭 *ژانر:* درام | رازآلود | فلسفی\n"
        f"🌍 *محصول:* آمریکا\n"
        f"🎬 *سازنده:* دیمون لینلوف\n"
        f"🗣 *وضعیت پخش:* کامل با زیرنویس چسبیده فارسی\n\n"
        f"📖 *خلاصه داستان (بدون اسپویل):*\n"
        f"تصور کنید در یک ثانیه، دو درصد از جمعیت کل کره زمین بدون هیچ رد و نشانی ناپدید شوند... دنیایی که باقی می‌ماند با اندوهی بزرگ و سوالاتی بی‌پاسخ دست‌وپنجه نرم می‌کند.\n\n"
        f"🔥 *چرا ارزش دیدن داره؟*\n"
        f"• یکی از عمیق‌ترین و فلسفی‌ترین سریال‌های تاریخ تلویزیون.\n"
        f"• موسیقی متن شاهکار و بازی‌های خیره‌کننده که تا اعماق وجودتون نفوذ می‌کنه.\n"
        f"اگه به آثار مفهومی و متفاوت علاقه داری، این شاهکار رو از دست نده. ❤️‍🩹\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎥 @cinamareport \n"
        f"معرفی فیلم و سریال بدون اسپویل 🍿"
    )

    user_drafts[user_id] = {
        "photo": photo_file_id,
        "text": post_text,
        "keyboard": keyboard,
        "waiting_for_time": False
    }

    del user_sessions[user_id]

    reply_markup = InlineKeyboardMarkup(keyboard)
    if photo_file_id:
        await update.message.reply_photo(
            photo=photo_file_id,
            caption="📌 *پیش‌نمایش پست سریال آماده شد:*\n\n" + post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text="📌 *پیش‌نمایش پست سریال آماده شد:*\n\n" + post_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_text = update.message.caption or update.message.text

        if not user_text:
            return

        # بررسی تنظیم ساعت زمان‌بندی
        if user_id in user_drafts and user_drafts[user_id].get("waiting_for_time"):
            time_str = user_text.strip()
            try:
                now = datetime.now()
                target_hour, target_minute = map(int, time_str.split(':'))
                target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                if target_time <= now:
                    target_time += timedelta(days=1)
                delay = (target_time - now).total_seconds()
                threading.Timer(delay, lambda: asyncio_run_coroutine(send_to_channel(context.bot, user_id))).start()
                user_drafts[user_id]["waiting_for_time"] = False
                await update.message.reply_text(f"⏰ زمان‌بندی انجام شد! پست ساعت *{time_str}* منتشر می‌شود. 🚀", parse_mode="Markdown")
                return
            except Exception:
                await update.message.reply_text("❌ فرمت ساعت نامعتبر است (مثال: 21:30)")
                return

        if user_id not in user_sessions:
            user_sessions[user_id] = {"texts": [], "photo": None}

        if update.message.photo:
            user_sessions[user_id]["photo"] = update.message.photo[-1].file_id

        user_sessions[user_id]["texts"].append(user_text)

        # بررسی اینکه آیا کاربر دستور اتمام را فرستاده است یا خیر
        if "پست رو آماده کن" in user_text:
            await generate_post(update, context, user_id)
        else:
            await update.message.reply_text(
                "📥 بخش اطلاعات دریافت شد.\n"
                "اگر لینک دیگری دارید بفرستید، و در آخرین پیام عبارت «پست رو آماده کن» را بنویسید."
            )
    except Exception as e:
        await update.message.reply_text(f"خطا: {e}")

async def send_to_channel(bot, user_id):
    if user_id not in user_drafts:
        return
    draft = user_drafts[user_id]
    if draft["photo"]:
        await bot.send_photo(chat_id=CHANNEL_USERNAME, photo=draft["photo"], caption=draft["text"], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(draft["keyboard"]))
    else:
        await bot.send_message(chat_id=CHANNEL_USERNAME, text=draft["text"], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(draft["keyboard"]))

def asyncio_run_coroutine(coro):
    import asyncio
    asyncio.run(coro)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_drafts:
        await query.edit_message_text("❌ منقضی شده است. لطفا دوباره شروع کنید.")
        return

    if query.data == "pub_now":
        await send_to_channel(context.bot, user_id)
        await query.edit_message_text("✅ پست سریال با موفقیت در کانال منتشر شد! 🎉")
    elif query.data == "pub_later":
        user_drafts[user_id]["waiting_for_time"] = True
        await query.edit_message_text("⏰ لطفاً ساعت انتشار را بفرستید (مثلاً `21:30`):", parse_mode="Markdown")

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & (~filters.COMMAND)), handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    main()
