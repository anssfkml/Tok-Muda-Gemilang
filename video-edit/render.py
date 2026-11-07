"""Draw the TikTok overlays (frosted-glass cards, room labels, watermark, CTA cursor)
on top of base.mp4 and encode the final video.

usage: python3 render.py <base.mp4> <contact_photo.jpg> <out.mp4> [--frames a:b] [--stills dir t1,t2,...]
"""
import math
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from timeline import FPS, H, SAFE_B, SAFE_L, SAFE_R, SAFE_T, TOTAL, W, seg_times

FONT_DIR = "/usr/share/fonts/opentype/inter/"
SYM = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def F(name, size):
    return ImageFont.truetype(FONT_DIR + name, size)


BLACK = lambda s: F("InterDisplay-Black.otf", s)
XBOLD = lambda s: F("InterDisplay-ExtraBold.otf", s)
BOLD = lambda s: F("InterDisplay-Bold.otf", s)
SEMI = lambda s: F("Inter-SemiBold.otf", s)
MED = lambda s: F("Inter-Medium.otf", s)

WHITE = (255, 255, 255, 255)
SOFT = (255, 255, 255, 215)
GOLD = (255, 212, 92, 255)
GREEN = (37, 211, 102, 255)
RED = (255, 77, 77, 255)
TINT = (16, 20, 28, 105)        # smoky frosted glass
BORDER = (255, 255, 255, 95)
RADIUS = 38
CX = (SAFE_L + SAFE_R) // 2 + 20  # visual centre of the TikTok safe zone (x=520)
MAXW = 2 * (SAFE_R - CX)          # 840

T = seg_times()


# ----------------------------------------------------------------- drawing helpers
def text_w(font, s):
    return font.getbbox(s)[2] - font.getbbox(s)[0] if s else 0


def shadow_text(d, xy, s, font, fill, anchor="la", sh=110):
    x, y = xy
    d.text((x, y + 3), s, font=font, fill=(0, 0, 0, sh), anchor=anchor)
    d.text((x, y), s, font=font, fill=fill, anchor=anchor)


def round_mask(w, h, r=RADIUS):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    return m


def glass_fg(w, h, r=RADIUS, tint=TINT):
    """Tint + highlight + hairline border of a frosted card (text is drawn on top)."""
    fg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(fg)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, fill=tint)
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # soft top sheen
    hd = ImageDraw.Draw(hl)
    for i in range(h // 2):
        hd.line((0, i, w, i), fill=(255, 255, 255, int(26 * (1 - i / (h / 2)))))
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (w, h), 0), round_mask(w, h, r)))
    fg.alpha_composite(hl)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, outline=BORDER, width=2)
    return fg


def shadow_img(w, h, r=RADIUS, pad=40):
    s = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), r, fill=(0, 0, 0, 90))
    return s.filter(ImageFilter.GaussianBlur(18)), pad


