#!/usr/bin/env python3
"""Nông Trại Của TEE — nông trại tự chơi, xuất video dọc 1080x1920 cho TikTok / Shorts.

Cách chạy:
    python farm_bot.py                          # xuất video 50 giây vào output/
    python farm_bot.py --preview 5,20,36        # chỉ xuất vài ảnh PNG để xem nhanh
    python farm_bot.py --seed 25 --out f2.mp4   # một ván khác
    python farm_bot.py --hook "Từ 40 xu lên bao nhiêu?" --duration 30

Luật game:
    - Bắt đầu với `start_money` xu và vài ô đất.
    - Bot mua hạt, gieo, chờ lớn, thu hoạch bán lấy xu, rồi mở thêm ô đất và trồng cây đắt hơn.
    - Sự kiện: trời mưa (cây lớn nhanh gấp đôi) và chợ phiên (giá bán gấp đôi).
"""
import argparse
import math
import random
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ============================================================================
# CONFIG — chỉnh ở đây
# ============================================================================
CONFIG = {
    "game_name": "NÔNG TRẠI CỦA TEE",
    "hook": "50 giây làm giàu từ 40 xu",
    "question": "Ván sau được bao nhiêu xu?\nBình luận dự đoán nhé!",
    "duration": 50,          # giây
    "fps": 30,
    "width": 1080,
    "height": 1920,
    "seed": 7,
    "cols": 4,
    "rows": 5,
    "start_money": 40,
    "start_plots": 4,
    "plot_price": 30,        # giá ô đất thứ nhất mua thêm
    "plot_price_grow": 1.55, # mỗi ô sau đắt hơn bao nhiêu lần
    "rain_every": 14,        # mỗi N giây trời mưa (0 = tắt)
    "rain_len": 4.0,
    "rain_boost": 2.0,       # cây lớn nhanh gấp mấy lần khi mưa
    "market_every": 22,      # mỗi N giây có chợ phiên (0 = tắt)
    "market_len": 5.0,
    "market_boost": 2.0,     # giá bán gấp mấy lần khi chợ phiên
    "end_card": 4.0,
    "audio": False,          # False = video không tiếng (không tạo âm thanh, render nhanh hơn)
    "music_volume": 0.18,
    "sfx_volume": 0.9,
    "crf": 20,
}

# name, giá hạt, giá bán, thời gian lớn (giây), màu quả
CROPS = [
    ("Lúa mì", 5, 12, 2.4, (238, 196, 70)),
    ("Cà rốt", 15, 38, 3.0, (250, 128, 36)),
    ("Ngô", 40, 104, 3.6, (255, 218, 60)),
    ("Cà chua", 100, 265, 4.2, (232, 52, 48)),
    ("Bí ngô", 250, 690, 4.8, (246, 142, 30)),
    ("Dâu tây", 600, 1750, 5.4, (234, 40, 84)),
    ("Dưa hấu", 1500, 4600, 6.0, (58, 168, 72)),
]

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"
SR = 44100
STAGES = 8


# ============================================================================
# Tiện ích
# ============================================================================
@lru_cache(maxsize=None)
def load_font(size, weight="ExtraBold"):
    for p in (ASSETS / "fonts" / "Baloo2.ttf", HERE / "Baloo2.ttf"):
        if p.exists():
            font = ImageFont.truetype(str(p), size)
            try:
                font.set_variation_by_name(weight)
            except Exception:
                pass
            return font
    for p in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    c = 1.7
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def fmt_num(n):
    return f"{int(n):,}".replace(",", ".")


