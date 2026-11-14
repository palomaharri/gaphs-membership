"""Typographic cover cards in the GAPHS style (noir, burnished gold, parchment).
Type follows brand Option 05: Montserrat 200 for titles, Cormorant Garamond 300 italic for supporting lines.

Used by tools/make_cards.py for the seeded Library and by Admin > Content ("Make a cover")
for anything added later.
"""
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "tools", "fonts")
NOIR, NOIR2 = (26, 26, 26), (36, 36, 36)
GOLD = (184, 150, 62)
PARCHMENT = (245, 241, 232)
STONE = (136, 136, 136)
W, H = 1200, 900


def _font(name, size, weight):
    f = ImageFont.truetype(os.path.join(FONTS, name), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _tracked(draw, xy, text, font, fill, tracking, anchor_center=False):
    x, y = xy
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    if anchor_center:
        x -= total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking
    return total


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _roof(draw, x0, x1, y_feet, rise, color, width):
    cx = (x0 + x1) / 2
    draw.line([(x0, y_feet), (cx, y_feet - rise), (x1, y_feet)], fill=color, width=width, joint="curve")
    for px, py in ((x0, y_feet), (x1, y_feet)):
        r = width / 2
        draw.ellipse([px - r, py - r, px + r, py + r], fill=color)


def _mark(draw, x, y, size, color):
    """Small G + roof, top-left at (x, y); size = cap height in px."""
    f = _font("Montserrat.ttf", int(size * 1.4), 300)
    bbox = draw.textbbox((0, 0), "G", font=f)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    gx, gy = x - bbox[0], y + size * 0.55 - bbox[1]
    draw.text((gx, gy), "G", font=f, fill=color)
    _roof(draw, x - gw * 0.07, x + gw * 1.07, y + size * 0.42, size * 0.38, color, max(2, int(size * 0.07)))


def make_cover(path, title, eyebrow="", subtitle="", style="ebook", number=""):
    bg, fg, sub = NOIR, (255, 255, 255), (205, 198, 182)
    if style == "template":
        bg, fg, sub = PARCHMENT, NOIR, (90, 90, 90)
    elif style == "class":
        bg = NOIR2
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    pad = 96

    # frame hairline
    d.rectangle([40, 40, W - 41, H - 41], outline=GOLD, width=1)

    # big faded mark for courses
    if style == "course":
        ghost = Image.new("RGB", (W, H), bg)
        gd = ImageDraw.Draw(ghost)
        _mark(gd, W - 430, 110, 240, (52, 47, 36))
        im = ghost
        d = ImageDraw.Draw(im)
        d.rectangle([40, 40, W - 41, H - 41], outline=GOLD, width=1)

    _mark(d, pad, pad - 6, 46, GOLD)
    small = _font("Montserrat.ttf", 20, 400)
    _tracked(d, (pad + 100, pad + 30), "GAPHS", small, GOLD if style != "template" else NOIR, 7)

    if number and style == "template":
        numf = _font("Montserrat.ttf", 200, 200)
        nb = d.textbbox((0, 0), number, font=numf)
        d.text((W - pad - (nb[2] - nb[0]) - nb[0], pad - 60), number, font=numf, fill=GOLD)

    # title block, anchored to the bottom
    title_font_size = 92 if len(title) < 32 else 78 if len(title) < 52 else 64
    tf = _font("Montserrat.ttf", int(title_font_size * 0.78), 200)
    lines = _wrap(d, title, tf, W - pad * 2 - (40 if style != "class" else 200))
    line_h = int(title_font_size * 0.78 * 1.28)
    subf = _font("CormorantItalic.ttf", 30, 300)
    sub_lines = _wrap(d, subtitle, subf, W - pad * 2 - 120)[:3] if subtitle else []
    block = len(lines) * line_h + (40 + len(sub_lines) * 36 if sub_lines else 0)
    y = H - pad - block
    if eyebrow:
        ef = _font("Montserrat.ttf", 19, 400)
        _tracked(d, (pad, y - 64), eyebrow.upper(), ef, GOLD, 6)
    for ln in lines:
        d.text((pad, y), ln, font=tf, fill=fg)
        y += line_h
    if sub_lines:
        y += 14
        d.line([(pad, y), (pad + 56, y)], fill=GOLD, width=2)
        y += 26
        for ln in sub_lines:
            d.text((pad, y), ln, font=subf, fill=sub)
            y += 36

    if style == "class":
        cx, cy, r = W - pad - 70, H - pad - 70, 64
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD, width=3)
        d.polygon([(cx - 18, cy - 28), (cx - 18, cy + 28), (cx + 30, cy)], fill=GOLD)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, "JPEG", quality=88, optimize=True, progressive=True)
    return path
