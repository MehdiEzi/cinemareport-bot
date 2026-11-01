# -*- coding: utf-8 -*-
"""
Cinema Report Bot
- عکس + عنوان + لینک‌ها (در چند پیام) -> پست آماده با اطلاعات Gemini
- پایان ورودی: ۱۰ ثانیه بعد از آخرین پیام، یا عبارت «پست رو آماده کن»، یا /done
- سریال‌های طولانی: دکمه‌های فشرده (E01 E02 ...) و در صورت زیاد بودن، صفحه‌ی Telegraph
"""
import asyncio
import html
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
# جلوگیری از چاپ توکن ربات در لاگ‌ها
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("cinema-bot")

# ───────────────────────── تنظیمات (از Environment Variables) ─────────────────────────
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("متغیر BOT_TOKEN در Environment رندر تنظیم نشده است.")

CHANNEL = os.environ.get("CHANNEL_USERNAME", "@cinamareport")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# مدل جایگزین، اگر مدل اصلی خطا داد (اختیاری)
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
# شناسه‌ی عددی ادمین‌ها، با کاما جدا شود. اگر خالی باشد همه می‌توانند از ربات استفاده کنند!
ADMIN_IDS = {
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}

TZ = ZoneInfo("Asia/Tehran")
WAIT_SECONDS = 10          # سکوت لازم برای تشخیص پایان ورودی
CAPTION_LIMIT = 1024       # سقف کپشن عکس در تلگرام
MAX_LINK_BUTTONS = 90      # سقف تلگرام ۱۰۰ دکمه است؛ جا برای دکمه‌های ادمین می‌گذاریم
BUTTONS_PER_ROW = 5

# ───────────────────────── Flask برای پورت رندر ─────────────────────────
app = Flask(__name__)


@app.route("/")
def home():
    return "Cinema Report Bot is running!"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ───────────────────────── حافظه‌ی موقت ─────────────────────────
sessions = {}  # ورودی‌های در حال جمع‌آوری
drafts = {}    # پیش‌نمایش‌های آماده‌ی انتشار

# ───────────────────────── ابزارهای تحلیل متن ─────────────────────────
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

URL_RE = re.compile(r"https?://\S+")
EP_RE = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")
QUALITY_RE = re.compile(r"(2160|1080|720|480|360)p", re.I)
LABEL_QUALITY_RE = re.compile(r"(2160|1080|720|480|360)")
# پیشوند مثل: [10/30/2026 5:26 PM] MeHDi:  (وقتی پیام‌ها از تلگرام دسکتاپ کپی می‌شوند)
PREFIX_RE = re.compile(r"^\[\d{1,2}/\d{1,2}/\d{2,4}[^\]]*\]\s*[^:]{1,40}:\s*")
TRIGGER_RE = re.compile(r"پست\s*(?:رو|را)\s*آماده\s*کن")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
# کلمه‌ی فعال‌کننده‌ی حالت «قسمت جدید» در خط عنوان
UPDATE_RE = re.compile(r"(?:آپدیت|اپدیت|قسمت\s*جدید|\bupdate\b)", re.I)
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

SEASON_WORDS = {
    "اول": 1, "دوم": 2, "سوم": 3, "چهارم": 4, "پنجم": 5,
    "ششم": 6, "هفتم": 7, "هشتم": 8, "نهم": 9, "دهم": 10,
}


def norm(s: str) -> str:
    return s.translate(_DIGITS)


def is_label_line(line: str) -> bool:
    n = norm(line)
    if "فصل" in n or "کیفیت" in n:
        return True
    return bool(re.fullmatch(r"\s*(?:2160|1080|720|480|360)p?\s*:?\s*", n, re.I))


def parse_label(line: str):
    """از خط برچسب (مثل «فصل اول کیفیت 1080») شماره‌ی فصل و کیفیت را درمی‌آورد."""
    n = norm(line)
    season = None
    m = re.search(r"فصل\s*(\d+)", n)
    if m:
        season = int(m.group(1))
    elif "فصل" in n:
        for word, val in SEASON_WORDS.items():
            if word in n:
                season = val
                break
    q = LABEL_QUALITY_RE.search(n)
    return season, (int(q.group(1)) if q else None)