def wrap_text(text, font, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            test = f"{cur} {word}".strip()
            if font.getlength(test) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def draw_lines(draw, cx, cy, lines, font, fill, stroke=6, stroke_fill=(30, 40, 20), gap=1.05):
    lh = font.size * gap
    y0 = cy - lh * (len(lines) - 1) / 2
    for i, line in enumerate(lines):
        draw.text((cx, y0 + i * lh), line, font=font, fill=fill, anchor="mm",
                  stroke_width=stroke, stroke_fill=stroke_fill)


def text_image(lines, font, fill, stroke=7, stroke_fill=(30, 40, 20), gap=1.05):
    lh = int(font.size * gap)
    w = int(max(font.getlength(l) for l in lines)) + stroke * 2 + 20
    h = lh * len(lines) + stroke * 2 + 20
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_lines(ImageDraw.Draw(img), w / 2, h / 2, lines, font, fill, stroke, stroke_fill, gap)
    return img


def star_points(cx, cy, r, inner=0.5, n=5):
    pts = []
    for k in range(n * 2):
        rad = r if k % 2 == 0 else r * inner
        a = math.radians(-90 + 180 / n * k)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


# ============================================================================
# Hình cây trồng, ô đất, nông dân
# ============================================================================
def load_png_asset(name, size):
    p = ASSETS / "nong-trai" / name
    if p.exists():
        return Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    return None


@lru_cache(maxsize=None)
def soil_sprite(size):
    png = load_png_asset("soil.png", size)
    if png is not None:
        return png
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, S * 0.04, S, S], radius=S * 0.12, fill=(96, 62, 36))
    d.rounded_rectangle([0, 0, S, S * 0.96], radius=S * 0.12, fill=(146, 98, 58))
    for k in range(4):
        y = S * (0.22 + 0.2 * k)
        d.rounded_rectangle([S * 0.1, y, S * 0.9, y + S * 0.05], radius=S * 0.025, fill=(118, 78, 44))
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def crop_sprite(ci, stage, size):
    """Cây `ci` ở giai đoạn 0..STAGES (STAGES = chín)."""
    png = load_png_asset(f"crop_{ci}_{stage}.png", size)
    if png is not None:
        return png
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = stage / STAGES
    color = CROPS[ci][4]
    leaf = (74, 170, 64) if ci != 0 or g < 1 else (200, 190, 80)
    leaf_dk = mix(leaf, (0, 0, 0), 0.3)
    ground = S * 0.8

    if stage == 0:
        for x in (0.3, 0.5, 0.7):
            d.ellipse([S * x - S * 0.03, ground - S * 0.05, S * x + S * 0.03, ground + S * 0.01], fill=(70, 44, 24))
        return img.resize((size, size), Image.LANCZOS)

    big = ci in (4, 6)                 # bí ngô, dưa hấu: một quả to ở giữa
    xs = (0.5,) if big else (0.26, 0.5, 0.74)
    stem_h = S * (0.08 + 0.34 * g) * (0.7 if big else 1)
    for x in xs:
        cx = S * x
        top = ground - stem_h
        d.line([(cx, ground), (cx, top)], fill=leaf_dk, width=int(S * 0.025))
        lw = S * (0.05 + 0.09 * g) * (1.8 if big else 1)
        ly = ground - stem_h * 0.45
        for side in (-1, 1):
            lx = cx + side * lw * 0.9
            d.ellipse([lx - lw, ly - lw * 0.45, lx + lw, ly + lw * 0.45], fill=leaf)
        d.ellipse([cx - lw * 0.55, top - lw * 0.55, cx + lw * 0.55, top + lw * 0.3], fill=leaf)

    k = clamp01((g - 0.5) / 0.5)       # quả lớn dần ở nửa sau
    if k > 0:
        for x in xs:
            cx = S * x
            top = ground - stem_h
            if ci == 0:     # lúa mì: bông vàng
                r = S * 0.05 * (0.4 + 0.6 * k)
                for j in range(3):
                    yy = top - r * 0.5 + j * r * 1.1
                    d.ellipse([cx - r * 0.7, yy - r, cx + r * 0.7, yy + r], fill=color, outline=mix(color, (0, 0, 0), 0.3))
            elif ci == 1:   # cà rốt: củ nhú lên khỏi đất
                w, h = S * 0.07 * (0.4 + 0.6 * k), S * 0.12 * (0.4 + 0.6 * k)
                d.polygon([(cx - w, ground - h * 0.3), (cx + w, ground - h * 0.3), (cx, ground + h * 0.7)], fill=color)
            elif ci == 2:   # ngô: bắp vàng có lá bao
                w, h = S * 0.045 * (0.4 + 0.6 * k), S * 0.12 * (0.4 + 0.6 * k)
                yy = ground - stem_h * 0.62
                d.ellipse([cx + S * 0.02, yy - h, cx + S * 0.02 + w * 2, yy + h], fill=color, outline=(200, 160, 30))
                d.polygon([(cx + S * 0.01, yy + h), (cx + S * 0.02 + w * 2.4, yy - h * 0.2), (cx + S * 0.02, yy)],
                          fill=leaf)
            elif ci == 3:   # cà chua: quả đỏ treo
                r = S * 0.045 * (0.4 + 0.6 * k)
                for dx, dy in ((-0.05, 0.35), (0.05, 0.6)):
                    px, py = cx + S * dx, ground - stem_h * dy
                    d.ellipse([px - r, py - r, px + r, py + r], fill=color)
                    d.ellipse([px - r * 0.5, py - r * 0.6, px - r * 0.1, py - r * 0.2], fill=(255, 200, 190))
            elif ci == 5:   # dâu tây
                r = S * 0.05 * (0.4 + 0.6 * k)
                for dx in (-0.06, 0.06):
                    px, py = cx + S * dx, ground - S * 0.05
                    d.polygon([(px - r, py - r * 0.6), (px + r, py - r * 0.6), (px, py + r * 1.2)], fill=color)
                    d.ellipse([px - r, py - r * 1.2, px + r, py], fill=color)
                    for sx, sy in ((-0.3, -0.3), (0.3, -0.3), (0, 0.2)):
                        d.ellipse([px + sx * r - 2, py + sy * r - 2, px + sx * r + 2, py + sy * r + 2],
                                  fill=(255, 230, 120))
            elif ci in (4, 6):   # bí ngô / dưa hấu
                w, h = S * 0.3 * (0.3 + 0.7 * k), S * 0.2 * (0.3 + 0.7 * k)
                py = ground - h * 0.8
                d.ellipse([cx - w, py - h, cx + w, py + h], fill=color, outline=mix(color, (0, 0, 0), 0.35),
                          width=int(S * 0.012))
                stripe = mix(color, (0, 0, 0), 0.3) if ci == 4 else (30, 110, 40)
                for j in (-0.5, 0, 0.5):
                    d.arc([cx + w * j - w * 0.25, py - h, cx + w * j + w * 0.25, py + h], 270, 90 if j >= 0 else 270,
                          fill=stripe, width=int(S * 0.012))
                    d.line([(cx + w * j, py - h * 0.9), (cx + w * j, py + h * 0.9)], fill=stripe, width=int(S * 0.01))
                d.ellipse([cx - w * 0.6, py - h * 0.7, cx - w * 0.2, py - h * 0.35], fill=(255, 255, 255, 90))
                if ci == 4:
                    d.rectangle([cx - S * 0.015, py - h - S * 0.05, cx + S * 0.015, py - h + S * 0.01],
                                fill=(110, 80, 40))
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def farmer_sprite(size):
    png = load_png_asset("farmer.png", size)
    if png is not None:
        return png
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = S * 0.5, S * 0.58
    r = S * 0.3
    d.ellipse([cx - r, cy - r + S * 0.03, cx + r, cy + r + S * 0.03], fill=(0, 0, 0, 70))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 214, 170), outline=(120, 70, 40), width=int(S * 0.02))
    for ex in (-0.35, 0.35):
        d.ellipse([cx + ex * r - S * 0.03, cy - S * 0.02, cx + ex * r + S * 0.03, cy + S * 0.06], fill=(50, 30, 20))
    d.arc([cx - r * 0.4, cy + r * 0.05, cx + r * 0.4, cy + r * 0.55], 20, 160, fill=(150, 60, 40), width=int(S * 0.025))
    d.ellipse([cx - r * 1.45, cy - r * 0.75, cx + r * 1.45, cy - r * 0.3], fill=(236, 196, 90),
              outline=(170, 120, 40), width=int(S * 0.015))
    d.chord([cx - r * 0.8, cy - r * 1.45, cx + r * 0.8, cy - r * 0.1], 180, 360, fill=(246, 210, 100),
            outline=(170, 120, 40), width=int(S * 0.015))
    d.rectangle([cx - r * 0.8, cy - r * 0.78, cx + r * 0.8, cy - r * 0.6], fill=(220, 60, 60))
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def coin_sprite(size):
    S = size * 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, S * 0.05, S, S], fill=(190, 120, 20))
    d.ellipse([0, 0, S, S * 0.95], fill=(255, 200, 40), outline=(200, 130, 20), width=int(S * 0.05))
    d.polygon(star_points(S / 2, S * 0.48, S * 0.25), fill=(255, 236, 140))
    return img.resize((size, size), Image.LANCZOS)


