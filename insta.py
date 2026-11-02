# -*- coding: utf-8 -*-
"""
insta.py - ساخت کاروسل ۵ اسلایدی اینستاگرام از روی پست کانال
قالب ثابت و مینیمال؛ فقط عکس‌ها از کاربر گرفته می‌شود و بقیه از متن پست استخراج می‌شود.

استفاده در main.py (فقط همین چند خط، بعد از ساخت application):

    try:
        import insta
        insta.register(application)
    except Exception:
        logging.exception("insta module disabled")
"""
import io
import os
import re
import asyncio
import logging
from functools import lru_cache

import colorsys
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from PIL import features as _pil_features

log = logging.getLogger("insta")

# ---------------------------------------------------------------- shaping backend
try:
    import arabic_reshaper
    try:
        from bidi.algorithm import get_display
    except ImportError:  # python-bidi >= 0.5
        from bidi import get_display
    HAVE_SHAPER = True
except Exception:  # pragma: no cover
    HAVE_SHAPER = False
HAVE_RAQM = _pil_features.check("raqm")

# ---------------------------------------------------------------- constants
W, H = 1080, 1440
BG = (247, 247, 247)
ACCENT = (252, 190, 17)
TEXT = (38, 38, 38)
MUTED = (110, 110, 110)
CARD = (224, 224, 224)
FRAME = (222, 222, 222)
BAR = (66, 66, 66)
WHITE = (255, 255, 255)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "fonts")
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")  # اختیاری

RTL_RE = re.compile(r"[\u0590-\u08FF]")
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٫٬", "0123456789.,")