def split_title_year(title: str):
    m = re.match(r"^(.*?)[\s(\[]+((?:19|20)\d{2})[)\]\s]*$", norm(title).strip())
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2)
    return title.strip(), None


def parse_input(raw: str) -> dict:
    lines = []
    for ln in raw.splitlines():
        ln = PREFIX_RE.sub("", ln.strip())
        ln = TRIGGER_RE.sub("", ln).strip()
        if ln:
            lines.append(ln)

    title = None
    if lines and not URL_RE.search(lines[0]) and not is_label_line(lines[0]):
        title = lines.pop(0)

    entries, seen, warnings = [], set(), []
    mismatches = {}
    dups = 0
    cur_label, cur_season, cur_quality = "", None, None

    for ln in lines:
        urls = URL_RE.findall(ln)
        if not urls:
            cur_label = ln
            cur_season, cur_quality = parse_label(ln)
            continue
        for url in urls:
            fname = unquote(url.split("?")[0].rstrip("/").rsplit("/", 1)[-1])
            em = EP_RE.search(fname)
            qm = QUALITY_RE.search(fname)
            season = int(em.group(1)) if em else None
            ep = int(em.group(2)) if em else None
            quality = int(qm.group(1)) if qm else cur_quality

            # اگر برچسب با محتوای لینک نخواند، هشدار می‌دهیم (اعتبار با خود لینک است)
            bad_season = season is not None and cur_season is not None and season != cur_season
            bad_quality = quality is not None and cur_quality is not None and quality != cur_quality
            if (bad_season or bad_quality) and cur_label not in mismatches:
                mismatches[cur_label] = (season, quality)

            key = (season, quality, ep) if ep is not None else ("m", quality, url)
            if key in seen:
                dups += 1
                continue
            seen.add(key)
            entries.append({"url": url, "season": season, "ep": ep, "quality": quality})

    is_series = any(e["ep"] is not None for e in entries)
    if is_series:
        no_ep = [e for e in entries if e["ep"] is None]
        if no_ep:
            warnings.append(f"⚠️ {len(no_ep)} لینک بدون شماره‌ی قسمت (SxxExx) نادیده گرفته شد.")
        entries = [e for e in entries if e["ep"] is not None]

    for label, (s, q) in mismatches.items():
        warnings.append(
            f"⚠️ زیر «{label}» لینک‌هایی از فصل {s if s else '؟'} با کیفیت {q if q else '؟'} بود. "
            f"ربات بر اساس خود لینک‌ها عمل کرد؛ برچسب یا لینک‌ها را چک کن."
        )
    if dups:
        warnings.append(f"⚠️ {dups} لینک تکراری حذف شد.")

    return {"title": title, "entries": entries, "is_series": is_series, "warnings": warnings}


def group_entries(entries):
    groups = {}
    for e in entries:
        groups.setdefault((e["season"], e["quality"]), []).append(e)
    ordered = sorted(groups, key=lambda k: (k[0] or 0, -(k[1] or 0)))
    return [(k, sorted(groups[k], key=lambda e: e["ep"])) for k in ordered]


# ───────────────────────── دکمه‌ها ─────────────────────────
def build_link_rows(entries, is_series):
    rows = []
    if not is_series:
        for e in sorted(entries, key=lambda e: -(e["quality"] or 0)):
            text = f"📥 دانلود با کیفیت {e['quality']}" if e["quality"] else "📥 دانلود"
            rows.append([InlineKeyboardButton(text, url=e["url"])])
        return rows

    for (season, quality), eps in group_entries(entries):
        header = f"📺 فصل {season} | کیفیت {quality if quality else '؟'}"
        rows.append([InlineKeyboardButton(header, callback_data="noop")])
        row = []
        for e in eps:
            row.append(InlineKeyboardButton(f"E{e['ep']:02d}", url=e["url"]))
            if len(row) == BUTTONS_PER_ROW:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    return rows