# ============================================================================
# Mô phỏng game (từng khung hình)
# ============================================================================
class Plot:
    __slots__ = ("locked", "crop", "growth", "rate")

    def __init__(self, locked):
        self.locked, self.crop, self.growth, self.rate = locked, None, 0.0, 1.0


class FarmGame:
    def __init__(self, cfg):
        self.cfg = cfg
        self.fps = cfg["fps"]
        self.dt = 1 / self.fps
        self.rng = random.Random(cfg["seed"])
        self.total = int(cfg["duration"] * self.fps)
        self.end_frame = self.total - int(cfg["end_card"] * self.fps)
        self.C, self.R = cfg["cols"], cfg["rows"]
        n = self.C * self.R
        self.plots = [Plot(i >= cfg["start_plots"]) for i in range(n)]
        self.money = cfg["start_money"]
        self.shown_money = float(self.money)
        self.bought = 0
        self.best_crop = -1
        self.frames = []        # ảnh chụp trạng thái mỗi khung
        self.floats = []        # (frame, text, plot, color)
        self.banners = []       # (frame, text, color)
        self.events = []        # âm thanh (frame, tên, tham số)
        self.stats = {"harvests": 0, "best_sale": 0, "plots": cfg["start_plots"]}
        # bot
        self.pos = (0.0, 0.0)
        self.move_from = self.move_to = self.pos
        self.move_t = self.move_len = 0.0
        self.act_t = 0.0
        self.pending = None
        self.acting = None      # (frame, plot) để vẽ nhún

    def plot_price(self):
        return int(round(self.cfg["plot_price"] * self.cfg["plot_price_grow"] ** self.bought / 5) * 5)

    def rc(self, i):
        return divmod(i, self.C)

    def in_event(self, frame, every, length):
        if not every:
            return False
        sec = frame / self.fps
        return sec >= every and (sec % every) < length and frame < self.end_frame

    # ---------- bot ----------
    def choose(self, frame):
        plots = self.plots
        r0, c0 = self.pos
        dist = lambda i: abs(self.rc(i)[0] - r0) + abs(self.rc(i)[1] - c0)
        ripe = [i for i, p in enumerate(plots) if p.crop is not None and p.growth >= 1]
        if ripe:
            return "harvest", min(ripe, key=dist)
        empty = [i for i, p in enumerate(plots) if not p.locked and p.crop is None]
        locked = [i for i, p in enumerate(plots) if p.locked]
        price = self.plot_price()
        left = (self.end_frame - frame) / self.fps
        if locked and left > 8 and self.money >= price and (not empty or price * 20 <= self.money):
            return "unlock", locked[0]
        if empty and self.money >= CROPS[0][1] and self.pick_crop(left) is not None:
            return "plant", min(empty, key=dist)
        growing = [i for i, p in enumerate(plots) if p.crop is not None]
        if growing:
            soon = max(growing, key=lambda i: plots[i].growth)
            if soon != self.target_plot():
                return "walk", soon
        return None

    def target_plot(self):
        r, c = self.move_to
        return int(round(r)) * self.C + int(round(c))

    def pick_crop(self, left):
        """Cây đắt nhất đủ tiền và kịp chín trước khi hết giờ,
        chừa tiền cho các ô trống còn lại trồng ít nhất lúa mì."""
        empty = sum(1 for p in self.plots if not p.locked and p.crop is None)
        budget = self.money - CROPS[0][1] * max(0, empty - 1)
        best = None
        for i, crop in enumerate(CROPS):
            if crop[1] <= max(budget, CROPS[0][1]) and crop[1] <= self.money and crop[3] * 1.3 < left:
                best = i
        return best

    def perform(self, frame, action, i):
        p = self.plots[i]
        if action == "harvest" and p.crop is not None and p.growth >= 1:
            mult = self.cfg["market_boost"] if self.in_event(frame, self.cfg["market_every"],
                                                              self.cfg["market_len"]) else 1
            gain = int(CROPS[p.crop][2] * mult)
            self.money += gain
            self.floats.append((frame, f"+{fmt_num(gain)}", i, (255, 230, 90)))
            self.events.append((frame, "coin", {"pitch": 1 + 0.08 * p.crop}))
            self.stats["harvests"] += 1
            self.stats["best_sale"] = max(self.stats["best_sale"], gain)
            p.crop, p.growth = None, 0.0
        elif action == "plant" and not p.locked and p.crop is None and                 self.pick_crop((self.end_frame - frame) / self.fps) is not None:
            ci = self.pick_crop((self.end_frame - frame) / self.fps)
            self.money -= CROPS[ci][1]
            p.crop, p.growth = ci, 0.0
            p.rate = self.rng.uniform(0.8, 1.25)   # mỗi cây lớn nhanh chậm khác nhau theo seed
            self.floats.append((frame, f"-{fmt_num(CROPS[ci][1])}", i, (255, 150, 140)))
            self.events.append((frame, "plant", {}))
            if ci > self.best_crop:
                if self.best_crop >= 0:
                    self.banners.append((frame, f"Mở khóa: {CROPS[ci][0]}!", (120, 70, 200)))
                    self.events.append((frame, "chime", {}))
                self.best_crop = ci
        elif action == "unlock" and p.locked and self.money >= self.plot_price():
            price = self.plot_price()
            self.money -= price
            p.locked = False
            self.bought += 1
            self.stats["plots"] += 1
            self.floats.append((frame, f"-{fmt_num(price)}", i, (255, 150, 140)))
            self.banners.append((frame, "Mở thêm ô đất!", (60, 140, 60)))
            self.events.append((frame, "chime", {}))
        self.acting = (frame, i)

    def step_bot(self, frame):
        if self.move_t < self.move_len:
            self.move_t += self.dt
            k = ease_out(clamp01(self.move_t / self.move_len))
            (r0, c0), (r1, c1) = self.move_from, self.move_to
            self.pos = (r0 + (r1 - r0) * k, c0 + (c1 - c0) * k)
            if self.move_t >= self.move_len and self.pending:
                action, i = self.pending
                self.pending = None
                if action != "walk":
                    self.perform(frame, action, i)
                    self.act_t = 0.14
            return
        if self.act_t > 0:
            self.act_t -= self.dt
            return
        if frame >= self.end_frame:
            return
        choice = self.pending or self.choose(frame)
        if choice is None:
            return
        action, i = choice
        r, c = self.rc(i)
        dist = math.hypot(r - self.pos[0], c - self.pos[1])
        self.move_from, self.move_to = self.pos, (float(r), float(c))
        self.move_t = 0.0
        self.move_len = 0.08 + min(0.25, 0.07 * dist)
        self.pending = (action, i)

    # ---------- chạy cả ván ----------
    def play(self):
        cfg = self.cfg
        was_rain = was_market = False
        for f in range(self.total):
            rain = self.in_event(f, cfg["rain_every"], cfg["rain_len"])
            market = self.in_event(f, cfg["market_every"], cfg["market_len"])
            if rain and not was_rain:
                self.banners.append((f, "Trời mưa! Cây lớn nhanh x2", (40, 110, 200)))
                self.events.append((f, "rain", {"dur": cfg["rain_len"]}))
            if market and not was_market:
                self.banners.append((f, "Chợ phiên! Giá bán x2", (220, 110, 20)))
                self.events.append((f, "fanfare", {}))
            was_rain, was_market = rain, market
            if f < self.end_frame:
                speed = cfg["rain_boost"] if rain else 1.0
                for p in self.plots:
                    if p.crop is not None and p.growth < 1:
                        before = p.growth
                        p.growth = min(1.0, p.growth + self.dt * speed * p.rate / CROPS[p.crop][3])
                        if before < 1 <= p.growth:
                            self.events.append((f, "ripe", {}))
            self.step_bot(f)
            self.shown_money += (self.money - self.shown_money) * 0.22
            if abs(self.money - self.shown_money) < 0.5:
                self.shown_money = self.money
            self.frames.append({
                "money": self.shown_money,
                "plots": [(p.locked, p.crop, p.growth) for p in self.plots],
                "pos": self.pos,
                "acting": self.acting,
                "price": self.plot_price(),
                "rain": rain,
                "market": market,
            })
        return self


