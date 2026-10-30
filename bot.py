import os
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ۱. راه‌اندازی سرور Flask برای پورت رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Cinema Report Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

TOKEN = "9207120214:AAH7jBlm1ojESyUeWr2PUdTjOtT4_U2da6k"

# تابع استخراج هوشمند لینک‌ها از صفحه وب
def extract_links_from_webpage(url):
    download_links = {}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                text = a_tag.get_text().lower()
                
                # جستجوی هوشمند کیفیت‌ها در لینک‌ها یا متن دکمه‌های سایت مقصد
                if '1080' in text or '1080' in href:
                    download_links['1080p'] = href
                elif '720' in text or '720' in href:
                    download_links['720p'] = href
                elif '480' in text or '480' in href:
                    download_links['480p'] = href
    except Exception as e:
        print(f"Scraping error: {e}")
    return download_links

# پردازنده پیام‌ها
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    lines = user_text.split('\n')
    
    title_input = lines[0] if lines else "عنوان نامشخص"
    download_links = {}
    
    # بررسی خطوط بعدی برای یافتن لینک صفحه وب یا لینک‌های مستقیم
    for line in lines[1:]:
        line = line.strip()
        if line.startswith("http"):
            # اگر کاربر لینک صفحه سایت را داده باشد، تلاش می‌کنیم لینک‌ها را استخراج کنیم
            scraped = extract_links_from_webpage(line)
            if scraped:
                download_links.update(scraped)
            else:
                # اگر اسکرپ نشد یا لینک مستقیم بود، دستی دسته‌بندی می‌کنیم
                if "1080" in line:
                    download_links["1080p"] = line
                elif "720" in line:
                    download_links["720p"] = line
                elif "480" in line:
                    download_links["480p"] = line
                else:
                    if "1080p" not in download_links:
                        download_links["1080p"] = line
                    elif "720p" not in download_links:
                        download_links["720p"] = line

    # تشخیص هوشمند فیلم یا سریال
    is_series = "سریال" in title_input or "season" in title_input.lower() or "فصل" in title_input
    media_type = "سریال" if is_series else "فیلم"
    header_emoji = "📺" if is_series else "🎬"
    tag = "#سریال" if is_series else "#فیلم"

    # قالب استاندارد کانال
    post_text = (
        f"{header_emoji} **CinamaReport | معرفی {media_type}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"{tag} | {title_input}\n"
        f"⭐ IMDb: 7.5/10\n"
        f"🍅 Rotten Tomatoes: ۷۵٪ (منتقدان) | ۸۰٪ (مخاطبان)\n"
        f"🎭 ژانر: درام | رازآلود\n"
        f"🌍 محصول: آمریکا\n"
        f"🎬 کارگردان / سازنده: مشخصات اثر\n"
        f"📝 معرفی:\n"
        f"گاهی مسیر داستان طوری پیش می‌ره که تا آخرین لحظه نمی‌تونی حدس بزنی چه اتفاقی قراره بیفته...\n"
        f"این اثر با فضاسازی فوق‌العاده و قصه‌ای که داره، قشنگ تو رو تا تهش با خودش همراه می‌کنه. اگر دنبال یه تجربه‌ی خاص و متفاوت هستی، حتماً وقت بذار و تماشاش کن! ✨\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎥 @cinamareport \n"
        f"معرفی فیلم و سریال بدون اسپویل 🍿"
    )

    # ساخت دکمه‌های شیشه‌ای
    keyboard = []
    if download_links:
        for quality, link in download_links.items():
            keyboard.append([InlineKeyboardButton(f"📥 دانلود کیفیت {quality}", url=link)])
    else:
        keyboard.append([InlineKeyboardButton("📥 دانلود رایگان با زیرنویس فارسی", url="https://t.me/cinamareport")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=post_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🤖 ربات Cinema Report با قابلیت استخراج لینک فعال شد...")
    application.run_polling()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    main()
