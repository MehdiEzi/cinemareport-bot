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

from PIL import Image, ImageDraw, ImageFont, ImageOps
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
    rrect(img, box, 16, ACCENT)
    if os.path.exists(LOGO_PATH):
        try:
            lg = Image.open(LOGO_PATH).convert("RGBA")
            lg.thumbnail((x1 - x0 - 20, y1 - y0 - 20))
            img.paste(lg, (x0 + (x1 - x0 - lg.width) // 2, y0 + (y1 - y0 - lg.height) // 2), lg)
            return
        except Exception:
            log.exception("logo load failed")
    d = ImageDraw.Draw(img)
    f = F(40, True)
    tw = tlen("CR", f)
    tdraw(d, (x0 + x1 - tw) / 2, (y0 + y1) / 2 + 14, "CR", f, (40, 40, 40))


def _footer(img, markup):
    rrect(img, (24, 1344, 1056, 1420), 28, BAR)
    _logo(img, (44, 1330, 132, 1432))
    lines, size, lh = fit_text(markup, frozenset(), 880, 70, 34, 24, 1.3)
    draw_lines(img, lines, size, lh, 1032, 160, 1344 + (76 - len(lines) * lh) / 2, "center", False, WHITE)


def _frame(img, src, frame_box, mode="cover"):
    rrect(img, frame_box, 44, FRAME)
    x0, y0, x1, y1 = frame_box
    paste_image(img, src, (x0 + 18, y0 + 16, x1 - 18, y1 - 16), 36, mode)


def _card(img, box):
    rrect(img, box, 48, CARD)


def _footer_cta(kw):
    return f"برای دریافت **لینک دانلود** و تماشا کلمه [[{kw}]] رو کامنت کنید!"


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
    _frame(img, src, (68, 340, 1012, 960))
    _card(img, (85, 990, 995, 1312))
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
    text_block(img, "\n".join(parts), _bold_names(d), (85, 990, 995, 1312), 38, 24,
               justify=False, lh_ratio=1.5, pad=(36, 16), valign="middle", names=_names(d))
    _footer(img, _footer_cta(kw))
    return img


def _text_slide(d, src, kw, heading, body):
    img = Image.new("RGB", (W, H), BG)
    _heading(img, heading)
    _frame(img, src, (68, 330, 1012, 800))
    _card(img, (85, 860, 995, 1215))
    text_block(img, body, _bold_names(d), (85, 860, 995, 1215), 40, 28, justify=True, names=_names(d))
    _footer(img, _footer_cta(kw))
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
    _footer(img, _footer_cta(kw))
    return img


def slide_final(d, src, kw):
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)
    _frame(img, src, (68, 50, 1012, 770), mode="contain")
    this = "این فیلم" if d["kind"] == "فیلم" else "این سریال"
    f1, f2 = F(54, True), F(54, True)
    l1, l2 = "برای دریافت لینک دانلود", f"و تماشای {this}"
    tdraw(dr, 540 - tlen(l1, f1) / 2, 880, l1, f1, TEXT)
    tdraw(dr, 540 - tlen(l2, f2) / 2, 952, l2, f2, TEXT)
    l3 = "زیر همین پست کامنت کن"
    f3 = F(36, False)
    tdraw(dr, 540 - tlen(l3, f3) / 2, 1030, l3, f3, MUTED)
    rrect(img, (270, 1060, 810, 1270), 40, WHITE, outline=ACCENT, ow=5)
    for size in range(120, 44, -4):
        fk = F(size, True)
        if tlen(kw, fk) <= 470:
            break
    tdraw(dr, 540 - tlen(kw, fk) / 2, 1165 + size * 0.32, kw, fk, TEXT)
    _footer(img, "[[@cinamareport]] معرفی فیلم و سریال بدون اسپویل")
    return img


# ---------------------------------------------------------------- public API
def build_slides(data, images, keyword):
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


def register(application):
    """هندلرها را در گروه -1 ثبت می‌کند تا قبل از هندلرهای فعلی ربات اجرا شوند.
    تا وقتی کاربر وسط جریان /insta نباشد، هیچ پیامی را نمی‌گیرد."""
    from telegram import InputMediaDocument, InputMediaPhoto
    from telegram.ext import (ApplicationHandlerStop, CommandHandler, MessageHandler, filters)

    async def cmd_start(update, context):
        if not _allowed(update):
            return
        context.user_data["insta"] = {"step": "post", "imgs": {}, "queue": list(IMG_STEPS)}
        await update.message.reply_text(
            "پست کانال را کپی/فوروارد کن (می‌توانی خط‌های اختیاری هم اضافه کنی):\n"
            "Metacritic: 74\n"
            "نمرات قسمت‌ها: 7.9 8.1 8.2 ...\n\n"
            "برای انصراف: /insta_cancel"
        )
        raise ApplicationHandlerStop

    async def cmd_cancel(update, context):
        if context.user_data.pop("insta", None) is not None:
            await update.message.reply_text("ساخت پست اینستاگرام لغو شد.")
            raise ApplicationHandlerStop

    async def on_message(update, context):
        st = context.user_data.get("insta")
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
                    st["step"] = "kw"
                    await msg.reply_text(
                        f"✅ {dd['title']} ({dd['year']}) خوانده شد.\n"
                        f"IMDb: {dd['imdb']} | RT: {dd['rt']} | Meta: {dd['meta']} | "
                        f"قسمت‌ها: {len(dd['episodes'])}\n\n"
                        "کلمه کامنت را بفرست (مثلاً: خون):"
                    )
            elif st["step"] == "kw":
                if not msg.text:
                    await msg.reply_text("کلمه کامنت را به صورت متن بفرست.")
                else:
                    st["kw"] = msg.text.strip()
                    st["step"] = "imgs"
                    await msg.reply_text(f"حالا {st['queue'][0][1]} را بفرست:")
            elif st["step"] == "imgs":
                data = None
                if msg.photo:
                    f = await msg.photo[-1].get_file()
                    data = bytes(await f.download_as_bytearray())
                elif msg.document and (msg.document.mime_type or "").startswith("image/"):
                    f = await msg.document.get_file()
                    data = bytes(await f.download_as_bytearray())
                if data is None:
                    await msg.reply_text("لطفاً یک عکس بفرست.")
                else:
                    idx, _ = st["queue"].pop(0)
                    st["imgs"][idx] = data
                    if st["queue"]:
                        await msg.reply_text(f"حالا {st['queue'][0][1]} را بفرست:")
                    else:
                        await msg.reply_text("⏳ در حال ساخت اسلایدها...")
                        slides = await asyncio.to_thread(build_slides, st["data"], st["imgs"], st["kw"])
                        context.user_data.pop("insta", None)
                        await msg.reply_media_group([InputMediaPhoto(s) for s in slides])
                        files = []
                        for i, s in enumerate(slides, 1):
                            bio = io.BytesIO(s)
                            bio.name = f"slide_{i}.jpg"
                            files.append(InputMediaDocument(bio))
                        await msg.reply_media_group(files)
                        await msg.reply_text("✅ آماده شد. نسخه دوم (فایل) با کیفیت کامل است.")
        except ApplicationHandlerStop:
            raise
        except Exception as e:
            log.exception("insta failed")
            context.user_data.pop("insta", None)
            await msg.reply_text(f"❌ خطا در ساخت پست: {e}")
        raise ApplicationHandlerStop

    application.add_handler(CommandHandler("insta", cmd_start), group=-1)
    application.add_handler(CommandHandler("insta_cancel", cmd_cancel), group=-1)
    application.add_handler(
        MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.IMAGE,
                       on_message),
        group=-1,
    )