# ---------------------------------------------------------------- fonts / text primitives
def _font_path(bold):
    cands = [
        os.path.join(FONT_DIR, "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("فونت پیدا نشد: fonts/Vazirmatn-Regular.ttf و Vazirmatn-Bold.ttf را بگذارید")


@lru_cache(maxsize=64)
def F(size, bold=False):
    if HAVE_SHAPER or not HAVE_RAQM:
        engine = ImageFont.Layout.BASIC
    else:
        engine = ImageFont.Layout.RAQM
    return ImageFont.truetype(_font_path(bold), int(size), layout_engine=engine)


def _has_rtl(s):
    return bool(RTL_RE.search(s))


def _prep(word):
    """متن را برای رسم آماده می‌کند -> (رشته، kwargs)"""
    if HAVE_SHAPER:
        if _has_rtl(word):
            s = get_display(arabic_reshaper.reshape(word)).replace("\u200c", "")
        else:
            s = word
        return s, {}
    if HAVE_RAQM:
        r = _has_rtl(word)
        return word, {"direction": "rtl" if r else "ltr", "language": "fa" if r else "en"}
    return word, {}


def tlen(word, font):
    s, kw = _prep(word)
    return font.getlength(s, **kw)


def tdraw(d, x, base, word, font, fill):
    s, kw = _prep(word)
    d.text((x, base), s, font=font, fill=fill, anchor="ls", **kw)


# ---------------------------------------------------------------- shapes (anti-aliased)
def _rr_mask(w, h, r, k=4):
    m = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * k - 1, h * k - 1), r * k, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def rrect(img, box, r, fill, outline=None, ow=0):
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    outer = _rr_mask(w, h, r)
    if outline and ow:
        img.paste(Image.new("RGB", (w, h), outline), (x0, y0), outer)
        inner = Image.new("L", (w, h), 0)
        inner.paste(_rr_mask(w - 2 * ow, h - 2 * ow, max(r - ow, 1)), (ow, ow))
        img.paste(Image.new("RGB", (w, h), fill), (x0, y0), inner)
    else:
        img.paste(Image.new("RGB", (w, h), fill), (x0, y0), outer)


def paste_image(img, src, box, r, mode="cover", bg=None):
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    src = ImageOps.exif_transpose(src).convert("RGB")
    if mode == "cover":
        fitted = ImageOps.fit(src, (w, h), Image.LANCZOS, centering=(0.5, 0.4))
        img.paste(fitted, (x0, y0), _rr_mask(w, h, r))
    else:  # contain
        scale = min(w / src.width, h / src.height)
        nw, nh = int(src.width * scale), int(src.height * scale)
        s2 = src.resize((nw, nh), Image.LANCZOS)
        ox, oy = x0 + (w - nw) // 2, y0 + (h - nh) // 2
        img.paste(s2, (ox, oy), _rr_mask(nw, nh, r))


def gauge(img, cx, cy, radius, frac, color, track=(78, 78, 84), thick=14, k=4):
    size = (radius + thick) * 2 + 4
    big = size * k
    c = big // 2
    rr = radius * k
    t = thick * k
    for col, f, is_track in ((track, 1.0, True), (color, frac, False)):
        m = Image.new("L", (big, big), 0)
        bbox = (c - rr, c - rr, c + rr, c + rr)
        if f >= 0.999:
            ImageDraw.Draw(m).ellipse(bbox, outline=255, width=t)
        elif f > 0:
            ImageDraw.Draw(m).arc(bbox, -90, -90 + 360 * f, fill=255, width=t)
        m = m.resize((size, size), Image.LANCZOS)
        img.paste(Image.new("RGB", (size, size), col), (cx - size // 2, cy - size // 2), m)


def dot(img, cx, cy, r, color, k=4):
    size = r * 2 + 2
    m = Image.new("L", (size * k, size * k), 0)
    ImageDraw.Draw(m).ellipse((k, k, (size - 1) * k, (size - 1) * k), fill=255)
    m = m.resize((size, size), Image.LANCZOS)
    img.paste(Image.new("RGB", (size, size), color), (cx - size // 2, cy - size // 2), m)


# ---------------------------------------------------------------- rich text
class Tok:
    __slots__ = ("t", "bold", "color", "nl")

    def __init__(self, t, bold=False, color=None, nl=False):
        self.t, self.bold, self.color, self.nl = t, bold, color, nl


def _norm(w):
    w = w.replace("\u200c", "").replace("ي", "ی").replace("ك", "ک")
    w = re.sub(r"[\s.,،؛:!؟?()\"«»…\-–—'\[\]]", "", w)
    return w.lower()


def _is_latin(s):
    return (not _has_rtl(s)) and any(ch.isalnum() for ch in s)


def _mark_name_sequences(toks, names):
    """نام کامل بازیگر/کارگردان را (حتی بخش‌های کوتاه مثل «سی») کامل بولد می‌کند"""
    seqs = [[_norm(p) for p in n.split() if _norm(p)] for n in names]
    for seq in seqs:
        n = len(seq)
        if n == 0:
            continue
        for i in range(len(toks) - n + 1):
            window = toks[i:i + n]
            if any(t.nl for t in window):
                continue
            if [_norm(t.t) for t in window] == seq:
                for t in window:
                    t.bold = True


def tokens(markup, bold_set=frozenset(), names=()):
    """**بولد**  و  [[زرد-بولد]]  و \\n برای خط جدید"""
    toks = []
    for part in re.split(r"(\*\*.+?\*\*|\[\[.+?\]\]|\n)", markup):
        if not part:
            continue
        if part == "\n":
            toks.append(Tok("", nl=True))
            continue
        bold, color = False, None
        if part.startswith("**"):
            part, bold = part[2:-2], True
        elif part.startswith("[["):
            part, bold, color = part[2:-2], True, ACCENT
        for w in part.split():
            b = bold or (_norm(w) in bold_set)
            toks.append(Tok(w, b, color))
    _mark_name_sequences(toks, names)
    out = []
    for t in toks:
        if (out and not t.nl and not out[-1].nl and _is_latin(t.t) and _is_latin(out[-1].t)
                and t.color == out[-1].color):
            out[-1].t += " " + t.t
            out[-1].bold = out[-1].bold or t.bold
        else:
            out.append(t)
    return out


def _layout(toks, size, width):
    fr, fb = F(size, False), F(size, True)
    sp = fr.getlength(" ")
    lines, cur, curw = [], [], 0.0
    for t in toks:
        if t.nl:
            lines.append((cur, True))
            cur, curw = [], 0.0
            continue
        w = tlen(t.t, fb if t.bold else fr)
        need = w if not cur else curw + sp + w
        if cur and need > width:
            lines.append((cur, False))
            cur, curw = [(t, w)], w
        else:
            cur.append((t, w))
            curw = need
    lines.append((cur, True))
    return lines


def fit_text(markup, bold_set, width, height, max_size, min_size, lh_ratio=1.6, names=()):
    toks = tokens(markup, bold_set, names)
    size = max_size
    while True:
        lines = _layout(toks, size, width)
        lh = int(size * lh_ratio)
        if len(lines) * lh <= height or size <= min_size:
            break
        size -= 2
    # اگر هنوز جا نشد، انتهای متن را کوتاه می‌کنیم
    while len(lines) * lh > height and len(toks) > 5:
        toks = toks[:-3]
        toks.append(Tok("…"))
        lines = _layout(toks, size, width)
    return lines, size, lh


def draw_lines(img, lines, size, lh, right, left, top, align="right", justify=True, color=TEXT):
    d = ImageDraw.Draw(img)
    fr, fb = F(size, False), F(size, True)
    sp = fr.getlength(" ")
    width = right - left
    y = top
    for words, hard in lines:
        if words:
            base = int(y + lh / 2 + size * 0.32)
            total = sum(w for _, w in words)
            n = len(words)
            gap = (width - total) / (n - 1) if (justify and not hard and n > 1) else sp
            line_w = total + gap * (n - 1)
            xr = right if align == "right" else left + (width + line_w) / 2
            for t, w in words:
                tdraw(d, xr - w, base, t.t, fb if t.bold else fr, t.color or color)
                xr -= w + gap
        y += lh
    return y


def text_block(img, markup, bold_set, box, max_size, min_size, align="right", justify=True,
               color=TEXT, lh_ratio=1.6, pad=(36, 26), valign="top", names=()):
    x0, y0, x1, y1 = box
    inner_w = (x1 - x0) - 2 * pad[0]
    inner_h = (y1 - y0) - 2 * pad[1]
    lines, size, lh = fit_text(markup, bold_set, inner_w, inner_h, max_size, min_size, lh_ratio, names)
    top = y0 + pad[1]
    if valign == "middle":
        top = y0 + ((y1 - y0) - len(lines) * lh) / 2
    draw_lines(img, lines, size, lh, x1 - pad[0], x0 + pad[0], top, align, justify, color)


# ---------------------------------------------------------------- parsing
def _num(s):
    s = (s or "").translate(PERSIAN_DIGITS)
    m = re.search(r"\d+(?:\.\d+)?", s.replace(",", "."))
    return float(m.group()) if m else None


def _split_kv(line):
    m = re.split(r"[:：]", line, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    return line.strip(), ""


def _split_list(s):
    return [p.strip() for p in re.split(r"[،,|/]", s) if p.strip()]


def parse_post(text):
    t = text.replace("\r", "")
    m = re.search(r"#\s*(فیلم|سریال)\s*[|｜]\s*(.+?)\s*\((\d{4})\)", t)
    if not m:
        raise ValueError("عنوان پست پیدا نشد (خط #فیلم | Title (سال))")
    d = {
        "kind": m.group(1), "title": m.group(2).strip(), "year": m.group(3),
        "imdb": None, "rt": None, "meta": None,
        "genres": "", "country": "", "director": "", "cast": [],
        "extra_label": "", "extra": "", "summary": "", "why": "", "episodes": [],
    }
    lines = [l.rstrip() for l in t.split("\n")]

    def strip_lead(l):
        return re.sub(r"^[^\w]+", "", l).strip()

    sum_i = why_i = None
    for i, raw in enumerate(lines):
        if "خلاصه داستان" in raw and sum_i is None:
            sum_i = i
        if "چرا" in raw and "ارزش" in raw and why_i is None:
            why_i = i

    def is_end(l):
        return l.strip().startswith("━") or "@" in l or l.strip().startswith("🎥")

    if sum_i is not None:
        buf = []
        for l in lines[sum_i + 1:]:
            if is_end(l) or ("چرا" in l and "ارزش" in l):
                break
            if l.strip():
                buf.append(l.strip())
        d["summary"] = " ".join(buf)
    if why_i is not None:
        buf = []
        for l in lines[why_i + 1:]:
            if is_end(l):
                break
            l = re.sub(r"^[\s•\-–*·]+", "", l).strip()
            if l:
                buf.append(l)
        d["why"] = " ".join(buf)

    skip = set()
    if sum_i is not None:
        skip.add(sum_i)
    if why_i is not None:
        skip.add(why_i)
    body_start = min([x for x in (sum_i, why_i) if x is not None], default=None)
    for i, raw in enumerate(lines):
        if i in skip or raw.strip().startswith("#"):
            continue
        l = strip_lead(raw)
        low = l.lower()
        label, val = _split_kv(l)
        if body_start is not None and i >= body_start:
            # بعد از شروع متن فقط خط‌های اختیاری (نمره متاکریتیک / نمرات قسمت‌ها) معتبرند
            if not re.search(r"[:：]", l):
                continue
            if not ("metacritic" in low or "متاکریتیک" in l or l.startswith("نمرات قسمت")
                    or low.startswith("episodes") or low.startswith("ep:")):
                continue
        if "imdb" in low and d["imdb"] is None:
            d["imdb"] = _num(val)
        elif "rotten" in low and d["rt"] is None:
            d["rt"] = _num(val)
        elif ("metacritic" in low or "متاکریتیک" in l) and d["meta"] is None:
            d["meta"] = _num(val)
        elif l.startswith("ژانر"):
            d["genres"] = "، ".join(_split_list(val))
        elif l.startswith("محصول"):
            d["country"] = "، ".join(_split_list(val))
        elif l.startswith("کارگردان"):
            d["director"] = val
        elif l.startswith("بازیگران"):
            d["cast"] = _split_list(val)
        elif l.startswith("تعداد فصل") or l.startswith("مدت زمان") or l.startswith("وضعیت"):
            d["extra_label"], d["extra"] = label, val
        elif l.startswith("نمرات قسمت") or low.startswith("episodes") or low.startswith("ep:"):
            nums = re.findall(r"\d+(?:[.,٫]\d+)?", val.translate(PERSIAN_DIGITS))
            d["episodes"] = [float(n.replace(",", ".")) for n in nums][:24]
    return d


def _names(d):
    return [n for n in list(d["cast"]) + ([d["director"]] if d["director"] else []) if n]


def _bold_names(d):
    names = list(d["cast"]) + ([d["director"]] if d["director"] else [])
    out = set()
    for n in names:
        for part in n.split():
            p = _norm(part)
            if len(p) >= 4:
                out.add(p)
    return frozenset(out)


# ---------------------------------------------------------------- slide parts
def _heading(img, text, base=250, size=78):
    d = ImageDraw.Draw(img)
    f = F(size, True)
    tdraw(d, 992 - tlen(text, f), base, text, f, ACCENT)


def _logo(img, box):
    x0, y0, x1, y1 = box
    rrect(img, box, 18, ACCENT)
    if os.path.exists(LOGO_PATH):
        try:
            lg = Image.open(LOGO_PATH).convert("RGBA")
            lg.thumbnail((x1 - x0 - 20, y1 - y0 - 20))
            img.paste(lg, (x0 + (x1 - x0 - lg.width) // 2, y0 + (y1 - y0 - lg.height) // 2), lg)
            return
        except Exception:
            log.exception("logo load failed")
    d = ImageDraw.Draw(img)
    size = 40
    while size > 20 and max(tlen("Cinama", F(size, True)), tlen("Report", F(size, True))) > (x1 - x0) - 24:
        size -= 2
    f = F(size, True)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tdraw(d, cx - tlen("Cinama", f) / 2, cy - size * 0.12, "Cinama", f, (40, 40, 40))
    tdraw(d, cx - tlen("Report", f) / 2, cy + size * 0.95, "Report", f, (40, 40, 40))


FOOTER_CTA = "**لینک دانلود رایگان**\nدر [[کانال تلگرامی]] قرار گرفت"
FOOTER_FINAL = "[[@cinamareport]]\nمعرفی فیلم و سریال بدون اسپویل"


def _footer(img, markup):
    rrect(img, (24, 1300, 1056, 1424), 30, BAR)
    _logo(img, (44, 1286, 214, 1438))
    lines, size, lh = fit_text(markup, frozenset(), 780, 116, 38, 24, 1.4)
    draw_lines(img, lines, size, lh, 1034, 244, 1300 + (124 - len(lines) * lh) / 2, "center", False, WHITE)


def _frame(img, src, frame_box, mode="cover"):
    rrect(img, frame_box, 44, FRAME)
    x0, y0, x1, y1 = frame_box
    paste_image(img, src, (x0 + 18, y0 + 16, x1 - 18, y1 - 16), 36, mode)


def _card(img, box):
    rrect(img, box, 48, CARD)


# ---------------------------------------------------------------- slides
def slide_cover(d, src, kw):
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)
    _heading(img, f"معرفی {d['kind']}", base=130, size=46)
    title, year = d["title"], f"({d['year']})"
    # عنوان انگلیسی (چپ‌به‌راست، راست‌چین)
    for size in range(96, 55, -4):
        f = F(size, True)
        fy = F(int(size * 0.62), False)
        wt, wy = tlen(title, f), tlen(" " + year, fy)
        if wt + wy <= 900:
            x = 992 - (wt + wy)
            tdraw(dr, x, 250, title, f, TEXT)
            tdraw(dr, x + wt, 250, " " + year, fy, ACCENT)
            break
    else:
        f = F(60, True)
        words, rows, cur = title.split(), [], ""
        for w in words:
            tryl = (cur + " " + w).strip()
            if tlen(tryl, f) > 900 and cur:
                rows.append(cur)
                cur = w
            else:
                cur = tryl
        rows.append(cur)
        rows = rows[:2]
        for i, row in enumerate(rows):
            tdraw(dr, 992 - tlen(row, f), 215 + i * 80, row, f, TEXT)
    _frame(img, src, (68, 340, 1012, 930))
    _card(img, (85, 960, 995, 1262))
    parts = []
    if d["genres"]:
        parts.append(f"**ژانر:** {d['genres']}")
    if d["country"]:
        parts.append(f"**محصول:** {d['country']}")
    if d["director"]:
        parts.append(f"**کارگردان:** {d['director']}")
    if d["cast"]:
        parts.append(f"**بازیگران:** {'، '.join(d['cast'])}")
    if d["extra"]:
        parts.append(f"**{d['extra_label']}:** {d['extra']}")
    text_block(img, "\n".join(parts), _bold_names(d), (85, 960, 995, 1262), 38, 24,
               justify=False, lh_ratio=1.5, pad=(36, 16), valign="middle", names=_names(d))
    _footer(img, FOOTER_CTA)
    return img


def _text_slide(d, src, kw, heading, body):
    img = Image.new("RGB", (W, H), BG)
    _heading(img, heading)
    _frame(img, src, (68, 330, 1012, 800))
    _card(img, (85, 860, 995, 1215))
    text_block(img, body, _bold_names(d), (85, 860, 995, 1215), 40, 28, justify=True, names=_names(d))
    _footer(img, FOOTER_CTA)
    return img


def slide_story(d, src, kw):
    return _text_slide(d, src, kw, "خلاصه داستان", d["summary"] or "—")


def slide_why(d, src, kw):
    return _text_slide(d, src, kw, "چرا باید این اثر رو دید؟", d["why"] or "—")


def _label(img, cx, cy, text, kind):
    d = ImageDraw.Draw(img)
    if kind == "imdb":
        f = F(38, True)
        w = tlen(text, f)
        rrect(img, (cx - w / 2 - 22, cy - 30, cx + w / 2 + 22, cy + 30), 10, ACCENT)
        tdraw(d, cx - w / 2, cy + 13, text, f, (20, 20, 20))
        return
    size = 32
    while size > 18:
        f = F(size, True)
        w = tlen(text, f)
        if w + size + 14 <= 232:
            break
        size -= 2
    f = F(size, True)
    w = tlen(text, f)
    total = w + size + 14
    x = cx - total / 2
    dot(img, int(x + size / 2), cy, int(size * 0.5), (226, 62, 44) if kind == "rt" else ACCENT)
    tdraw(d, x + size + 14, cy + size * 0.35, text, f, WHITE)


def slide_ratings(d, kw):
    img = Image.new("RGB", (W, H), BG)
    _heading(img, "لیست نمرات")
    rrect(img, (68, 330, 1012, 800), 44, FRAME)
    rrect(img, (86, 346, 994, 784), 38, (30, 30, 34))
    items = []
    if d["meta"] is not None:
        items.append(("metacritic", "meta", d["meta"], d["meta"] / 100, ACCENT))
    if d["rt"] is not None:
        items.append(("Rotten Tomatoes", "rt", d["rt"], d["rt"] / 100, (226, 62, 44)))
    if d["imdb"] is not None:
        items.append(("IMDb", "imdb", d["imdb"], d["imdb"] / 10, ACCENT))
    n = max(len(items), 1)
    cw, gap = 262, 24
    start = 540 - (n * cw + (n - 1) * gap) / 2
    dr = ImageDraw.Draw(img)
    for i, (label, kind, val, frac, col) in enumerate(items):
        x0 = int(start + i * (cw + gap))
        rrect(img, (x0, 400, x0 + cw, 730), 36, (44, 44, 50), outline=(72, 72, 80), ow=2)
        cx = x0 + cw // 2
        _label(img, cx, 462, label, kind)
        gauge(img, cx, 603, 80, max(0.0, min(frac, 1.0)), col)
        txt = f"{val:g}"
        f = F(62, True)
        tdraw(dr, cx - tlen(txt, f) / 2, 603 + 22, txt, f, WHITE)
    if d["episodes"]:
        eps = d["episodes"]
        rows = (len(eps) + 7) // 8
        th, tg = 66, 10
        ch = 44 + rows * th + (rows - 1) * tg
        rrect(img, (85, 860, 995, 860 + ch), 40, CARD)
        tw = (910 - 44 - 7 * tg) / 8
        for i, v in enumerate(eps):
            r, c = divmod(i, 8)
            x0 = 85 + 22 + c * (tw + tg)
            x1 = x0 + tw
            y0 = 860 + 22 + r * (th + tg)
            col = (46, 184, 92) if v >= 8.0 else (250, 226, 100)
            rrect(img, (x0, y0, x1, y0 + th), 10, col)
            tdraw(dr, x0 + 8, y0 + 24, f"E{i + 1}", F(20, False), (60, 60, 60))
            vf = F(34, True)
            tdraw(dr, x1 - 8 - tlen(f"{v:g}" if v != int(v) else f"{v:.1f}", vf), y0 + th - 12,
                  f"{v:g}" if v != int(v) else f"{v:.1f}", vf, (30, 30, 30))
    else:
        rrect(img, (85, 860, 995, 1040), 40, CARD)
        text_block(img, f"**{d['title']}** ({d['year']})\n{d['genres']}", frozenset(),
                   (85, 860, 995, 1040), 40, 26, align="center", justify=False, pad=(30, 14),
                   valign="middle")
    _footer(img, FOOTER_CTA)
    return img


def slide_final(d, src, kw=""):
    img = Image.new("RGB", (W, H), BG)
    _frame(img, src, (68, 50, 1012, 770), mode="contain")
    this = "فیلم" if d["kind"] == "فیلم" else "سریال"
    body = (f"برای دریافت لینک دانلود این {this} و دیگر آثار معرفی‌شده به "
            f"**کانال تلگرامی** که در **بایو پیج** هست مراجعه کنید.")
    text_block(img, body, frozenset(), (68, 790, 1012, 1090), 50, 34, align="center",
               justify=False, lh_ratio=1.6, pad=(30, 10), valign="middle")
    rrect(img, (170, 1110, 910, 1252), 40, WHITE, outline=ACCENT, ow=5)
    text_block(img, "همراهی شما دلگرمی ماست", frozenset(), (170, 1110, 910, 1252), 56, 30,
               align="center", justify=False, lh_ratio=1.3, pad=(30, 10), valign="middle")
    _footer(img, FOOTER_FINAL)
    return img


# ---------------------------------------------------------------- public API
def build_slides(data, images, keyword=""):
    """images: dict با کلیدهای 1,2,3,5 -> bytes. خروجی: لیست ۵ تا JPEG (bytes)"""
    def load(i):
        return Image.open(io.BytesIO(images[i]))

    slides = [
        slide_cover(data, load(1), keyword),
        slide_story(data, load(2), keyword),
        slide_why(data, load(3), keyword),
        slide_ratings(data, keyword),
        slide_final(data, load(5), keyword),
    ]
    out = []
    for s in slides:
        b = io.BytesIO()
        s.save(b, "JPEG", quality=95, subsampling=0)
        out.append(b.getvalue())
    return out



# ---------------------------------------------------------------- caption
def _hashtag(text):
    t = re.sub(r"[^\w\u0600-\u06FF\u200c]+", " ", text or "").strip().replace("\u200c", "_")
    t = re.sub(r"\s+", "_", t).strip("_")
    return f"#{t}" if t else ""


def _title_tag(title):
    latin = re.sub(r"[^A-Za-z0-9]+", "", title or "")
    return f"#{latin}" if latin else _hashtag(title)


def _clean_tags(tags, limit=15):
    out, seen = [], set()
    for t in tags:
        t = _hashtag(str(t).lstrip("#")) if not str(t).startswith("#") or " " in str(t) else str(t)
        t = re.sub(r"[^\w\u0600-\u06FF#]", "", t)
        if len(t) > 1 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:limit]


def _fallback_tags(d):
    kind = d["kind"]
    tags = [f"#معرفی_{kind}", f"#{kind}", "#سینما_ریپورت", "#CinamaReport", _title_tag(d["title"])]
    tags += [_hashtag(g) for g in re.split(r"[،,]", d["genres"]) if g.strip()][:3]
    tags += [_hashtag(n) for n in d["cast"][:2]]
    if d["director"]:
        tags.append(_hashtag(d["director"]))
    return tags


def _gemini_json(prompt, timeout=25, total=60):
    """JSON را از Gemini می‌گیرد؛ اگر نشد None برمی‌گرداند (کلید و مدل‌ها از همان env ربات اصلی)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    import json
    import time
    import requests
    models = [os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")]
    fb = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    if fb and fb not in models:
        models.append(fb)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    deadline = time.monotonic() + total
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            if time.monotonic() > deadline:
                return None
            try:
                r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                  json=body, timeout=timeout)
            except requests.RequestException:
                time.sleep(2)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 200:
                break
            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except Exception:
                log.exception("caption parse failed")
    return None


def make_caption(d):
    """-> (کپشن, با_هوش_مصنوعی_ساخته_شد)"""
    kind = d["kind"]
    emoji = "🎬" if kind == "فیلم" else "📺"
    prompt = (
        f"برای پیج اینستاگرام معرفی فیلم و سریال، کپشن {kind} «{d['title']}» ({d['year']}) را بنویس.\n"
        "فقط بر اساس اطلاعات زیر بنویس و چیزی از خودت اضافه نکن:\n"
        f"ژانر: {d['genres']}\nبازیگران: {'، '.join(d['cast'])}\nکارگردان: {d['director']}\n"
        f"خلاصه: {d['summary']}\nدلیل دیدن: {d['why']}\n\n"
        "خروجی فقط یک JSON با کلیدهای hook, body, hashtags باشد:\n"
        "- hook: یک جمله‌ی جذاب و کنجکاوکننده برای خط اول (حداکثر ۱۲ کلمه، یک ایموجی)\n"
        "- body: ۲ تا ۳ جمله‌ی کوتاه، صمیمی و خودمونی، بدون اسپویل\n"
        "- hashtags: آرایه‌ای از ۶ تا ۸ هشتگ اختصاصی (نام اثر انگلیسی، بازیگران و ژانر؛ "
        "فاصله‌ها با _ جایگزین شوند)\n"
        "درباره‌ی کامنت گذاشتن یا لینک دانلود چیزی ننویس."
    )
    ai = None
    try:
        ai = _gemini_json(prompt)
    except Exception:
        log.exception("caption AI failed")
    hook = body = ""
    extra = []
    if ai:
        hook = str(ai.get("hook") or "").strip()
        body = str(ai.get("body") or "").strip()
        extra = ai.get("hashtags") if isinstance(ai.get("hashtags"), list) else []
    used_ai = bool(hook and body)
    if not used_ai:
        first_genre = (d["genres"].split("،")[0].strip() if d["genres"] else "")
        hook = (f"{emoji} اگه عاشق ژانر {first_genre} هستی، «{d['title']}» رو از دست نده!"
                if first_genre else f"{emoji} «{d['title']}» رو دیدی؟")
        body = (d["summary"] or "")[:350].strip()

    info = []
    if d["imdb"] is not None:
        info.append(f"⭐ IMDb: {d['imdb']:g}")
    if d["rt"] is not None:
        info.append(f"🍅 Rotten Tomatoes: {d['rt']:g}%")
    if d["meta"] is not None:
        info.append(f"Ⓜ️ Metacritic: {d['meta']:g}")
    lines = [hook, "", body, ""]
    if info:
        lines.append(" | ".join(info))
    if d["genres"]:
        lines.append(f"🎭 {d['genres']}")
    if d["cast"]:
        lines.append(f"👤 {'، '.join(d['cast'])}")
    lines += [
        "",
        f"📥 لینک دانلود رایگان این {kind} در کانال تلگرامی ما قرار گرفته؛ لینک کانال توی بایو پیجه.",
        "🍿 دیگر آثار معرفی‌شده رو هم از همون‌جا ببین.",
        "",
        "💾 ذخیره کن و برای دوستی که عاشق سینماست بفرست!",
        "",
        " ".join(_clean_tags(_fallback_tags(d)[:5] + list(extra) + _fallback_tags(d)[5:])),
    ]
    caption = "\n".join(lines).strip()
    return caption[:2200], used_ai



# ================================================================= LIST MODE (چند اثر در یک پست)
LW, LH = 1080, 1350
LBG = (12, 14, 22)
SLOGAN = "معرفی بدون اسپویل فیلم و سریال‌های با کیفیت"
MAX_LIST = 12


def _open(b):
    return ImageOps.exif_transpose(Image.open(io.BytesIO(b))).convert("RGB")


def _fade(img, box, color, a0, a1, horizontal=False):
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    g = Image.linear_gradient("L")
    if horizontal:
        g = g.rotate(90, expand=True)
    g = g.resize((w, h), Image.BILINEAR).point(lambda v: int(255 * (a0 + (a1 - a0) * v / 255)))
    img.paste(Image.new("RGB", (w, h), color), (x0, y0), g)


def _glass(img, box, r=36, tint=(255, 255, 255), alpha=0.16, blur=20, border_alpha=0.4):
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    region = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur))
    region = Image.blend(region, Image.new("RGB", (w, h), tint), alpha)
    mask = _rr_mask(w, h, r)
    img.paste(region, (x0, y0), mask)
    inner = Image.new("L", (w, h), 0)
    inner.paste(_rr_mask(w - 4, h - 4, max(r - 2, 1)), (2, 2))
    ring = ImageChops.subtract(mask, inner).point(lambda v: int(v * border_alpha))
    img.paste(Image.new("RGB", (w, h), (255, 255, 255)), (x0, y0), ring)


def _glass_footer(img):
    box = (48, 1226, 1032, 1324)
    _glass(img, box, r=42, tint=(255, 255, 255), alpha=0.18, blur=20, border_alpha=0.45)
    lines, size, lh = fit_text("[[CinamaReport]]\n" + SLOGAN, frozenset(), 900, 90, 32, 22, 1.35)
    draw_lines(img, lines, size, lh, 1032 - 40, 48 + 40, 1226 + (98 - len(lines) * lh) / 2,
               "center", False, WHITE)


def accent_from(src):
    im = src.convert("RGB")
    im.thumbnail((48, 48))
    bins = [0.0] * 12
    for r, g, b in im.getdata():
        h, s_, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s_ > 0.35 and v > 0.3:
            bins[int(h * 12) % 12] += s_ * v
    if max(bins) < 0.5:
        return ACCENT
    k = bins.index(max(bins))
    r, g, b = colorsys.hsv_to_rgb((k + 0.5) / 12, 0.85, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def _tracked_width(text, font, tr):
    return sum(font.getlength(ch) for ch in text) + tr * (len(text) - 1)


def _tracked_right(d, xr, base, text, font, fill, tr):
    if _has_rtl(text):
        tdraw(d, xr - tlen(text, font), base, text, font, fill)
        return
    x = xr - _tracked_width(text, font, tr)
    for ch in text:
        d.text((x, base), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + tr


def _kind_words(ld):
    kinds = {it.get("kind") for it in ld["items"]}
    if kinds == {"فیلم"}:
        return "فیلم", "فیلم‌ها"
    if kinds == {"سریال"}:
        return "سریال", "سریال‌ها"
    return "اثر", "آثار"


def _fmt_imdb(v):
    return "—" if v is None else f"{float(v):.1f}"


def _fmt_rt(v):
    return "—" if v is None else f"{int(round(float(v)))}%"


def lslide_cover(ld, posters):
    img = Image.new("RGB", (LW, LH), LBG)
    n = len(posters)
    for i, b in enumerate(posters):
        x0, x1 = round(i * LW / n), round((i + 1) * LW / n)
        img.paste(ImageOps.fit(_open(b), (x1 - x0, 920), Image.LANCZOS, centering=(0.5, 0.3)), (x0, 0))
    _fade(img, (0, 520, LW, 920), LBG, 0.0, 1.0)
    text_block(img, f"**{ld['headline']}**", frozenset(), (60, 925, 1020, 1125), 76, 38,
               align="center", justify=False, color=WHITE, lh_ratio=1.35, pad=(0, 0), valign="middle")
    text_block(img, ld["subline"], frozenset(), (90, 1125, 990, 1215), 32, 22, align="center",
               justify=False, color=(205, 208, 215), lh_ratio=1.5, pad=(0, 0), valign="top")
    _glass_footer(img)
    return img


def lslide_ratings(ld, posters, accents):
    img = Image.new("RGB", (LW, LH), LBG)
    items = ld["items"]
    n = len(items)
    usable = 1210
    bh = usable // n
    d = ImageDraw.Draw(img)
    for i, it in enumerate(items):
        y0 = i * bh
        y1 = LH if i == n - 1 else (i + 1) * bh
        band = ImageOps.fit(_open(posters[i]), (LW, y1 - y0), Image.LANCZOS, centering=(0.5, 0.3))
        img.paste(band, (0, y0))
        _fade(img, (int(LW * 0.28), y0, LW, y1), (14, 14, 18), 0.0, 0.96, horizontal=True)
        _fade(img, (int(LW * 0.70), y0, LW, y1), (14, 14, 18), 0.96, 0.96, horizontal=True)
        if i:
            d.rectangle((0, y0, LW, y0 + 1), fill=(52, 52, 58))
        acc = accents[i]
        t = max(34, min(108, int(bh * 0.40)))
        short = (it.get("short") or it["title"]).upper()
        tr = max(4, int(t * 0.16))
        while t > 30 and _tracked_width(short, F(t, True), tr) > 590:
            t -= 4
            tr = max(3, int(t * 0.16))
        sub = it["title"].upper()
        sz = max(18, int(bh * 0.095))
        while sz > 14 and _tracked_width(sub, F(sz, False), 2) > 590:
            sz -= 1
        rs = max(24, min(44, int(bh * 0.15)))
        total = t * 0.72 + 12 + sz + 18 + rs
        top = y0 + (bh - total) / 2
        tb = top + t * 0.72
        sb = tb + 12 + sz * 0.9
        rb = sb + 18 + rs * 0.95
        xr = 1032
        _tracked_right(d, xr, int(tb), short, F(t, True), acc, tr)
        _tracked_right(d, xr, int(sb), sub, F(sz, False), (225, 225, 228), 2)
        # ردیف نمره (از راست به چپ): RT، گوجه، /10، IMDb، نشان IMDb
        fr = F(rs, True)
        txt = _fmt_rt(it.get("rt"))
        x = xr - tlen(txt, fr)
        tdraw(d, x, int(rb), txt, fr, WHITE)
        x -= rs * 0.45
        dot(img, int(x - rs * 0.3), int(rb - rs * 0.35), max(8, int(rs * 0.32)), (226, 62, 44))
        x -= rs * 0.9 + 26
        small = F(max(14, int(rs * 0.5)), False)
        x -= tlen("/10", small)
        tdraw(d, x, int(rb), "/10", small, (190, 190, 195))
        val = _fmt_imdb(it.get("imdb"))
        x -= tlen(val, fr) + 3
        tdraw(d, x, int(rb), val, fr, WHITE)
        bf = F(max(12, int(rs * 0.5)), True)
        bw = tlen("IMDb", bf) + 16
        bx1 = x - 12
        rrect(img, (bx1 - bw, rb - rs * 0.95, bx1, rb + 2), 6, (232, 185, 40))
        tdraw(d, bx1 - bw + 8, int(rb - rs * 0.12), "IMDb", bf, (20, 20, 20))
    _glass_footer(img)
    return img


def lslide_item(it, still, acc):
    img = Image.new("RGB", (LW, LH), LBG)
    img.paste(ImageOps.fit(_open(still), (LW, 900), Image.LANCZOS, centering=(0.5, 0.3)), (0, 0))
    _fade(img, (0, 520, LW, 900), LBG, 0.0, 1.0)
    _glass(img, (60, 730, 1020, 1190), r=40, tint=(0, 0, 0), alpha=0.5, blur=24, border_alpha=0.3)
    d = ImageDraw.Draw(img)
    title = it["title"].upper()
    size = 50
    while size > 26 and tlen(title, F(size, True)) > 880:
        size -= 2
    f = F(size, True)
    tdraw(d, 100, 800, title, f, acc)
    rrect(img, (100, 816, 100 + int(min(tlen(title, f), 880) * 0.38) + 40, 821), 2, acc)
    meta = " | ".join(x for x in (it.get("kind"), str(it.get("year") or ""), it.get("genre") or "") if x)
    text_block(img, f"**{meta}**", frozenset(), (80, 832, 1000, 890), 32, 20, justify=False,
               color=WHITE, lh_ratio=1.3, pad=(20, 4), valign="middle")
    text_block(img, it.get("summary") or "—", frozenset(), (80, 892, 1000, 1176), 38, 26, justify=True,
               color=(235, 236, 240), lh_ratio=1.62, pad=(20, 6))
    _glass_footer(img)
    return img


def lslide_final(ld, posters):
    img = Image.new("RGB", (LW, LH), LBG)
    n = len(posters)
    for i, b in enumerate(posters):
        x0, x1 = round(i * LW / n), round((i + 1) * LW / n)
        img.paste(ImageOps.fit(_open(b), (x1 - x0, LH), Image.LANCZOS, centering=(0.5, 0.3)), (x0, 0))
    img = Image.blend(img, Image.new("RGB", (LW, LH), LBG), 0.80).filter(ImageFilter.GaussianBlur(6))
    _, plural = _kind_words(ld)
    text_block(img, f"**نظر شما درباره این {plural} چیه؟**", frozenset(), (60, 300, 1020, 620), 72, 40,
               align="center", justify=False, color=WHITE, lh_ratio=1.45, pad=(0, 0), valign="middle")
    _glass(img, (70, 680, 1010, 980), r=44, tint=(255, 255, 255), alpha=0.14, blur=22, border_alpha=0.4)
    text_block(img, f"لینک تمامی این {plural} داخل **کانال تلگرامی** قرار گرفته؛ لینک کانال در **بایو** پیجه.",
               frozenset(), (70, 680, 1010, 980), 42, 28, align="center", justify=False, color=WHITE,
               lh_ratio=1.65, pad=(40, 20), valign="middle")
    text_block(img, "نظرت رو توی کامنت‌ها برامون بنویس", frozenset(), (60, 1010, 1020, 1100), 36, 24,
               align="center", justify=False, color=ACCENT, lh_ratio=1.4, pad=(0, 0), valign="middle")
    _glass_footer(img)
    return img


def build_list_slides(ld, posters, stills):
    pimgs = [_open(b) for b in posters]
    accents = [accent_from(im) for im in pimgs]
    slides = [lslide_cover(ld, posters), lslide_ratings(ld, posters, accents)]
    for i, it in enumerate(ld["items"]):
        slides.append(lslide_item(it, stills[i], accents[i]))
    slides.append(lslide_final(ld, posters))
    out = []
    for sl in slides:
        b = io.BytesIO()
        sl.save(b, "JPEG", quality=95, subsampling=0)
        out.append(b.getvalue())
    return out


# ---------------------------------------------------------------- list: input parsing / AI data
def parse_list_names(text, n):
    items = []
    for raw in text.replace("\r", "").split("\n"):
        l = raw.strip()
        if not l:
            continue
        l = re.sub(r"^\s*[\d۰-۹]+\s*[\.\-\)،:]\s*", "", l)
        parts = [p.strip() for p in l.split("|")]
        if not parts[0]:
            continue
        nums = [_num(p) if p and p != "-" else None for p in parts[1:3]]
        nums += [None] * (2 - len(nums))
        items.append({"query": parts[0], "imdb_o": nums[0], "rt_o": nums[1]})
    return items


def _fa_num(n):
    return str(n).translate(_FA_FROM_EN)


_FA_FROM_EN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fetch_list_data(entries):
    n = len(entries)
    listing = "\n".join(f"{i + 1}. {e['query']}" for i, e in enumerate(entries))
    prompt = (
        f"این {n} فیلم/سریال را برای یک پست اینستاگرامی معرفی بدون اسپویل آماده کن. به همین ترتیب:\n{listing}\n\n"
        "خروجی فقط یک JSON با این ساختار باشد:\n"
        '{"headline": "...", "subline": "...", "items": [{"title": "...", "short": "...", "year": "...", '
        '"kind": "فیلم یا سریال", "imdb": 7.9, "rt": 57, "genre": "...", "summary": "..."}], '
        '"caption": {"hook": "...", "body": "...", "hashtags": ["..."]}}\n'
        f"- items دقیقاً {n} عضو و به همان ترتیب ورودی باشد.\n"
        "- title: نام رسمی انگلیسی اثر. short: نام کوتاه و گیرا برای تیتر درشت (حداکثر ۱۴ حرف، انگلیسی)، "
        "مثلاً از «Monster: The Jeffrey Dahmer Story» بشود «Dahmer».\n"
        "- year: سال اولین پخش. kind: دقیقاً «فیلم» یا «سریال».\n"
        "- imdb عدد از ۱۰ و rt درصد راتن تومیتوز؛ اگر مطمئن نیستی null بگذار و عدد حدسی ننویس.\n"
        "- genre: حداکثر ۳ ژانر فارسی با ' | '.\n"
        "- summary: خلاصه‌ی فارسی، صمیمی، بدون اسپویل، ۲ تا ۳ جمله (حداکثر ۴۵ کلمه).\n"
        "- headline: تیتر کاور فارسی کوتاه و جذاب (حداکثر ۸ کلمه) که وجه مشترک این آثار را بگوید. "
        "subline: یک جمله‌ی فارسی کوتاه زیر تیتر.\n"
        "- caption.hook: یک جمله‌ی جذاب برای خط اول کپشن (یک ایموجی). caption.body: ۲ تا ۳ جمله‌ی صمیمی. "
        "caption.hashtags: ۸ تا ۱۰ هشتگ مرتبط.\n"
        "درباره‌ی کامنت یا لینک دانلود چیزی ننویس."
    )
    data = _gemini_json(prompt, timeout=45, total=110)
    if not data or not isinstance(data.get("items"), list) or len(data["items"]) < n:
        return None, "اطلاعات آثار از Gemini گرفته نشد (شلوغ است یا پاسخ ناقص بود)."
    items = []
    for i, e in enumerate(entries):
        raw = data["items"][i] if isinstance(data["items"][i], dict) else {}
        imdb = _num(str(raw.get("imdb"))) if raw.get("imdb") not in (None, "") else None
        rt = _num(str(raw.get("rt"))) if raw.get("rt") not in (None, "") else None
        if e.get("imdb_o") is not None:
            imdb = e["imdb_o"]
        if e.get("rt_o") is not None:
            rt = e["rt_o"]
        title = str(raw.get("title") or e["query"]).strip()
        items.append({
            "title": title,
            "short": str(raw.get("short") or title.split(":")[0]).strip()[:16],
            "year": str(raw.get("year") or "").strip(),
            "kind": raw.get("kind") if raw.get("kind") in ("فیلم", "سریال") else "فیلم",
            "imdb": imdb if imdb is None or 0 <= imdb <= 10 else None,
            "rt": rt if rt is None or 0 <= rt <= 100 else None,
            "genre": str(raw.get("genre") or "").strip(),
            "summary": str(raw.get("summary") or "").strip(),
        })
    ld = {"items": items, "caption": data.get("caption") if isinstance(data.get("caption"), dict) else {}}
    word, _ = _kind_words(ld)
    ld["headline"] = str(data.get("headline") or "").strip() or f"معرفی {_fa_num(n)} {word} که باید ببینی"
    ld["subline"] = (str(data.get("subline") or "").strip()
                     or "خلاصه و امتیاز هر کدوم رو توی اسلایدهای بعدی ببین.")
    return ld, None


def list_caption(ld):
    word, plural = _kind_words(ld)
    cap = ld.get("caption") or {}
    hook = str(cap.get("hook") or "").strip() or f"🎬 {len(ld['items'])} {word} که نباید از دستشون بدی!"
    body = str(cap.get("body") or "").strip()
    lines = [hook, ""]
    if body:
        lines += [body, ""]
    for it in ld["items"]:
        emo = "🎬" if it["kind"] == "فیلم" else "📺"
        yr = f" ({it['year']})" if it["year"] else ""
        lines.append(f"{emo} {it['title']}{yr} | ⭐ {_fmt_imdb(it['imdb'])} | 🍅 {_fmt_rt(it['rt'])}")
    lines += [
        "",
        f"📥 لینک دانلود رایگان همه‌ی این {plural} در کانال تلگرامی ما قرار گرفته؛ لینک کانال توی بایو پیجه.",
        f"💬 نظر شما درباره این {plural} چیه؟ توی کامنت‌ها بنویس!",
        "",
    ]
    tags = ["#سینما_ریپورت", "#CinamaReport", "#معرفی_فیلم_و_سریال"]
    tags += [_title_tag(it["title"]) for it in ld["items"]]
    tags += list(cap.get("hashtags") or [])
    lines.append(" ".join(_clean_tags(tags, limit=20)))
    return "\n".join(lines).strip()[:2200]


def list_info_text(ld):
    rows = []
    for i, it in enumerate(ld["items"], 1):
        rows.append(f"{i}. {it['title']} ({it['year']}) — IMDb: {_fmt_imdb(it['imdb'])} | RT: {_fmt_rt(it['rt'])}")
    return "\n".join(rows)


# ---------------------------------------------------------------- telegram glue
IMG_STEPS = [
    (1, "عکس کاور (عکس اصلی بالای اسلاید اول)"),
    (2, "عکس اسلاید «خلاصه داستان»"),
    (3, "عکس اسلاید «چرا باید دید؟»"),
    (5, "عکس اسلاید آخر (پوستر)"),
]


def _allowed(update):
    ids = os.environ.get("ADMIN_IDS", "").replace(" ", "")
    if not ids:
        return True
    try:
        allowed = {int(x) for x in ids.split(",") if x}
    except ValueError:
        return True
    return update.effective_user and update.effective_user.id in allowed


def _chunk_sizes(n):
    """تلگرام در هر آلبوم حداکثر ۱۰ فایل می‌پذیرد؛ تقسیم متعادل."""
    k = -(-n // 10)
    return [n // k + (1 if i < n % k else 0) for i in range(k)]


def register(application):
    """هندلرها را در گروه -1 ثبت می‌کند تا قبل از هندلرهای فعلی ربات اجرا شوند.
    تا وقتی کاربر وسط جریان /insta یا /insta_list نباشد، هیچ پیامی را نمی‌گیرد."""
    from telegram import InputMediaDocument, InputMediaPhoto
    from telegram.ext import (ApplicationHandlerStop, CommandHandler, MessageHandler, filters)

    def _clear(context):
        for k in ("insta", "insta_list", "insta_fix"):
            context.user_data.pop(k, None)

    async def get_image(msg):
        f = None
        if msg.photo:
            f = await msg.photo[-1].get_file()
        elif msg.document and (msg.document.mime_type or "").startswith("image/"):
            f = await msg.document.get_file()
        return bytes(await f.download_as_bytearray()) if f else None

    async def send_album(msg, slides):
        pos = 0
        for sz in _chunk_sizes(len(slides)):
            await msg.reply_media_group([InputMediaPhoto(x) for x in slides[pos:pos + sz]])
            pos += sz
        pos, idx = 0, 1
        for sz in _chunk_sizes(len(slides)):
            files = []
            for x in slides[pos:pos + sz]:
                bio = io.BytesIO(x)
                bio.name = f"slide_{idx}.jpg"
                idx += 1
                files.append(InputMediaDocument(bio))
            pos += sz
            await msg.reply_media_group(files)

    # ------------------------------------------------------------ /insta (یک اثر)
    async def cmd_start(update, context):
        if not _allowed(update):
            return
        _clear(context)
        context.user_data["insta"] = {"step": "post", "imgs": {}, "queue": list(IMG_STEPS)}
        await update.message.reply_text(
            "پست کانال را کپی/فوروارد کن (می‌توانی خط‌های اختیاری هم اضافه کنی):\n"
            "Metacritic: 74\n"
            "نمرات قسمت‌ها: 7.9 8.1 8.2 ...\n\n"
            "برای انصراف: /insta_cancel"
        )
        raise ApplicationHandlerStop

    async def cmd_cancel(update, context):
        if not _allowed(update):
            return
        had = any(context.user_data.get(k) for k in ("insta", "insta_list", "insta_fix"))
        _clear(context)
        if had:
            await update.message.reply_text("ساخت پست اینستاگرام لغو شد.")
            raise ApplicationHandlerStop

    # ------------------------------------------------------------ /insta_list (چند اثر)
    async def cmd_list_start(update, context):
        if not _allowed(update):
            return
        _clear(context)
        context.user_data["insta_list"] = {"step": "count"}
        await update.message.reply_text(
            f"چند فیلم/سریال می‌خواهی در این پست معرفی کنی؟ (یک عدد بین ۲ تا {MAX_LIST})\n"
            "برای انصراف: /insta_cancel"
        )
        raise ApplicationHandlerStop

    async def cmd_fix(update, context):
        if not _allowed(update):
            return
        last = context.user_data.get("insta_list_last")
        if not last:
            await update.message.reply_text("پست چندتایی‌ای برای اصلاح پیدا نشد (شاید ربات ری‌استارت شده). دوباره /insta_list را بزن.")
            raise ApplicationHandlerStop
        _clear(context)
        context.user_data["insta_fix"] = True
        await update.message.reply_text(
            "نمره‌های فعلی:\n" + list_info_text(last["ld"]) + "\n\n"
            "برای اصلاح، هر اثر را در یک خط بفرست: شماره | IMDb | راتن\n"
            "مثال: 2 | 7.7 | 47\n"
            "برای نگه‌داشتن یک مقدار، به‌جایش - بزن؛ مثال: 3 | - | 65\n"
            "برای انصراف: /insta_cancel"
        )
        raise ApplicationHandlerStop

    async def deliver_list(msg, ld, slides):
        await send_album(msg, slides)
        await msg.reply_text("✅ آماده شد. آلبوم دوم (فایل) با کیفیت کامل است.")
        await msg.reply_text(
            "📊 اطلاعاتی که استخراج شد (نمره‌ها را حتماً چک کن؛ اگر غلط بود /insta_fix را بزن):\n"
            + list_info_text(ld)
        )
        await msg.reply_text("📝 کپشن پیشنهادی اینستاگرام (برای کپی، نگه دار و Copy را بزن):")
        await msg.reply_text(list_caption(ld))

    async def run_build(msg, context):
        st = context.user_data["insta_list"]
        await msg.reply_text("⏳ در حال گرفتن اطلاعات آثار (ممکن است ۱۰ تا ۴۰ ثانیه طول بکشد)...")
        ld, err = await asyncio.to_thread(fetch_list_data, st["entries"])
        if ld is None:
            st["step"] = "retry"
            await msg.reply_text(f"❌ {err}\nعکس‌هایت نگه داشته شد. «دوباره» را بنویس تا تلاش کنم، یا /insta_cancel.")
            return
        await msg.reply_text("🎨 در حال ساخت اسلایدها...")
        slides = await asyncio.to_thread(build_list_slides, ld, st["posters"], st["stills"])
        context.user_data["insta_list_last"] = {"ld": ld, "posters": st["posters"], "stills": st["stills"]}
        context.user_data.pop("insta_list", None)
        await deliver_list(msg, ld, slides)

    async def handle_list(update, context):
        msg = update.message
        ud = context.user_data
        try:
            if ud.get("insta_fix"):
                last = ud.get("insta_list_last")
                ld = last["ld"]
                changed = 0
                for raw in (msg.text or "").splitlines():
                    parts = [x for x in re.split(r"[|\s]+", raw.strip()) if x]
                    if len(parts) < 2:
                        continue
                    idx = _num(parts[0])
                    if idx is None or not 1 <= int(idx) <= len(ld["items"]):
                        continue
                    it = ld["items"][int(idx) - 1]
                    for key, pi, hi in (("imdb", 1, 10), ("rt", 2, 100)):
                        if len(parts) > pi and parts[pi] not in ("-", "—"):
                            v = _num(parts[pi])
                            if v is not None and 0 <= v <= hi:
                                it[key] = v
                    changed += 1
                if not changed:
                    await msg.reply_text("چیزی نفهمیدم. فرمت: 2 | 7.7 | 47  (یا /insta_cancel)")
                    return
                ud.pop("insta_fix", None)
                await msg.reply_text("🎨 در حال ساخت دوباره‌ی اسلایدها...")
                slides = await asyncio.to_thread(build_list_slides, ld, last["posters"], last["stills"])
                await deliver_list(msg, ld, slides)
                return

            st = ud["insta_list"]
            step = st["step"]
            if step == "count":
                m = re.search(r"\d+", (msg.text or "").translate(PERSIAN_DIGITS))
                n = int(m.group()) if m else 0
                if not 2 <= n <= MAX_LIST:
                    await msg.reply_text(f"یک عدد بین ۲ تا {MAX_LIST} بفرست.")
                    return
                st["n"], st["step"] = n, "names"
                await msg.reply_text(
                    f"اسم {n} اثر را بفرست، هر کدام در یک خط (برای دقت بیشتر می‌توانی سال را هم بنویسی):\n"
                    "The Leftovers\nDahmer 2022\n\n"
                    "اگر نمره‌ی مطمئنی داری، می‌توانی کنار اسم بنویسی (اختیاری):\n"
                    "Dahmer 2022 | 7.9 | 57"
                )
            elif step == "names":
                entries = parse_list_names(msg.text or "", st["n"])
                if len(entries) != st["n"]:
                    await msg.reply_text(f"{len(entries)} خط دریافت شد، ولی گفتی {st['n']} اثر. دوباره بفرست (هر اثر یک خط).")
                    return
                st["entries"], st["posters"], st["stills"], st["step"] = entries, [], [], "posters"
                await msg.reply_text(
                    "حالا برای هر اثر یک «پوستر یا تصویر کاور» بفرست (برای نوارهای کاور و اسلاید نمرات).\n"
                    f"۱ از {st['n']}: {entries[0]['query']}"
                )
            elif step == "posters":
                data = await get_image(msg)
                if data is None:
                    await msg.reply_text("لطفاً یک عکس بفرست.")
                    return
                st["posters"].append(data)
                k = len(st["posters"])
                if k < st["n"]:
                    await msg.reply_text(f"{k + 1} از {st['n']}: {st['entries'][k]['query']}")
                else:
                    st["step"] = "stills"
                    await msg.reply_text(
                        "حالا برای هر اثر یک «عکس اسلاید خلاصه» بفرست.\n"
                        "اگر می‌خواهی از همان پوستر استفاده شود، بنویس «همین»؛ برای همه‌ی بقیه: «همه همین».\n"
                        f"۱ از {st['n']}: {st['entries'][0]['query']}"
                    )
            elif step == "stills":
                txt = (msg.text or "").strip()
                k = len(st["stills"])
                if txt == "همه همین":
                    st["stills"].extend(st["posters"][k:])
                elif txt == "همین":
                    st["stills"].append(st["posters"][k])
                else:
                    data = await get_image(msg)
                    if data is None:
                        await msg.reply_text("یک عکس بفرست، یا بنویس «همین» / «همه همین».")
                        return
                    st["stills"].append(data)
                k = len(st["stills"])
                if k < st["n"]:
                    await msg.reply_text(f"{k + 1} از {st['n']}: {st['entries'][k]['query']}")
                else:
                    await run_build(msg, context)
            elif step == "retry":
                if (msg.text or "").strip() == "دوباره":
                    await run_build(msg, context)
                else:
                    await msg.reply_text("«دوباره» را بنویس یا /insta_cancel را بزن.")
        except Exception as e:
            log.exception("insta list failed")
            _clear(context)
            await msg.reply_text(f"❌ خطا: {e}")

    # ------------------------------------------------------------ پیام‌ها
    async def on_message(update, context):
        ud = context.user_data
        if ud.get("insta_list") or ud.get("insta_fix"):
            if not _allowed(update):
                return
            await handle_list(update, context)
            raise ApplicationHandlerStop
        st = ud.get("insta")
        if not st or not _allowed(update):
            return  # اجازه بده بقیه هندلرهای ربات کار خودشان را بکنند
        msg = update.message
        try:
            if st["step"] == "post":
                if not msg.text:
                    await msg.reply_text("متن پست را بفرست.")
                else:
                    try:
                        st["data"] = parse_post(msg.text)
                    except ValueError as e:
                        await msg.reply_text(f"❌ {e}")
                        raise ApplicationHandlerStop
                    dd = st["data"]
                    st["step"] = "imgs"
                    await msg.reply_text(
                        f"✅ {dd['title']} ({dd['year']}) خوانده شد.\n"
                        f"IMDb: {dd['imdb']} | RT: {dd['rt']} | Meta: {dd['meta']} | "
                        f"قسمت‌ها: {len(dd['episodes'])}\n\n"
                        f"حالا {st['queue'][0][1]} را بفرست:"
                    )
            elif st["step"] == "imgs":
                data = await get_image(msg)
                if data is None:
                    await msg.reply_text("لطفاً یک عکس بفرست.")
                else:
                    idx, _ = st["queue"].pop(0)
                    st["imgs"][idx] = data
                    if st["queue"]:
                        await msg.reply_text(f"حالا {st['queue'][0][1]} را بفرست:")
                    else:
                        await msg.reply_text("⏳ در حال ساخت اسلایدها...")
                        slides = await asyncio.to_thread(build_slides, st["data"], st["imgs"])
                        ud.pop("insta", None)
                        await send_album(msg, slides)
                        await msg.reply_text("✅ آماده شد. نسخه دوم (فایل) با کیفیت کامل است.")
                        try:
                            caption, used_ai = await asyncio.to_thread(make_caption, st["data"])
                            await msg.reply_text("📝 کپشن پیشنهادی اینستاگرام (برای کپی، نگه دار و Copy را بزن):")
                            await msg.reply_text(caption)
                            if not used_ai:
                                await msg.reply_text("ℹ️ Gemini جواب نداد؛ کپشن با قالب ساده ساخته شد.")
                        except Exception:
                            log.exception("caption failed")
                            await msg.reply_text("⚠️ ساخت کپشن خطا داد، ولی اسلایدها آماده‌اند.")
        except ApplicationHandlerStop:
            raise
        except Exception as e:
            log.exception("insta failed")
            ud.pop("insta", None)
            await msg.reply_text(f"❌ خطا در ساخت پست: {e}")
        raise ApplicationHandlerStop

    application.add_handler(CommandHandler("insta", cmd_start), group=-1)
    application.add_handler(CommandHandler("insta_list", cmd_list_start), group=-1)
    application.add_handler(CommandHandler("insta_fix", cmd_fix), group=-1)
    application.add_handler(CommandHandler("insta_cancel", cmd_cancel), group=-1)
    application.add_handler(
        MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.IMAGE,
                       on_message),
        group=-1,
    )