def admin_rows():
    return [
        [
            InlineKeyboardButton("🚀 انتشار همین الان", callback_data="pub_now"),
            InlineKeyboardButton("⏰ تنظیم زمان", callback_data="pub_later"),
        ],
        [
            InlineKeyboardButton("✏️ ویرایش", callback_data="edit_menu"),
            InlineKeyboardButton("🗑 لغو", callback_data="pub_cancel"),
        ],
    ]


FULL_FIELDS = [
    ("title", "عنوان"), ("imdb", "IMDb"), ("rt", "Rotten Tomatoes"),
    ("genre", "ژانر"), ("country", "محصول"), ("director", "کارگردان"),
    ("cast", "بازیگران"), ("duration", "مدت / وضعیت"),
    ("summary", "خلاصه داستان"), ("why", "چرا ارزش دیدن"),
]
UPDATE_FIELDS = [("title", "عنوان"), ("headline", "تیتر قسمت")]
EDIT_TIMEOUT = 600  # ثانیه؛ بعد از این مدت، حالت ویرایش خودکار لغو می‌شود


def fields_for(draft):
    return UPDATE_FIELDS if draft["kind"] == "update" else FULL_FIELDS


def edit_menu_markup(draft):
    buttons = [InlineKeyboardButton(label, callback_data=f"edit_f:{key}") for key, label in fields_for(draft)]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("↩️ بازگشت به پیش‌نمایش", callback_data="edit_back")])
    return InlineKeyboardMarkup(rows)


def current_value(draft, key):
    d = draft["data"]
    if key == "title":
        return d["title"] + (f" {d['year']}" if d.get("year") else "")
    if key == "headline":
        return d.get("headline") or default_headline(d["season"], d["ep"])
    val = d["info"].get(key)
    if isinstance(val, list):
        val = " ".join(str(x) for x in val)
    return str(val) if val else "نامشخص"


# ───────────────────────── Telegraph ─────────────────────────
_tg_token = os.environ.get("TELEGRAPH_TOKEN")


def telegraph_page(title, entries):
    global _tg_token
    if not _tg_token:
        r = requests.post(
            "https://api.telegra.ph/createAccount",
            data={"short_name": "CinamaReport", "author_name": "CinamaReport"},
            timeout=20,
        ).json()
        if not r.get("ok"):
            raise RuntimeError(f"Telegraph account error: {r.get('error')}")
        _tg_token = r["result"]["access_token"]

    nodes = []
    for (season, quality), eps in group_entries(entries):
        nodes.append({"tag": "h4", "children": [f"فصل {season} | کیفیت {quality if quality else '؟'}"]})
        children = []
        for e in eps:
            if children:
                children.append("  |  ")
            children.append(
                {"tag": "a", "attrs": {"href": e["url"]}, "children": [f"E{e['ep']:02d}"]}
            )
        nodes.append({"tag": "p", "children": children})

    r = requests.post(
        "https://api.telegra.ph/createPage",
        data={
            "access_token": _tg_token,
            "title": title[:200],
            "author_name": "CinamaReport",
            "content": json.dumps(nodes, ensure_ascii=False),
        },
        timeout=30,
    ).json()
    if not r.get("ok"):
        raise RuntimeError(f"Telegraph page error: {r.get('error')}")
    return r["result"]["url"]


