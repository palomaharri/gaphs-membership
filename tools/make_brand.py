"""Generate the GAPHS logo files and launch icons (Option 05, The Roofmark, Sans).

Run from the project folder:  python tools/make_brand.py
Writes to static/img/ and static/icons/. Text is converted to outlines, so the
files look the same everywhere, with or without the fonts installed.
"""
import io
import os
import sys

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "tools", "fonts")
IMG = os.path.join(ROOT, "static", "img")
ICONS = os.path.join(ROOT, "static", "icons")

GOLD = "#B8963E"
NOIR = "#1A1A1A"
WHITE = "#FFFFFF"
STONE = "#888888"
PARCHMENT = "#F5F1E8"

_fonts = {}


def font(weight=200):
    if weight not in _fonts:
        f = TTFont(os.path.join(FONT_DIR, "Montserrat.ttf"))
        _fonts[weight] = instantiateVariableFont(f, {"wght": weight})
    return _fonts[weight]


def glyph_name(f, ch):
    return f.getBestCmap()[ord(ch)]


def text_paths(text, size, x, baseline, tracking=0.0, weight=200):
    """Return ([(char, path_d, ink_bounds)], total_advance) for text set at size px."""
    f = font(weight)
    gs = f.getGlyphSet()
    upm = f["head"].unitsPerEm
    s = size / upm
    out = []
    cx = x
    for i, ch in enumerate(text):
        if ch == " ":
            cx += gs[glyph_name(f, " ")].width * s + tracking
            continue
        g = gs[glyph_name(f, ch)]
        pen = SVGPathPen(gs)
        g.draw(TransformPen(pen, (s, 0, 0, -s, cx, baseline)))
        bp = BoundsPen(gs)
        g.draw(TransformPen(bp, (s, 0, 0, -s, cx, baseline)))
        out.append((ch, pen.getCommands(), bp.bounds))
        cx += g.width * s + (tracking if i < len(text) - 1 else 0)
    return out, cx - x


def cap_height(size, weight=200):
    f = font(weight)
    return f["OS/2"].sCapHeight * size / f["head"].unitsPerEm


def roof_points(gb, size, overhang=0.06, rise=0.25, gap=0.10):
    """Chevron over the G: feet slightly wider than the G's ink, centred on it."""
    x0, y0, x1, y1 = gb  # y0 is the top of the G (SVG y grows down)
    w = x1 - x0
    left, right = x0 - w * overhang, x1 + w * overhang
    foot = y0 - size * gap
    peak = foot - size * rise
    return left, foot, (left + right) / 2, peak, right, foot


def logo_svg(aphs_color, sub_color, subtitle=True, bg=None, pad=24):
    """The full lockup. Returns (svg_text, width, height)."""
    size = 100.0
    tracking = size * 0.13 * 1.25
    baseline = 200.0
    glyphs, adv = text_paths("GAPHS", size, 0, baseline, tracking)
    gb = glyphs[0][2]
    l, fy, px, py, r, _ = roof_points((gb[0], gb[1], gb[2], gb[3]), size)
    stroke = size * 0.022
    # ink extents of the word
    word_l = min(g[2][0] for g in glyphs)
    word_r = max(g[2][2] for g in glyphs)
    rule_y = baseline + size * 0.26
    rule_ext = (word_r - word_l) * 0.07
    parts = []
    parts.append(
        f'<polyline points="{l:.2f},{fy:.2f} {px:.2f},{py:.2f} {r:.2f},{fy:.2f}" fill="none" '
        f'stroke="{GOLD}" stroke-width="{stroke:.2f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    for ch, d, _ in glyphs:
        parts.append(f'<path d="{d}" fill="{GOLD if ch == "G" else aphs_color}"/>')
    min_x = min(l, word_l - rule_ext) - pad
    max_x = max(r, word_r + rule_ext) + pad
    min_y = py - stroke - pad
    max_y = baseline + pad
    if subtitle:
        parts.append(
            f'<line x1="{word_l - rule_ext:.2f}" y1="{rule_y:.2f}" x2="{word_r + rule_ext:.2f}" '
            f'y2="{rule_y:.2f}" stroke="{GOLD}" stroke-width="{size * 0.012:.2f}"/>'
        )
        sub_size = size * 0.115
        sub_track = sub_size * 0.42
        centre = (word_l + word_r) / 2
        y = rule_y + sub_size * 2.1
        for line in ("GLOBAL ASSOCIATION OF", "PROFESSIONAL HOME STAGERS"):
            g2, a2 = text_paths(line, sub_size, 0, y, sub_track, weight=300)
            off = centre - a2 / 2
            for _, d, _b in g2:
                parts.append(f'<path transform="translate({off:.2f},0)" d="{d}" fill="{sub_color}"/>')
            y += sub_size * 1.75
        max_y = y - sub_size * 1.75 + pad
    w, h = max_x - min_x, max_y - min_y
    bg_rect = f'<rect x="{min_x:.2f}" y="{min_y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{bg}"/>' if bg else ""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.2f} {min_y:.2f} {w:.2f} {h:.2f}" '
        f'width="{w:.0f}" height="{h:.0f}" role="img" aria-label="GAPHS, Global Association of Professional Home Stagers">'
        f"{bg_rect}{''.join(parts)}</svg>"
    )
    return svg, w, h