# ============================================================================
# Vẽ khung hình
# ============================================================================
class Renderer:
    def __init__(self, game, cfg):
        self.g, self.cfg = game, cfg
        self.W, self.H = cfg["width"], cfg["height"]
        self.cell = 224
        self.fx0 = (self.W - self.cell * game.C) // 2
        self.fy0 = 620
        self.plot_size = self.cell - 20
        self.bg = self.build_background()
        self.hook_img = text_image(wrap_text(cfg["hook"], load_font(92), self.W - 120), load_font(92),
                                   (255, 255, 255))
        self.title_img = text_image([cfg["game_name"]], load_font(50), (255, 236, 120), stroke=5)

    def build_background(self):
        W, H = self.W, self.H
        sky_h = 590
        t = np.linspace(0, 1, sky_h)[:, None]
        sky = np.array([84, 170, 240]) * (1 - t) + np.array([170, 222, 250]) * t
        grass = np.zeros((H - sky_h, 1, 3)) + np.array([104, 180, 78])
        arr = np.concatenate([sky[:, None, :], grass], axis=0).repeat(W, axis=1)
        img = Image.fromarray(arr.astype(np.uint8), "RGB")
        d = ImageDraw.Draw(img, "RGBA")
        rng = random.Random(4)
        for _ in range(5):   # mây
            x, y = rng.randrange(W), rng.randrange(40, 520)
            for dx, dy, r in ((0, 0, 50), (45, -18, 42), (85, 0, 46), (40, 12, 44)):
                d.ellipse([x + dx - r, y + dy - r * 0.7, x + dx + r, y + dy + r * 0.7], fill=(255, 255, 255, 70))
        d.polygon([(0, sky_h), (W * 0.3, sky_h - 70), (W * 0.6, sky_h - 20), (W, sky_h - 90), (W, sky_h), (0, sky_h)],
                  fill=(86, 160, 70))
        for _ in range(260):  # cỏ
            x, y = rng.randrange(W), rng.randrange(sky_h, H)
            d.line([(x, y), (x + rng.randint(-5, 5), y - rng.randint(8, 18))], fill=(70, 150, 60, 150), width=3)
        field = [self.fx0 - 22, self.fy0 - 22, self.fx0 + self.cell * self.g.C + 22,
                 self.fy0 + self.cell * self.g.R + 22]
        d.rounded_rectangle(field, radius=36, fill=(160, 120, 70, 255), outline=(120, 84, 46), width=8)
        for k in range(0, field[2] - field[0], 44):   # hàng rào gỗ
            d.rectangle([field[0] + k, field[1] - 10, field[0] + k + 12, field[1] + 4], fill=(200, 150, 90))
        return img

    def plot_xy(self, r, c):
        return self.fx0 + c * self.cell + self.cell / 2, self.fy0 + r * self.cell + self.cell / 2

    def paste_c(self, img, spr, x, y):
        img.paste(spr, (int(x - spr.width / 2), int(y - spr.height / 2)), spr)

    def render(self, frame):
        g = self.g
        st = g.frames[frame]
        img = self.bg.copy()
        d = ImageDraw.Draw(img, "RGBA")
        ps = self.plot_size
        act_f, act_i = st["acting"] or (-99, -1)

        for i, (locked, crop, growth) in enumerate(st["plots"]):
            r, c = g.rc(i)
            x, y = self.plot_xy(r, c)
            if locked:
                d.rounded_rectangle([x - ps / 2, y - ps / 2, x + ps / 2, y + ps / 2], radius=24,
                                    fill=(60, 110, 50, 140), outline=(255, 255, 255, 60), width=3)
                self.draw_lock(d, x, y - 18)
                if i == next(j for j, p in enumerate(st["plots"]) if p[0]):
                    d.text((x, y + 58), f"{fmt_num(st['price'])} xu", font=load_font(38), fill=(255, 240, 150),
                           anchor="mm", stroke_width=4, stroke_fill=(40, 60, 20))
                continue
            bounce = 1.0
            if i == act_i and 0 <= frame - act_f < 8:
                bounce = 1 + 0.08 * math.sin((frame - act_f) / 8 * math.pi)
            soil = soil_sprite(int(ps * bounce) // 2 * 2)
            self.paste_c(img, soil, x, y)
            if crop is None:
                continue
            ripe = growth >= 1
            if ripe:
                glow = 0.5 + 0.5 * math.sin(frame * 0.4 + i)
                d.rounded_rectangle([x - ps / 2 - 4, y - ps / 2 - 4, x + ps / 2 + 4, y + ps / 2 + 4], radius=28,
                                    outline=(255, 240, 120, int(140 + 110 * glow)), width=7)
            spr = crop_sprite(crop, min(STAGES, int(growth * STAGES)), ps)
            dy = -4 * abs(math.sin(frame * 0.25 + i)) if ripe else 0
            self.paste_c(img, spr, x, y - 8 + dy)
            if ripe:
                for k in range(2):
                    a = frame * 0.12 + k * math.pi + i
                    sx, sy = x + math.cos(a) * ps * 0.36, y - ps * 0.25 + math.sin(a) * ps * 0.12
                    s = 10 + 5 * math.sin(frame * 0.5 + k)
                    d.polygon(star_points(sx, sy, s, 0.4, 4), fill=(255, 255, 210, 230))
            else:
                bx0, bx1, by = x - ps * 0.36, x + ps * 0.36, y + ps / 2 - 16
                d.rounded_rectangle([bx0, by - 7, bx1, by + 7], radius=7, fill=(0, 0, 0, 90))
                d.rounded_rectangle([bx0, by - 7, bx0 + max(14, (bx1 - bx0) * growth), by + 7], radius=7,
                                    fill=(120, 230, 90))

        # nông dân
        pr, pc = st["pos"]
        fx, fy = self.plot_xy(pr, pc)
        hop = 10 * abs(math.sin(frame * 0.35))
        self.paste_c(img, farmer_sprite(120), fx + 62, fy + 40 - hop)

        if st["rain"]:
            self.draw_rain(d, frame)
        self.draw_floats(d, frame)
        self.draw_hud(img, d, st, frame)
        self.draw_banners(d, frame)
        if frame >= g.end_frame:
            self.draw_end_card(img, frame)
        return img

    def draw_lock(self, d, x, y):
        d.arc([x - 24, y - 50, x + 24, y], 180, 360, fill=(230, 230, 240), width=10)
        d.rounded_rectangle([x - 34, y - 22, x + 34, y + 30], radius=10, fill=(250, 196, 60),
                            outline=(170, 120, 30), width=4)
        d.ellipse([x - 7, y - 4, x + 7, y + 10], fill=(120, 80, 20))

    def draw_rain(self, d, frame):
        d.rectangle([0, 0, self.W, self.H], fill=(40, 80, 160, 40))
        rng = random.Random(frame)
        for _ in range(90):
            x, y = rng.randrange(self.W + 200), rng.randrange(self.H)
            d.line([(x, y), (x - 14, y + 40)], fill=(220, 235, 255, 150), width=3)

    def draw_floats(self, d, frame):
        for f0, text, i, col in self.g.floats:
            k = frame - f0
            if not 0 <= k < 30:
                continue
            r, c = self.g.rc(i)
            x, y = self.plot_xy(r, c)
            a = int(255 * (1 - clamp01((k - 18) / 12)))
            big = text.startswith("+")
            font = load_font(66 if big else 44)
            ty = y - 40 - 90 * ease_out(k / 30) if big else y + 70 - 30 * ease_out(k / 30)
            d.text((x, ty), text, font=font, fill=col + (a,), anchor="mm",
                   stroke_width=6 if big else 4, stroke_fill=(60, 30, 10, a))

    def draw_banners(self, d, frame):
        live = [(f0, t, c) for f0, t, c in self.g.banners if 0 <= frame - f0 < 48]
        for n, (f0, text, col) in enumerate(live[-2:]):
            k = frame - f0
            slide = ease_out_back(clamp01(k / 8)) if k < 40 else 1 - ease_out(clamp01((k - 40) / 8))
            y = self.fy0 + self.cell * 2.5 + n * 120
            w = 900 * slide
            if w < 20:
                continue
            d.rounded_rectangle([self.W / 2 - w / 2, y - 50, self.W / 2 + w / 2, y + 50], radius=50,
                                fill=col + (235,), outline=(255, 255, 255, 200), width=5)
            d.text((self.W / 2, y), text, font=load_font(max(10, int(56 * slide))), fill=(255, 255, 255),
                   anchor="mm", stroke_width=5, stroke_fill=mix(col, (0, 0, 0), 0.5))

    def draw_hud(self, img, d, st, frame):
        g = self.g
        img.paste(self.title_img, (int(self.W / 2 - self.title_img.width / 2), 60), self.title_img)
        s = ease_out_back(clamp01(frame / 12)) if frame < 12 else 1 + 0.02 * math.sin(frame * 0.12)
        hook = self.hook_img
        if abs(s - 1) > 0.005:
            hook = hook.resize((max(1, int(hook.width * s)), max(1, int(hook.height * s))), Image.BILINEAR)
        img.paste(hook, (int(self.W / 2 - hook.width / 2), int(290 - hook.height / 2)), hook)

        # túi tiền
        y0 = 450
        d.rounded_rectangle([self.W / 2 - 300, y0, self.W / 2 + 300, y0 + 120], radius=60, fill=(92, 60, 30, 240),
                            outline=(255, 214, 90, 200), width=5)
        coin = coin_sprite(84)
        img.paste(coin, (int(self.W / 2 - 270), int(y0 + 18)), coin)
        d.text((self.W / 2 + 40, y0 + 58), f"{fmt_num(st['money'])} xu", font=load_font(84), fill=(255, 255, 255),
               anchor="mm", stroke_width=6, stroke_fill=(60, 40, 10))
        if st["market"]:
            d.rounded_rectangle([self.W / 2 + 230, y0 - 20, self.W / 2 + 330, y0 + 40], radius=24,
                                fill=(230, 90, 30))
            d.text((self.W / 2 + 280, y0 + 10), "x2", font=load_font(44), fill=(255, 255, 255), anchor="mm")

        # thanh thời gian
        left = max(0.0, (g.end_frame - frame) / g.fps)
        frac = clamp01((g.end_frame - frame) / g.end_frame)
        y1 = self.fy0 + self.cell * g.R + 52
        x0, x1 = 90, self.W - 90
        d.rounded_rectangle([x0, y1, x1, y1 + 30], radius=15, fill=(0, 0, 0, 70))
        if frac > 0:
            col = mix((255, 80, 60), (255, 230, 80), clamp01(frac * 2))
            d.rounded_rectangle([x0, y1, x0 + max(30, (x1 - x0) * frac), y1 + 30], radius=15, fill=col)
        plots = sum(1 for p in st["plots"] if not p[0])
        d.text((self.W / 2, y1 + 72), f"Còn {int(math.ceil(left))} giây  ·  Ô đất {plots}/{len(st['plots'])}  ·  "
               f"Ván số {g.cfg['seed']}", font=load_font(38, "Bold"), fill=(255, 255, 255, 230), anchor="mm",
               stroke_width=4, stroke_fill=(40, 80, 30))

    def draw_end_card(self, img, frame):
        g = self.g
        k = clamp01((frame - g.end_frame) / 10)
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([0, 0, self.W, self.H], fill=(10, 24, 8, int(170 * k)))
        s = ease_out_back(k)
        if s < 0.05:
            return
        cy = self.H / 2
        pw, ph = 900 * s, 860 * s
        d.rounded_rectangle([self.W / 2 - pw / 2, cy - ph / 2, self.W / 2 + pw / 2, cy + ph / 2], radius=50,
                            fill=(60, 110, 46, 245), outline=(255, 214, 90), width=6)
        f = lambda size: load_font(max(10, int(size * s)))
        d.text((self.W / 2, cy - 320 * s), "HẾT GIỜ!", font=f(110), fill=(255, 236, 120), anchor="mm",
               stroke_width=8, stroke_fill=(40, 50, 10))
        d.text((self.W / 2, cy - 190 * s), f"Từ {fmt_num(self.cfg['start_money'])} xu thành", font=f(52),
               fill=(230, 255, 220), anchor="mm")
        d.text((self.W / 2, cy - 80 * s), f"{fmt_num(g.money)} xu", font=f(124), fill=(255, 255, 255), anchor="mm",
               stroke_width=8, stroke_fill=(40, 50, 10))
        lines = wrap_text(self.cfg["question"], f(58), pw - 60)
        draw_lines(d, self.W / 2, cy + 190 * s, lines, f(58), (255, 226, 110), stroke=6)


# ============================================================================
# Âm thanh tự tổng hợp
# ============================================================================
def _t(dur):
    return np.arange(int(SR * dur)) / SR


def s_coin(pitch=1.0):
    a, b = _t(0.07), _t(0.2)
    sq = lambda f, t: np.sign(np.sin(2 * np.pi * f * t)) * 0.2 + np.sin(2 * np.pi * f * t) * 0.4
    return np.concatenate([sq(988 * pitch, a) * np.exp(-a * 10), sq(1319 * pitch, b) * np.exp(-b * 12)]) * 0.5


def s_plant():
    t = _t(0.12)
    return np.sin(2 * np.pi * np.cumsum(420 - 1500 * t) / SR) * np.exp(-t * 30) * 0.45


def s_ripe():
    t = _t(0.1)
    return np.sin(2 * np.pi * 1760 * t) * np.exp(-t * 45) * 0.18


def s_chime():
    out = []
    for f in (784, 988, 1175, 1568):
        t = _t(0.09)
        out.append(np.sin(2 * np.pi * f * t) * np.exp(-t * 18) * 0.4)
    return np.concatenate(out)


def s_fanfare():
    out = []
    for f, dur in ((523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.35)):
        t = _t(dur)
        ph = 2 * np.pi * f * t
        out.append((np.sin(ph) * 0.5 + np.sign(np.sin(ph)) * 0.12) * np.minimum(1, (dur - t) * 20) * 0.45)
    return np.concatenate(out)


def s_rain(dur=4.0):
    t = _t(dur)
    noise = np.random.default_rng(3).normal(0, 1, len(t))
    noise = noise - np.convolve(noise, np.ones(6) / 6, mode="same")
    env = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.8)
    return noise * env * 0.12