# ───────────────────────── Gemini (بدون نیاز به کتابخانه‌ی اضافه) ─────────────────────────
def generate_ai_info(title, year, is_series):
    if not GEMINI_API_KEY:
        return None, "کلید GEMINI_API_KEY تنظیم نشده است."
    kind = "سریال" if is_series else "فیلم"
    year_txt = f" ({year})" if year else ""
    prompt = (
        f"برای {kind} «{title}»{year_txt} اطلاعات زیر را به زبان فارسی برای یک کانال تلگرامی معرفی فیلم تولید کن.\n"
        "خروجی فقط یک شیء JSON با این کلیدها باشد: imdb, rt, genre, country, director, cast, duration, summary, why.\n"
        "- imdb: امتیاز IMDb مثل 8.1/10\n"
        "- rt: درصد Rotten Tomatoes (اگر هر دو بود منتقدان و مخاطبان)\n"
        "- genre: ژانرها با ' | ' جدا شوند\n"
        "- country: کشور سازنده\n"
        "- director: کارگردان یا سازنده\n"
        "- cast: ۲ یا ۳ بازیگر اصلی\n"
        "- duration: مدت زمان فیلم، یا برای سریال تعداد فصل‌ها و وضعیت پخش\n"
        "- summary: خلاصه‌ی داستان بدون اسپویل، حداکثر ۲ جمله‌ی کوتاه\n"
        "- why: یک پاراگراف جذاب و روان (۳ تا ۴ جمله، حداکثر ۵۰ کلمه) درباره‌ی اینکه چرا ارزش دیدن دارد؛ "
        "بدون بولت و بدون اسپویل، با لحن صمیمی و خودمونی، طوری که مخاطب را کنجکاو کند. "
        "مقدارش یک رشته‌ی متنی باشد، نه آرایه\n"
        "اگر درباره‌ی مقداری مطمئن نیستی، مقدارش را «نامشخص» بنویس و عدد یا نام حدسی ننویس. "
        "متن‌ها کوتاه باشند."
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
    }
    models = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models.append(GEMINI_FALLBACK_MODEL)

    last_err = "خطای نامشخص از Gemini."
    deadline = time.monotonic() + 90  # حداکثر زمان کل انتظار برای Gemini
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            if time.monotonic() > deadline:
                break
            try:
                r = requests.post(
                    url,
                    headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                    json=body,
                    timeout=25,
                )
            except requests.RequestException as e:
                log.warning("Gemini network error (%s), model %s", type(e).__name__, model)
                last_err = "Gemini جواب نداد (کند یا شلوغ است)."
                if isinstance(e, requests.Timeout):
                    break  # مدل کند است؛ فوراً سراغ مدل بعدی
                time.sleep(3 * (attempt + 1))
                continue

            if r.status_code in (429, 500, 502, 503, 504):
                # شلوغی یا خطای موقت سرور؛ کمی صبر و تلاش دوباره
                log.warning("Gemini HTTP %s (%s), attempt %d", r.status_code, model, attempt + 1)
                last_err = f"Gemini شلوغ است (کد {r.status_code})."
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 200:
                log.error("Gemini HTTP %s (%s): %s", r.status_code, model, r.text[:300])
                last_err = f"خطای Gemini (کد {r.status_code}). نام مدل یا کلید را چک کن."
                break  # سراغ مدل بعدی

            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
                data = json.loads(text)
            except Exception as e:  # noqa: BLE001
                log.exception("Gemini parse failed")
                last_err = f"پاسخ Gemini قابل‌خواندن نبود ({type(e).__name__})."
                continue
            if isinstance(data, dict):
                return data, None
            last_err = "پاسخ Gemini قابل‌استفاده نبود."

    return None, last_err


# ───────────────────────── ساخت متن پست ─────────────────────────
def esc(x) -> str:
    return html.escape(str(x).strip())