def stem_width(size, weight):
    """Width of a vertical stem (the letter I) so the roof line matches the G's weight."""
    (_, _, b), = text_paths("I", size, 0, 0, weight=weight)[0]
    return b[2] - b[0]


def mark_svg(bg=None, canvas=1024, scale=0.58, radius=0.0, color=GOLD, weight=200):
    """The G with its roofmark, optically centred in a square. scale = G+roof height / canvas."""
    size = 100.0
    glyphs, _ = text_paths("G", size, 0, 200, weight=weight)
    _, d, gb = glyphs[0]
    l, fy, px, py, r, _ = roof_points(gb, size, overhang=0.07, rise=0.27, gap=0.12)
    stroke = stem_width(size, weight) * 0.92
    top = py - stroke / 2
    bottom = gb[3]
    left = min(l, gb[0]) - stroke / 2
    right = max(r, gb[2]) + stroke / 2
    group_h = bottom - top
    k = canvas * scale / group_h
    gw = (right - left) * k
    # optical centring: nudge the group slightly up so the heavier G sits balanced
    tx = (canvas - gw) / 2 - left * k
    ty = (canvas - group_h * k) / 2 - top * k - canvas * 0.01
    rect = ""
    if bg:
        rx = canvas * radius
        rect = f'<rect width="{canvas}" height="{canvas}" rx="{rx:.1f}" fill="{bg}"/>'
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}" width="{canvas}" height="{canvas}">'
        f"{rect}<g transform=\"translate({tx:.2f},{ty:.2f}) scale({k:.5f})\">"
        f'<polyline points="{l:.2f},{fy:.2f} {px:.2f},{py:.2f} {r:.2f},{fy:.2f}" fill="none" stroke="{color}" '
        f'stroke-width="{stroke:.2f}" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="{d}" fill="{color}"/></g></svg>'
    )
    return svg


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def png(svg, path, width=None, height=None):
    import cairosvg

    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=width, output_height=height)


def main():
    os.makedirs(IMG, exist_ok=True)
    os.makedirs(ICONS, exist_ok=True)
    # Lockups
    dark, w, h = logo_svg(WHITE, GOLD)  # for black backgrounds
    light, _, _ = logo_svg(NOIR, STONE)  # for white / parchment backgrounds
    word_dark, ww, wh = logo_svg(WHITE, GOLD, subtitle=False, pad=6)
    word_light, _, _ = logo_svg(NOIR, STONE, subtitle=False, pad=6)
    write(os.path.join(IMG, "gaphs-logo-white.svg"), dark)
    write(os.path.join(IMG, "gaphs-logo-black.svg"), light)
    write(os.path.join(IMG, "gaphs-wordmark-white.svg"), word_dark)
    write(os.path.join(IMG, "gaphs-wordmark-black.svg"), word_light)
    png(dark, os.path.join(IMG, "gaphs-logo-white.png"), width=1200)
    png(light, os.path.join(IMG, "gaphs-logo-black.png"), width=1200)
    email, _, _ = logo_svg(WHITE, GOLD, bg=NOIR, pad=60)
    png(email, os.path.join(IMG, "gaphs-email-header.png"), width=600)
    write(os.path.join(IMG, "gaphs-mark-gold.svg"), mark_svg(weight=300))

    # Launch icons: gold G + roofmark on noir
    # Launch icons use a slightly heavier cut than the wordmark so the mark holds up
    # at home-screen sizes; favicons heavier still so they read at 16-32 px.
    full = mark_svg(bg=NOIR, scale=0.56, weight=300)  # square, full bleed (iOS rounds corners itself)
    rounded = mark_svg(bg=NOIR, scale=0.56, radius=0.2237, weight=300)  # macOS / web style
    maskable = mark_svg(bg=NOIR, scale=0.46, weight=300)  # inside the 80% safe zone for Android
    tiny = mark_svg(bg=NOIR, scale=0.74, radius=0.18, weight=600)
    write(os.path.join(ICONS, "icon.svg"), rounded)
    write(os.path.join(ICONS, "icon-maskable.svg"), maskable)
    png(full, os.path.join(ICONS, "icon-1024.png"), 1024, 1024)
    png(full, os.path.join(ICONS, "apple-touch-icon.png"), 180, 180)
    png(rounded, os.path.join(ICONS, "icon-512.png"), 512, 512)
    png(rounded, os.path.join(ICONS, "icon-192.png"), 192, 192)
    png(maskable, os.path.join(ICONS, "icon-maskable-512.png"), 512, 512)
    png(maskable, os.path.join(ICONS, "icon-maskable-192.png"), 192, 192)
    png(tiny, os.path.join(ICONS, "favicon-32.png"), 32, 32)
    png(tiny, os.path.join(ICONS, "favicon-16.png"), 16, 16)
    from PIL import Image

    big = Image.open(io.BytesIO(__import__("cairosvg").svg2png(bytestring=tiny.encode(), output_width=256, output_height=256)))
    big.save(os.path.join(ICONS, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("Brand files written to static/img and static/icons")


if __name__ == "__main__":
    sys.exit(main())