class Card:
    """A frosted card: static fg (tint, border, content) + live blurred background."""

    def __init__(self, t0, t1, w, h, x=None, y=None, zone="upper", r=RADIUS, slide=40):
        self.t0, self.t1, self.w, self.h, self.r, self.slide = t0, t1, w, h, r, slide
        self.x = CX - w // 2 if x is None else x
        if y is None:
            y = SAFE_T + 20 if zone == "upper" else SAFE_B - 10 - h
        self.y = y
        self.fg = glass_fg(w, h, r)
        self.d = ImageDraw.Draw(self.fg)
        self.mask = round_mask(w, h, r)
        self.shadow, self.spad = shadow_img(w, h, r)

    def alpha(self, t):
        a_in = min(1.0, max(0.0, (t - self.t0) / 0.35))
        a_out = min(1.0, max(0.0, (self.t1 - t) / 0.25))
        a_in = 1 - (1 - a_in) ** 3  # ease-out
        return min(a_in, a_out), (1 - a_in) * self.slide

    def draw(self, frame, t):
        if not (self.t0 <= t < self.t1):
            return
        a, dy = self.alpha(t)
        if a <= 0:
            return
        x, y = self.x, int(self.y + dy)
        frame.paste(self.shadow, (x - self.spad, y - self.spad), scale_alpha(self.shadow, a))
        region = frame.crop((x, y, x + self.w, y + self.h))
        small = region.resize((max(1, self.w // 8), max(1, self.h // 8)), Image.BILINEAR)
        blur = small.filter(ImageFilter.GaussianBlur(2.2)).resize((self.w, self.h), Image.BICUBIC)
        frame.paste(blur, (x, y), scale_alpha(self.mask, a))
        frame.paste(self.fg, (x, y), scale_alpha(self.fg, a))


def scale_alpha(img, a):
    ch = img if img.mode == "L" else img.getchannel("A")
    if a >= 0.999:
        return ch
    return ch.point(lambda v: int(v * a))


# ------------------------------------------------------------------- card builders
def text_card(t0, t1, lines, zone="upper", w=None, pad=40, y=None, align="center"):
    """lines: list of (text, font, color, gap_after)."""
    widths = [text_w(f, s) for s, f, _, _ in lines]
    w = w or min(MAXW, max(widths) + 2 * pad)
    hts = [f.getbbox("ÁgHy")[3] - f.getbbox("ÁgHy")[1] for _, f, _, _ in lines]
    h = pad * 2 + sum(hts) + sum(g for *_, g in lines[:-1])
    c = Card(t0, t1, w, h, zone=zone, y=y)
    yy = pad
    for (s, f, col, g), lh in zip(lines, hts):
        top = f.getbbox("ÁgHy")[1]
        x = w // 2 if align == "center" else pad
        shadow_text(c.d, (x, yy - top), s, f, col, anchor="ma" if align == "center" else "la")
        yy += lh + g
    return c


def pill(d, xy, s, font, fill, txt=(255, 255, 255, 255), padx=22, pady=12):
    x, y = xy
    tw = text_w(font, s)
    bb = font.getbbox("HAgy")
    h = bb[3] - bb[1] + 2 * pady
    d.rounded_rectangle((x, y, x + tw + 2 * padx, y + h), h // 2, fill=fill)
    d.text((x + padx, y + pady - bb[1]), s, font=font, fill=txt)
    return tw + 2 * padx, h


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=fill)


def check(d, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    d.line((cx - r * 0.45, cy + r * 0.02, cx - r * 0.1, cy + r * 0.38, cx + r * 0.5, cy - r * 0.35),
           fill=(16, 20, 28, 255), width=max(3, int(r * 0.28)), joint="curve")


def pin(d, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r * 1.6, cx + r, cy + r * 0.4), fill=fill)
    d.polygon([(cx - r * 0.82, cy - r * 0.2), (cx + r * 0.82, cy - r * 0.2), (cx, cy + r * 1.3)], fill=fill)
    d.ellipse((cx - r * 0.4, cy - r * 1.0, cx + r * 0.4, cy - r * 0.2), fill=(16, 20, 28, 255))


def list_card(t0, t1, title, items, zone, icon="check", w=MAXW, f_item=None, row=56, pad=38):
    f_t = BLACK(46)
    f_item = f_item or SEMI(36)
    h = pad + 56 + 18 + row * len(items) + pad - 12
    c = Card(t0, t1, w, h, zone=zone)
    d = c.d
    shadow_text(d, (pad, pad - f_t.getbbox("A")[1]), title, f_t, GOLD)
    yy = pad + 56 + 18
    for s in items:
        cy = yy + row // 2 - 4
        if icon == "star":
            star(d, pad + 18, cy, 17, GOLD)
        else:
            check(d, pad + 18, cy, 16, GREEN)
        top = f_item.getbbox("Ag")
        d.text((pad + 52, cy - (top[1] + top[3]) / 2), s, font=f_item, fill=WHITE)
        yy += row
    return c


# ---------------------------------------------------------------- build the cards
def build(photo_path):
    cards = []
    t = T

    # 1. HOOK -------------------------------------------------------------------
    cards.append(text_card(0.15, t["door"][0] + 0.8, [
        ("Bangun pagi,", XBOLD(84), WHITE, 10),
        ("ini view bilik tidur kau…", XBOLD(68), WHITE, 0),
    ], zone="upper", pad=36))

    # 2. SCHOOL REVEAL ------------------------------------------------------------
    s0 = t["door"][0] + 1.0
    c = text_card(s0, t["door"][1], [
        ("PADANG SEKOLAH!", BLACK(84), GOLD, 14),
        ("Rumah betul-betul sebelah sekolah", SEMI(40), WHITE, 0),
    ], zone="upper", pad=36)
    cards.append(c)

    # 3. OPENING / PROJECT --------------------------------------------------------
    a, b = t["open"]
    w, h, pad = MAXW, 420, 38
    c = Card(a + 0.1, b, w, h, zone="upper")
    d = c.d
    bw, bh = pill(d, (0, 0), "DIBUKA UNTUK PENDAFTARAN!!", BLACK(40), RED, padx=26, pady=16)
    c.fg = glass_fg(w, h)  # redraw clean, then centre the pill
    d = c.d = ImageDraw.Draw(c.fg)
    pill(d, ((w - bw) // 2, pad), "DIBUKA UNTUK PENDAFTARAN!!", BLACK(40), RED, padx=26, pady=16)
    yy = pad + bh + 30
    shadow_text(d, (w // 2, yy), "PROJEK PERUMAHAN BARU", SEMI(34), SOFT, anchor="ma")
    yy += 52
    shadow_text(d, (w // 2, yy), "Rumah Teres 2-Tingkat", BLACK(70), WHITE, anchor="ma")
    yy += 96
    f = BOLD(48)
    lbl = "Tok Muda, Kapar"
    lw = text_w(f, lbl) + 50
    pin(d, w // 2 - lw // 2 + 16, yy + 30, 15, GOLD)
    shadow_text(d, (w // 2 - lw // 2 + 50, yy), lbl, f, GOLD)
    cards.append(c)

    # 4. FREEHOLD -----------------------------------------------------------------
    a, b = t["title"]
    w, h = MAXW, 250
    c = Card(a + 0.1, b, w, h, zone="upper")
    d = c.d
    f = BLACK(46)
    chips = [("FREEHOLD", GOLD, (16, 20, 28, 255)), ("Open Title", (255, 255, 255, 235), (16, 20, 28, 255))]
    tot = sum(text_w(f, s) + 52 for s, *_ in chips) + 20
    xx = (w - tot) // 2
    for s, bg, fgc in chips:
        cw, ch = pill(d, (xx, 40), s, f, bg, txt=fgc, padx=26, pady=16)
        xx += cw + 20
    shadow_text(d, (w // 2, 40 + ch + 28), "OPEN TO ALL", BLACK(64), WHITE, anchor="ma")
    cards.append(c)

    # 5. PRICE --------------------------------------------------------------------
    a, b = t["price"]
    cards.append(text_card(a + 0.1, b, [
        ("Harga Dari", SEMI(40), SOFT, 6),
        ("RM439,200", BLACK(120), GOLD, 10),
        ("nett  •  Intermediate Lot", SEMI(38), WHITE, 0),
    ], zone="lower", w=MAXW, pad=38))

    # 6. INTERIOR: room labels + specs ---------------------------------------------
    rooms = [("hall", "Ruang Tamu"), ("kitchen", "Dapur"), ("bath1", "Bilik Air"),
             ("stairs", "Naik atas…"), ("bed", "Bilik Tidur"), ("bath2", "Bilik Air")]
    for sid, name in rooms:
        a, b = t[sid]
        f = BOLD(46)
        lw = text_w(f, name) + 64
        c = Card(a + 0.05, b - 0.02, lw, 92, x=SAFE_L + 10, y=SAFE_T + 20, r=46, slide=0)
        c.d.ellipse((24, 38, 40, 54), fill=GOLD)
        bb = f.getbbox("Ag")
        c.d.text((50, 46 - (bb[1] + bb[3]) / 2), name, font=f, fill=WHITE)
        cards.append(c)

    i0, i1 = t["hall"][0], t["bath2"][1]
    mid = t["stairs"][0]
    # specs A: rooms count
    w, h = MAXW, 230
    c = Card(i0 + 0.2, mid, w, h, zone="lower")
    d = c.d
    for k, (num, lab) in enumerate([("4", "Bilik Tidur"), ("3", "Bilik Air")]):
        cx = w // 4 + k * w // 2
        shadow_text(d, (cx, 30), num, BLACK(110), GOLD, anchor="ma")
        shadow_text(d, (cx, 160), lab, BOLD(42), WHITE, anchor="ma")
    d.line((w // 2, 50, w // 2, h - 50), fill=(255, 255, 255, 90), width=2)
    cards.append(c)
    # specs B: sizes + completion
    rows = [("Saiz Tanah", "1,194 sqft (20'x60')"), ("Saiz Binaan", "1,359 sqft"),
            ("Dijangka Siap", "Mei 2027")]
    w, h, pad, rh = MAXW, 2 * 36 + 3 * 74 - 14, 36, 74
    c = Card(mid + 0.05, i1, w, h, zone="lower")
    d = c.d
    for k, (lab, val) in enumerate(rows):
        yy = pad + k * rh
        shadow_text(d, (pad, yy + 6), lab, SEMI(36), SOFT)
        shadow_text(d, (w - pad, yy), val, BLACK(46), GOLD if k == 2 else WHITE, anchor="ra")
        if k < 2:
            d.line((pad, yy + rh - 12, w - pad, yy + rh - 12), fill=(255, 255, 255, 50), width=2)
    cards.append(c)

    # 7. PACKAGE ------------------------------------------------------------------
    a, b = t["package"]
    cards.append(list_card(a + 0.1, b, "PAKEJ ISTIMEWA", [
        "BOOKING RM1000 sahaja!!", "FREE SPA Legal Fee", "FREE MOT", "Zero Deposit"],
        zone="lower", icon="star", f_item=BOLD(40), row=62))

    # 8. AMENITIES ----------------------------------------------------------------
    a, b = t["amenity"]
    cards.append(list_card(a + 0.1, b, "KEMUDAHAN BERDEKATAN", [
        "Masjid Al-Ehsan Kampung Tok Muda", "SRA Kampung Tok Muda", "Sek Keb Tok Muda",
        "SMK Tengku Idris, Pekan Kapar", "Sek Men Islam Hira'", "Klinik Kesihatan Tok Muda",
        "99 Speedmart"], zone="upper", f_item=SEMI(34), row=54))

    # 9. ACCESS -------------------------------------------------------------------
    a, b = t["access"]
    items = ["Pekan Kapar", "Shah Alam", "Setia Alam", "Federal Highway", "WCE", "NKVE"]
    w, pad = MAXW, 36
    f = BOLD(36)
    ch = f.getbbox("HAgy")[3] - f.getbbox("HAgy")[1] + 28
    h = pad + 56 + 22 + 3 * (ch + 16) - 16 + pad
    c = Card(a + 0.1, b, w, h, zone="lower")
    d = c.d
    shadow_text(d, (pad, pad - BLACK(46).getbbox("A")[1]), "AKSES MUDAH", BLACK(46), GOLD)
    colw = (w - 2 * pad - 16) // 2
    for k, s in enumerate(items):
        xx = pad + (k % 2) * (colw + 16)
        yy = pad + 56 + 22 + (k // 2) * (ch + 16)
        d.rounded_rectangle((xx, yy, xx + colw, yy + ch), ch // 2, fill=(255, 255, 255, 38),
                            outline=(255, 255, 255, 70), width=2)
        bb = f.getbbox("HAgy")
        d.text((xx + colw // 2, yy + ch // 2 - (bb[1] + bb[3]) / 2 + bb[1]), s, font=f, fill=WHITE, anchor="ma")
    cards.append(c)

    # 10. CTA ---------------------------------------------------------------------
    a, b = t["cta"]
    # contact card (upper)
    w, h = MAXW, 600
    c = Card(a + 0.1, b + 1, w, h, zone="upper")
    d = c.d
    ph = ImageOps.exif_transpose(Image.open(photo_path)).convert("RGB")
    pw, phh = ph.size
    cx_, cy_, sz = int(pw * 0.47), int(phh * 0.585), int(pw * 0.46)
    ph = ph.crop((cx_ - sz // 2, cy_ - sz // 2, cx_ + sz // 2, cy_ + sz // 2)).resize((280, 280), Image.LANCZOS)
    ring = 300
    d.ellipse(((w - ring) // 2, 34, (w + ring) // 2, 34 + ring), fill=GOLD)
    m = Image.new("L", (280, 280), 0)
    ImageDraw.Draw(m).ellipse((0, 0, 279, 279), fill=255)
    c.fg.paste(ph, ((w - 280) // 2, 44), m)
    yy = 34 + ring + 26
    shadow_text(d, (w // 2, yy), "Hubungi Anis", BLACK(68), WHITE, anchor="ma")
    shadow_text(d, (w // 2, yy + 92), "untuk viewing & booking", SEMI(40), SOFT, anchor="ma")
    shadow_text(d, (w // 2, yy + 152), "BOOKING RM1000 sahaja!!", BOLD(40), GOLD, anchor="ma")
    cards.append(c)

    # price + WhatsApp button (lower)
    w, h = MAXW, 330
    c = Card(a + 0.4, b + 1, w, h, zone="lower")
    d = c.d
    shadow_text(d, (w // 2, 30), "HARGA DARI", SEMI(36), SOFT, anchor="ma")
    shadow_text(d, (w // 2, 74), "RM439,200", BLACK(96), GOLD, anchor="ma")
    cards.append(c)
    btn = (c.x + 40, c.y + 196, c.x + w - 40, c.y + 196 + 104)
    return cards, btn


# --------------------------------------------------------------- CTA button + cursor
def wa_icon(size):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    d.ellipse((s * 0.06, s * 0.06, s * 0.94, s * 0.94), outline=WHITE, width=max(3, s // 12))
    d.polygon([(s * 0.12, s * 0.95), (s * 0.2, s * 0.7), (s * 0.36, s * 0.86)], fill=WHITE)
    # handset
    d.rounded_rectangle((s * 0.33, s * 0.28, s * 0.45, s * 0.42), s * 0.05, fill=WHITE)
    d.rounded_rectangle((s * 0.56, s * 0.57, s * 0.72, s * 0.68), s * 0.05, fill=WHITE)
    d.arc((s * 0.30, s * 0.28, s * 0.74, s * 0.72), 90, 190, fill=WHITE, width=max(4, s // 9))
    return im


def make_button(bx0, by0, bx1, by1, pressed=False):
    w, h = bx1 - bx0, by1 - by0
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = (28, 178, 86, 255) if pressed else GREEN
    d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=col)
    f = BLACK(46)
    s = "WA Anis: 016-602 9067"
    tw = text_w(f, s)
    ic = wa_icon(56)
    x0 = (w - tw - 56 - 16) // 2
    im.alpha_composite(ic, (x0, (h - 56) // 2))
    bb = f.getbbox("0A")
    d.text((x0 + 72, h / 2 - (bb[1] + bb[3]) / 2), s, font=f, fill=WHITE)
    return im


def make_cursor(scale=1.0):
    s = 4  # supersample
    pts = [(0, 0), (0, 52), (13, 40), (22, 61), (31, 57), (22, 37), (39, 37)]
    k = 1.55 * scale
    big = Image.new("RGBA", (int(80 * k * s), int(90 * k * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    P = [((x + 6) * k * s, (y + 6) * k * s) for x, y in pts]
    d.polygon(P, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=int(3.2 * k * s))
    im = big.resize((big.width // s, big.height // s), Image.LANCZOS)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.putalpha(im.getchannel("A").point(lambda v: int(v * 0.45)))
    out = Image.new("RGBA", (im.width + 12, im.height + 12), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)), (8, 8))
    out.alpha_composite(im, (0, 0))
    return out


def ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3 if x < 1 else 1.0


class CTA:
    def __init__(self, btn, t_card):
        self.btn = btn
        self.t0 = t_card + 0.6           # button appears
        self.t_move = t_card + 1.5       # cursor starts moving
        self.t_click = t_card + 2.6      # click
        self.up = make_button(*btn)
        self.down = make_button(*btn, pressed=True)
        self.cur = make_cursor()
        self.cur_down = make_cursor(0.88)

    def draw(self, frame, t):
        if t < self.t0:
            return
        bx0, by0, bx1, by1 = self.btn
        a = ease((t - self.t0) / 0.35)
        pressed = self.t_click <= t < self.t_click + 0.22
        # gentle pulse after click to keep attention
        b = self.down if pressed else self.up
        frame.paste(b, (bx0, by0 + int((1 - a) * 30)), scale_alpha(b, a))
        # ripple
        if self.t_click <= t < self.t_click + 0.7:
            p = (t - self.t_click) / 0.7
            cx, cy = self.target()
            r = int(30 + 140 * p)
            rip = Image.new("RGBA", (2 * r + 8, 2 * r + 8), (0, 0, 0, 0))
            ImageDraw.Draw(rip).ellipse((4, 4, 2 * r + 4, 2 * r + 4), outline=(255, 255, 255, int(230 * (1 - p))),
                                         width=8)
            frame.paste(rip, (cx - r - 4, cy - r - 4), rip)
        # cursor
        if t >= self.t_move:
            p = ease((t - self.t_move) / 1.0)
            sx, sy = 1010, 1780  # enters from bottom-right
            tx, ty = self.target()
            # slight arc
            x = sx + (tx - sx) * p
            y = sy + (ty - sy) * p - math.sin(p * math.pi) * 60
            cimg = self.cur_down if pressed else self.cur
            frame.paste(cimg, (int(x), int(y)), cimg)

    def target(self):
        bx0, by0, bx1, by1 = self.btn
        return int(bx1 - 34), int((by0 + by1) / 2 + 14)


# --------------------------------------------------------------------- watermark
def make_watermark():
    f = SEMI(62)
    s = "aniskamalrealty"
    tw = text_w(f, s)
    im = Image.new("RGBA", (tw + 40, 110), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((22, 22), s, font=f, fill=(0, 0, 0, 40))
    d.text((20, 20), s, font=f, fill=(255, 255, 255, 80))
    return im


# --------------------------------------------------------------------------- main
def main():
    base, photo, out = sys.argv[1:4]
    frames = None
    stills = None
    args = sys.argv[4:]
    if "--frames" in args:
        a, b = args[args.index("--frames") + 1].split(":")
        frames = (int(a), int(b))
    if "--stills" in args:
        i = args.index("--stills")
        stills = (args[i + 1], [float(x) for x in args[i + 2].split(",")])

    cards, btn = build(photo)
    cta = CTA(btn, T["cta"][0] + 0.4)
    wm = make_watermark()
    wm_xy = (W // 2 - wm.width // 2, H // 2 - wm.height // 2)

    def compose(img, t):
        img.paste(wm, wm_xy, wm)
        for c in cards:
            c.draw(img, t)
        cta.draw(img, t)
        return img

    if stills:
        outdir, ts = stills
        for t in ts:
            n = int(round(t * FPS))
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / FPS:.4f}", "-i", base, "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
            img = Image.frombytes("RGB", (W, H), raw)
            compose(img, t).save(f"{outdir}/still_{t:05.2f}.jpg", quality=90)
        return

    n_total = int(round(TOTAL * FPS))
    f0, f1 = frames or (0, n_total)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{f0 / FPS:.4f}", "-i", base, "-frames:v", str(f1 - f0),
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                            "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out],
                           stdin=subprocess.PIPE)
    fsize = W * H * 3
    for n in range(f0, f1):
        raw = dec.stdout.read(fsize)
        if len(raw) < fsize:
            break
        img = Image.frombytes("RGB", (W, H), raw)
        enc.stdin.write(compose(img, n / FPS).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()


if __name__ == "__main__":
    main()