def visible_len(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def default_headline(season, ep):
    return f"قسمت {ep} فصل {season} اضافه شد".translate(_FA_DIGITS)


def build_update_text(title, year, season, ep, headline=None):
    title_txt = esc(title) + (f" ({esc(year)})" if year else "")
    headline = esc(headline) if headline else default_headline(season, ep)
    return (
        f"🆕 <b>CinamaReport | قسمت جدید</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"#سریال | <b>{title_txt}</b>\n\n"
        f"📺 <b>{headline}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎥 @cinamareport"
    )


def build_post_text(info, title, year, is_series):
    def g(key):
        v = info.get(key)
        return esc(v) if v else "نامشخص"

    why = info.get("why")
    if isinstance(why, list):
        why = " ".join(str(x).strip().lstrip("•-– ").strip() for x in why if str(x).strip())
    why_txt = esc(why) if why and str(why).strip() else "نامشخص"

    emoji = "📺" if is_series else "🎬"
    kind = "سریال" if is_series else "فیلم"
    title_txt = esc(title) + (f" ({esc(year)})" if year else "")
    duration_label = "تعداد فصل / وضعیت" if is_series else "مدت زمان"

    return (
        f"{emoji} <b>CinamaReport | معرفی {kind}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"#{kind} | <b>{title_txt}</b>\n"
        f"⭐ <b>IMDb:</b> {g('imdb')}\n"
        f"🍅 <b>Rotten Tomatoes:</b> {g('rt')}\n"
        f"🎭 <b>ژانر:</b> {g('genre')}\n"
        f"🌍 <b>محصول:</b> {g('country')}\n"
        f"🎬 <b>کارگردان / سازنده:</b> {g('director')}\n"
        f"👤 <b>بازیگران:</b> {g('cast')}\n"
        f"⏱ <b>{duration_label}:</b> {g('duration')}\n\n"
        f"📖 <b>خلاصه داستان (بدون اسپویل):</b>\n{g('summary')}\n\n"
        f"🔥 <b>چرا ارزش دیدن داره؟</b>\n{why_txt}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎥 @cinamareport\n"
        f"معرفی فیلم و سریال بدون اسپویل 🍿"
    )


def render_draft(draft):
    """متن پست را از روی داده‌های ذخیره‌شده دوباره می‌سازد (بعد از هر ویرایش)."""
    d = draft["data"]
    if draft["kind"] == "update":
        draft["text"] = build_update_text(d["title"], d["year"], d["season"], d["ep"], d.get("headline"))
    else:
        draft["text"] = build_post_text(d["info"], d["title"], d["year"], d["is_series"])
    draft["split"] = bool(draft["photo"]) and visible_len(draft["text"]) > CAPTION_LIMIT


# ───────────────────────── ارسال پست ─────────────────────────
async def send_post(bot, chat_id, draft, extra_rows=None):
    rows = list(draft["link_rows"]) + (extra_rows or [])
    markup = InlineKeyboardMarkup(rows) if rows else None
    photo = draft["photo"]
    if photo and not draft["split"]:
        await bot.send_photo(
            chat_id, photo, caption=draft["text"], parse_mode=ParseMode.HTML, reply_markup=markup
        )
    elif photo:
        await bot.send_photo(chat_id, photo)
        await bot.send_message(
            chat_id, draft["text"], parse_mode=ParseMode.HTML,
            reply_markup=markup, disable_web_page_preview=True,
        )
    else:
        await bot.send_message(
            chat_id, draft["text"], parse_mode=ParseMode.HTML,
            reply_markup=markup, disable_web_page_preview=True,
        )


def is_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS


# ───────────────────────── ساخت پیش‌نمایش ─────────────────────────
async def build_and_preview(bot, user_id, chat_id):
    try:
        session = sessions.pop(user_id, None)
        if not session or not session["texts"]:
            await bot.send_message(chat_id, "❌ چیزی برای پردازش پیدا نشد. عنوان و لینک‌ها را بفرست.")
            return

        parsed = parse_input("\n".join(session["texts"]))
        if not parsed["title"]:
            await bot.send_message(
                chat_id,
                "❌ عنوان پیدا نشد. خط اولِ اولین پیام باید اسم اثر باشد "
                "(مثلاً <code>The Leftovers</code> یا <code>Revolutionary Road 2008</code>). دوباره بفرست.",
                parse_mode=ParseMode.HTML,
            )
            return
        if not parsed["entries"]:
            await bot.send_message(chat_id, "❌ هیچ لینکی پیدا نشد. دوباره بفرست.")
            return

        raw_title = parsed["title"]
        is_update = bool(UPDATE_RE.search(raw_title))
        if is_update:
            raw_title = UPDATE_RE.sub("", raw_title).strip(" -–|:،")
            if not raw_title:
                await bot.send_message(chat_id, "❌ اسم سریال کنار کلمه‌ی «آپدیت» پیدا نشد. مثال: The Leftovers آپدیت")
                return
        title, year = split_title_year(raw_title)
        is_series = parsed["is_series"]
        warnings = list(parsed["warnings"])

        if is_update:
            if not is_series:
                await bot.send_message(
                    chat_id,
                    "❌ برای پست قسمت جدید، لینک‌ها باید شماره‌ی فصل و قسمت داشته باشند (مثل S03E06 توی اسم فایل).",
                )
                return
            latest = max(parsed["entries"], key=lambda e: (e["season"] or 0, e["ep"] or 0))
            kind = "update"
            data = {"title": title, "year": year, "season": latest["season"], "ep": latest["ep"], "headline": None}
        else:
            await bot.send_message(chat_id, "🤖 در حال نوشتن معرفی...")
            info, ai_err = await asyncio.to_thread(generate_ai_info, title, year, is_series)
            if ai_err:
                warnings.append(f"⚠️ {ai_err} اطلاعات به‌صورت «نامشخص» پر شد؛ پیشنهاد می‌کنم لغو کنی و دوباره بفرستی.")
            kind = "full"
            data = {"title": title, "year": year, "is_series": is_series, "info": dict(info or {})}
        rows = build_link_rows(parsed["entries"], is_series)

        n_buttons = sum(len(r) for r in rows)
        if n_buttons > MAX_LINK_BUTTONS:
            try:
                page_url = await asyncio.to_thread(telegraph_page, title, parsed["entries"])
            except Exception as e:  # noqa: BLE001
                log.exception("Telegraph failed")
                await bot.send_message(
                    chat_id,
                    f"❌ تعداد لینک‌ها از سقف دکمه‌ها بیشتر است و ساخت صفحه‌ی Telegraph هم خطا داد: {e}",
                )
                return
            rows = [[InlineKeyboardButton("📥 مشاهده‌ی همه‌ی لینک‌های دانلود", url=page_url)]]
            warnings.append("ℹ️ تعداد لینک‌ها زیاد بود؛ همه داخل یک صفحه‌ی Telegraph گذاشته شد.")

        drafts[user_id] = {
            "photo": session["photo"],
            "kind": kind,
            "data": data,
            "link_rows": rows,
            "text": "",
            "split": False,
            "waiting_for_time": False,
            "editing": None,
        }
        render_draft(drafts[user_id])
        if drafts[user_id]["split"]:
            warnings.append(
                f"ℹ️ طول متن از {CAPTION_LIMIT} کاراکتر بیشتر شد؛ پست در دو پیام ارسال می‌شود "
                f"(اول عکس، بعد متن و دکمه‌ها). با دکمه‌ی ✏️ ویرایش می‌توانی بخش‌ها را کوتاه‌تر کنی."
            )

        if warnings:
            await bot.send_message(chat_id, "\n".join(warnings))
        await bot.send_message(chat_id, "📌 پیش‌نمایش پست:")
        await send_post(bot, chat_id, drafts[user_id], extra_rows=admin_rows())
    except Exception as e:  # noqa: BLE001
        log.exception("build_and_preview failed")
        await bot.send_message(chat_id, f"❌ خطا در ساخت پست: {e}")


async def apply_edit(bot, chat_id, draft, value):
    key = draft["editing"]
    draft["editing"] = None
    d = draft["data"]
    if key == "title":
        d["title"], d["year"] = split_title_year(value)
    elif key == "headline":
        d["headline"] = value
    else:
        d["info"][key] = value
    render_draft(draft)
    note = "✅ تغییر اعمال شد."
    if draft["split"]:
        note += f" (متن از {CAPTION_LIMIT} کاراکتر بیشتر است؛ پست در دو پیام ارسال می‌شود.)"
    await bot.send_message(chat_id, note)
    await send_post(bot, chat_id, draft, extra_rows=admin_rows())


# ───────────────────────── تایمر پایان ورودی ─────────────────────────
def cancel_timer(context, user_id):
    for job in context.job_queue.get_jobs_by_name(f"fin_{user_id}"):
        job.schedule_removal()


def start_timer(context, user_id, chat_id):
    cancel_timer(context, user_id)
    context.job_queue.run_once(
        finalize_job, WAIT_SECONDS, name=f"fin_{user_id}", chat_id=chat_id, user_id=user_id
    )


async def finalize_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await build_and_preview(context.bot, job.user_id, job.chat_id)


# ───────────────────────── هندلرها ─────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(f"شناسه‌ی عددی شما: {uid}\nشما دسترسی استفاده از این ربات را ندارید.")
        return
    sessions.pop(uid, None)
    cancel_timer(context, uid)
    if drafts.get(uid):
        drafts[uid]["editing"] = None
    await update.message.reply_text(
        "🎬 <b>سلام مدیر عزیز!</b>\n\n"
        "۱. پوستر را همراه عنوان (خط اول کپشن) بفرست؛ مثلاً <code>The Leftovers</code> "
        "یا <code>Revolutionary Road 2008</code>.\n"
        "۲. لینک‌ها را در یک یا چند پیام بفرست (برچسب فصل/کیفیت بالای هر دسته).\n"
        f"۳. {WAIT_SECONDS} ثانیه بعد از آخرین پیام، ربات خودش پست را می‌سازد. "
        "برای سریع‌تر شدن می‌توانی بنویسی «پست رو آماده کن» یا /done را بزنی.\n\n"
        "🆕 <b>قسمت جدید سریال‌های هفتگی:</b> کنار اسم سریال کلمه‌ی «آپدیت» بنویس "
        "(مثلاً <code>The Leftovers آپدیت</code>) و لینک‌ها را بفرست؛ بدون معرفی، فقط تیتر قسمت جدید و دکمه‌ها.\n\n"
        "/cancel برای پاک کردن ورودی‌های نیمه‌کاره.\n"
        f"شناسه‌ی عددی شما: <code>{uid}</code>",
        parse_mode=ParseMode.HTML,
    )


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    cancel_timer(context, uid)
    await build_and_preview(context.bot, uid, update.effective_chat.id)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    cancel_timer(context, uid)
    sessions.pop(uid, None)
    drafts.pop(uid, None)
    await update.message.reply_text("🗑 همه‌ی ورودی‌ها و پیش‌نمایش‌های نیمه‌کاره پاک شد.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    text = msg.caption or msg.text or ""
    chat_id = msg.chat_id

    # دریافت ساعتِ انتشار زمان‌بندی‌شده
    draft = drafts.get(uid)
    if draft and draft.get("waiting_for_time"):
        m = TIME_RE.fullmatch(norm(text).strip())
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            if hour > 23 or minute > 59:
                await msg.reply_text("❌ ساعت نامعتبر است. مثال: 21:30")
                return
            now = datetime.now(TZ)
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            drafts.pop(uid, None)
            context.job_queue.run_once(
                scheduled_publish, when=target, data=draft,
                name=f"sched_{uid}_{int(target.timestamp())}", chat_id=chat_id,
            )
            await msg.reply_text(
                f"⏰ زمان‌بندی شد: {target.strftime('%Y-%m-%d %H:%M')} (به وقت تهران) 🚀"
            )
            return
        # ورودی ساعت نبود؛ یعنی پست جدیدی شروع شده
        draft["waiting_for_time"] = False

    # دریافت متن جدید برای ویرایش (فقط تا چند دقیقه؛ ارسال عکس یعنی پست جدید)
    if draft and draft.get("editing"):
        fresh = time.time() - draft.get("editing_at", 0) < EDIT_TIMEOUT
        if msg.photo or not fresh:
            draft["editing"] = None
        elif msg.text and msg.text.strip():
            await apply_edit(context.bot, chat_id, draft, msg.text.strip())
            return
        else:
            return

    if not text and not msg.photo:
        return

    session = sessions.setdefault(uid, {"texts": [], "photo": None})
    first = not session["texts"] and session["photo"] is None
    if msg.photo:
        session["photo"] = msg.photo[-1].file_id
    if text:
        session["texts"].append(text)

    if TRIGGER_RE.search(text):
        cancel_timer(context, uid)
        await build_and_preview(context.bot, uid, chat_id)
        return

    start_timer(context, uid, chat_id)
    if first:
        await msg.reply_text(
            f"📥 دریافت شد. {WAIT_SECONDS} ثانیه بعد از آخرین پیام، پست ساخته می‌شود "
            f"(یا «پست رو آماده کن» / /done)."
        )


async def scheduled_publish(context: ContextTypes.DEFAULT_TYPE):
    draft = context.job.data
    chat_id = context.job.chat_id
    try:
        await send_post(context.bot, CHANNEL, draft)
        await context.bot.send_message(chat_id, "✅ پست زمان‌بندی‌شده در کانال منتشر شد.")
    except Exception as e:  # noqa: BLE001
        log.exception("scheduled publish failed")
        await context.bot.send_message(chat_id, f"❌ انتشار زمان‌بندی‌شده ناموفق بود: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "noop":  # دکمه‌های عنوان فصل
        await query.answer()
        return
    uid = query.from_user.id
    if not is_admin(uid):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    await query.answer()

    draft = drafts.get(uid)
    if not draft:
        await query.message.reply_text("❌ این پیش‌نمایش منقضی شده است. دوباره اطلاعات را بفرست.")
        return

    data = query.data
    if data == "edit_menu":
        draft["editing"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✏️ کدام بخش را ویرایش کنم؟", reply_markup=edit_menu_markup(draft))
        return
    if data.startswith("edit_f:"):
        key = data.split(":", 1)[1]
        label = dict(fields_for(draft)).get(key)
        if not label:
            return
        draft["editing"] = key
        draft["editing_at"] = time.time()
        await query.message.reply_text(
            f"✏️ متن جدید «{label}» را بفرست.\n\nمقدار فعلی:\n{current_value(draft, key)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ انصراف", callback_data="edit_back")]]),
        )
        return
    if data == "edit_back":
        draft["editing"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("📌 پیش‌نمایش پست:")
        await send_post(context.bot, query.message.chat_id, draft, extra_rows=admin_rows())
        return

    if query.data == "pub_now":
        try:
            await send_post(context.bot, CHANNEL, draft)
        except Exception as e:  # noqa: BLE001
            log.exception("publish failed")
            await query.message.reply_text(f"❌ انتشار ناموفق بود: {e}")
            return
        drafts.pop(uid, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ پست با موفقیت در کانال منتشر شد! 🎉")
    elif query.data == "pub_later":
        draft["waiting_for_time"] = True
        await query.message.reply_text("⏰ ساعت انتشار را بفرست (به وقت تهران، مثلاً 21:30):")
    elif query.data == "pub_cancel":
        drafts.pop(uid, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("🗑 پیش‌نمایش لغو شد.")


def main():
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS تنظیم نشده؛ هر کسی که ربات را پیدا کند می‌تواند پست بسازد!")
    application = ApplicationBuilder().token(TOKEN).build()
    if application.job_queue is None:
        raise RuntimeError("در requirements.txt باید python-telegram-bot[job-queue]==20.7 باشد.")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("done", done_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), handle_message)
    )

    # ابزار ساخت پست اینستاگرام (دستور /insta). اگر خطا بدهد، بقیه‌ی ربات عادی کار می‌کند.
    try:
        import insta
        insta.register(application)
        log.info("Instagram tool loaded.")
    except Exception:
        log.exception("insta module disabled")

    log.info("Bot started.")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    main()