def music(total_sec):
    """Nhạc nền đồng quê đơn giản tự tạo (không bản quyền)."""
    bpm = 120
    beat = 60 / bpm
    t = _t(total_sec)
    out = np.zeros_like(t)
    melody = [523, 587, 659, 784, 659, 587, 523, 392, 440, 523, 587, 523, 440, 392, 440, 523]
    bass = [131, 131, 175, 196]
    for i, start in enumerate(np.arange(0, total_sec, beat / 2)):
        s = int(start * SR)
        n = min(len(t) - s, int(beat / 2 * SR))
        if n <= 0:
            break
        tt = t[:n]
        f = melody[i % len(melody)]
        out[s:s + n] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 9) * 0.16
        if i % 2 == 0:
            fb = bass[(i // 8) % 4]
            out[s:s + n] += np.sin(2 * np.pi * fb * tt) * np.exp(-tt * 5) * 0.3
    fade = np.minimum(1, np.minimum(t / 0.5, (total_sec - t) / 1.5))
    return out * fade


def build_audio(game, cfg, path):
    total_sec = game.total / game.fps
    n = int(total_sec * SR)
    mixbuf = np.zeros(n)
    if cfg["music_volume"] > 0:
        mixbuf += music(total_sec) * cfg["music_volume"]
    makers = {"coin": s_coin, "plant": s_plant, "ripe": s_ripe, "chime": s_chime, "fanfare": s_fanfare,
              "rain": s_rain}
    last = {}
    for frame, name, kw in game.events:
        if frame >= game.total:
            continue
        if name == "ripe" and frame - last.get("ripe", -99) < 4:   # tránh dồn tiếng
            continue
        last[name] = frame
        snd = makers[name](**kw) * cfg["sfx_volume"]
        s = int(frame / game.fps * SR)
        e = min(n, s + len(snd))
        mixbuf[s:e] += snd[:e - s]
    mixbuf = np.tanh(mixbuf * 1.1)
    peak = np.max(np.abs(mixbuf)) or 1
    pcm = (mixbuf / peak * 0.92 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())


# ============================================================================
# Xuất video / ảnh xem thử
# ============================================================================
def export_video(game, renderer, cfg, out_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("Không tìm thấy ffmpeg. Cài ffmpeg và thêm vào PATH (kiểm tra: ffmpeg -version).")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [ffmpeg, "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cfg['width']}x{cfg['height']}",
               "-r", str(cfg["fps"]), "-i", "-"]
        if cfg.get("audio"):
            wav = Path(tmp) / "audio.wav"
            build_audio(game, cfg, wav)
            cmd += ["-i", str(wav), "-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-an"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(cfg["crf"]), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t0 = time.time()
        try:
            for f in range(game.total):
                proc.stdin.write(renderer.render(f).tobytes())
                if f % cfg["fps"] == 0 or f == game.total - 1:
                    pct = (f + 1) / game.total
                    print(f"\r  Đang render {pct:5.1%}  ({time.time() - t0:5.1f}s)", end="", flush=True)
        finally:
            proc.stdin.close()
            proc.wait()
        print()
        if proc.returncode != 0:
            sys.exit(f"ffmpeg lỗi (mã {proc.returncode}).")


def resolve_out(path_str, default_name):
    p = Path(path_str) if path_str else Path(default_name)
    if not p.is_absolute() and p.parent == Path("."):
        p = OUTPUT / p
    return p


def main():
    if hasattr(sys.stdout, "reconfigure"):   # console Windows in được tiếng Việt
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Nông Trại Của TEE — game tự chơi xuất video dọc")
    ap.add_argument("--seed", type=int, help="số ván (mỗi seed ra một ván khác)")
    ap.add_argument("--out", help="tên file video; chỉ có tên file thì lưu vào output/")
    ap.add_argument("--preview", help="xuất ảnh ở các giây này, ví dụ 5,20,36")
    ap.add_argument("--hook", help="câu hook hiện ở đầu video")
    ap.add_argument("--question", help="câu hỏi cuối video")
    ap.add_argument("--duration", type=float, help="độ dài video (giây)")
    args = ap.parse_args()

    cfg = dict(CONFIG)
    for key in ("seed", "hook", "question", "duration"):
        if getattr(args, key) is not None:
            cfg[key] = getattr(args, key)

    t0 = time.time()
    game = FarmGame(cfg).play()
    renderer = Renderer(game, cfg)
    st = game.stats
    print(f"Ván số {cfg['seed']}: {fmt_num(cfg['start_money'])} → {fmt_num(game.money)} xu · "
          f"{st['harvests']} lần thu hoạch · {st['plots']} ô đất · cây xịn nhất: {CROPS[game.best_crop][0]}")

    if args.preview:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for sec in [float(s) for s in args.preview.split(",") if s.strip()]:
            f = min(game.total - 1, int(sec * cfg["fps"]))
            p = OUTPUT / f"nong-trai_seed{cfg['seed']}_{sec:g}s.png"
            renderer.render(f).save(p)
            print(f"  Đã lưu {p}")
        return

    out = resolve_out(args.out, f"nong-trai_seed{cfg['seed']}.mp4")
    export_video(game, renderer, cfg, out)
    print(f"Xong: {out}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
