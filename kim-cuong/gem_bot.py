#!/usr/bin/env python3
"""Kim Cương TEE — game kim cương tự chơi, xuất video dọc 1080x1920 cho TikTok / Shorts.

Cách chạy:
    python gem_bot.py                          # xuất video 50 giây vào output/
    python gem_bot.py --preview 5,20,36        # chỉ xuất vài ảnh PNG để xem nhanh
    python gem_bot.py --seed 25 --out v2.mp4   # một ván khác
    python gem_bot.py --hook "Ván này được bao nhiêu điểm?" --duration 30
    python gem_bot.py --theme keo --items do-an             # đổi template (xem gem_templates.py)
    python gem_bot.py --nen --duration 180     # clip NỀN cho video đọc truyện (xem tao_kho_nen.py)

Luật game:
    - Đổi chỗ 2 viên cạnh nhau để có hàng 3+ viên cùng loại thì vỡ.
    - Hàng 4 tạo ra bom, hàng 5 tạo ra siêu bom.
    - Bom nổ khi bị đổi chỗ, khi có viên vỡ sát bên, hoặc khi dính vụ nổ khác (nổ liên hoàn).
    - Cứ mỗi `rain_every` giây có "mưa bom": bom rơi xuống bàn và nổ cùng lúc.

Muốn thay hình tự vẽ bằng ảnh PNG (giai đoạn 2): đặt file vào assets/kim-cuong/
    gem_0.png … gem_5.png, bomb.png, super_bomb.png  (PNG vuông, nền trong suốt).
"""
import argparse
import bisect
import heapq
import math
import random
import re
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gem_templates as T  # noqa: E402

# ============================================================================
# CONFIG — chỉnh ở đây
# ============================================================================
CONFIG = {
    "game_name": "KIM CƯƠNG TEE",
    "theme": "dem",          # giao diện: dem (Đêm tím) · keo (Kẹo ngọt) · neon (Neon)
    "items": "kim-cuong",    # bộ icon: kim-cuong · do-an (Đồ ăn) · trai-cay (Trái cây)
    "hook": "Bom nổ liên hoàn tới đâu?",
    "question": "Ván sau được bao nhiêu điểm?\nBình luận dự đoán nhé!",
    "duration": 50,          # giây (tối đa nên để 180 = 3 phút)
    "speed": 1.0,            # tốc độ chơi: 0.8 = chậm, 1 = như người thật, 1.3 = nhanh, 1.6 = rất nhanh
    # Nhịp như người chơi thật: bot "nghĩ" trước mỗi nước để người xem kịp tự đoán.
    "think_min": 0.6,        # giây nghĩ ngắn nhất trước mỗi nước
    "think_max": 1.5,        # giây nghĩ dài nhất
    "decoy_chance": 0.4,     # tỉ lệ ngón tay ghé một viên khác trước (lưỡng lự)
    "touch_time": 0.3,       # giây chạm giữ viên trước khi gạt
    "swipe_time": 0.35,      # giây gạt viên sang ô bên cạnh
    "skill": 0.6,            # độ giỏi: 1 = luôn chọn nước tốt nhất, 0 = chọn bừa một nước hợp lệ
    "fps": 30,
    "width": 1080,
    "height": 1920,
    "seed": 7,
    "rows": 8,
    "cols": 8,
    "bomb_spawn": 0.035,     # tỉ lệ viên mới rơi xuống là bom
    "super_spawn": 0.006,    # tỉ lệ viên mới rơi xuống là siêu bom
    "rain_every": 12,        # mỗi N giây có mưa bom (0 = tắt)
    "rain_count": 6,         # số bom mỗi trận mưa
    "end_card": 4.0,         # số giây cuối hiện câu hỏi
    "level": 0,              # số Level hiện trên HUD (0 = tự động theo seed)
    "leaderboard": "",       # điểm Top 1-3, ví dụ "35400 32000 29030" (trống = tự động theo điểm ván)
    "audio": False,          # False = video không tiếng (không tạo âm thanh, render nhanh hơn)
    "music_volume": 0.18,    # nhạc nền tự tổng hợp (0 = tắt), chỉ dùng khi audio = True
    "sfx_volume": 0.9,
    "crf": 20,               # chất lượng x264 (thấp = nét hơn, file nặng hơn)
    # Chế độ NỀN: clip làm nền cho video đọc truyện (project_5), không phải Shorts.
    # Tắt hook, end card "HẾT GIỜ", đồng hồ nháy đỏ 10 giây cuối, chớp sáng khi nổ;
    # băng "MƯA BOM!" thu nhỏ, không phủ đỏ cả màn. Người xem nghe truyện cả tiếng
    # đồng hồ — mấy thứ giật mình đó hợp 50 giây Shorts chứ nghe lâu thì phiền.
    "nen": False,
    "hud": True,             # False = bỏ bảng TOP/Level/điểm trên cùng (chỉ còn bàn cờ)
}

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"

BOMB, SUPER = 10, 11
GEM_COLORS = [
    (236, 62, 86),    # đỏ
    (255, 178, 36),   # vàng cam
    (60, 204, 112),   # xanh lá
    (54, 142, 246),   # xanh dương
    (172, 92, 242),   # tím
    (78, 226, 228),   # xanh ngọc
]
# Mỗi màu một hình dạng riêng, để người mù màu vẫn phân biệt được.
GEM_SHAPES = ["diamond", "round", "square", "triangle", "hexagon", "star"]

CLEAR_FRAMES = 9
CHAIN_DELAY = 4
SR = 44100


# ============================================================================
# Tiện ích
# ============================================================================
_TPL = {"font": "Baloo2.ttf", "weight": "ExtraBold", "scale": 1.0, "items": "kim-cuong"}


def set_template(theme_key, items_key):
    """Chọn font + bộ icon dùng cho các lần vẽ tiếp theo."""
    if theme_key not in T.THEMES:
        raise ValueError(f"Không có giao diện '{theme_key}'. Có: {', '.join(T.THEMES)}")
    if items_key not in T.ITEM_SETS:
        raise ValueError(f"Không có bộ icon '{items_key}'. Có: {', '.join(T.ITEM_SETS)}")
    th = T.THEMES[theme_key]
    _TPL.update(font=th["font"], weight=th["weight"], scale=th["font_scale"], items=items_key)
    return th


def load_font(size, weight=None):
    w = _TPL["weight"] and (weight if weight and _TPL["weight"] else _TPL["weight"])
    return _font(_TPL["font"], max(6, int(size * _TPL["scale"])), w)


@lru_cache(maxsize=None)
def _font(file, size, weight):
    for p in (ASSETS / "fonts" / file, HERE / file):
        if p.exists():
            font = ImageFont.truetype(str(p), size)
            if weight:
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


def ease_in(t):
    return t * t


def ease_out_back(t):
    c = 1.7
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def fmt_num(n):
    return f"{int(n):,}"


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


def draw_lines(draw, cx, cy, lines, font, fill, stroke=6, stroke_fill=(24, 12, 48), gap=1.05):
    """Vẽ nhiều dòng chữ, căn giữa quanh (cx, cy)."""
    lh = font.size * gap
    y0 = cy - lh * (len(lines) - 1) / 2
    for i, line in enumerate(lines):
        draw.text((cx, y0 + i * lh), line, font=font, fill=fill, anchor="mm",
                  stroke_width=stroke, stroke_fill=stroke_fill)


def text_image(lines, font, fill, stroke=7, stroke_fill=(24, 12, 48), gap=1.05):
    """Chữ vẽ sẵn thành ảnh RGBA, để phóng to/thu nhỏ khi làm hiệu ứng nảy."""
    lh = int(font.size * gap)
    w = int(max(font.getlength(l) for l in lines)) + stroke * 2 + 20
    h = lh * len(lines) + stroke * 2 + 20
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_lines(d, w / 2, h / 2, lines, font, fill, stroke, stroke_fill, gap)
    return img


# ============================================================================
# Hình kim cương & bom
# ============================================================================
def shape_points(shape, cx, cy, r):
    def ring(n, start, radius):
        return [(cx + radius * math.cos(math.radians(start + 360 * k / n)),
                 cy + radius * math.sin(math.radians(start + 360 * k / n))) for k in range(n)]

    if shape == "diamond":
        return [(cx, cy - r), (cx + r * 0.82, cy), (cx, cy + r), (cx - r * 0.82, cy)]
    if shape == "round":
        return ring(40, 0, r * 0.92)
    if shape == "square":
        return ring(4, 45, r * 1.12)
    if shape == "triangle":
        return ring(3, -90, r * 1.12)
    if shape == "hexagon":
        return ring(6, 0, r)
    if shape == "star":
        pts = []
        for k in range(10):
            rad = r * (1.05 if k % 2 == 0 else 0.55)
            a = math.radians(-90 + 36 * k)
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
        return pts
    raise ValueError(shape)


def load_png_asset(name, size):
    p = ASSETS / "kim-cuong" / name
    if p.exists():
        return Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    return None


def gem_sprite(color, size):
    png = load_png_asset(f"gem_{color}.png", size)
    if png is not None:
        return png
    ss = 3
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = GEM_COLORS[color]
    shape = GEM_SHAPES[color]
    cx, cy, r = S / 2, S / 2, S * 0.42
    if shape == "triangle":
        cy += r * 0.12
    d.polygon(shape_points(shape, cx, cy + S * 0.025, r), fill=mix(base, (0, 0, 0), 0.55))  # bóng
    d.polygon(shape_points(shape, cx, cy, r), fill=base)
    outer = shape_points(shape, cx, cy, r * 0.97)
    inner = shape_points(shape, cx, cy - r * 0.05, r * 0.52)
    # các mặt cắt: nửa trên sáng, nửa dưới tối
    for i in range(len(outer)):
        a, b = outer[i], outer[(i + 1) % len(outer)]
        ia, ib = inner[i], inner[(i + 1) % len(inner)]
        mid_y = (a[1] + b[1]) / 2
        shade = mix(base, (255, 255, 255), 0.25) if mid_y < cy else mix(base, (0, 0, 0), 0.22)
        d.polygon([a, b, ib, ia], fill=shade)
    d.polygon(inner, fill=mix(base, (255, 255, 255), 0.4))
    d.ellipse([cx - r * 0.5, cy - r * 0.62, cx - r * 0.12, cy - r * 0.34], fill=(255, 255, 255, 190))
    d.line(outer + [outer[0]], fill=mix(base, (0, 0, 0), 0.45), width=int(S * 0.018))
    return img.resize((size, size), Image.LANCZOS)


def bomb_sprite(kind, size):
    png = load_png_asset("super_bomb.png" if kind == SUPER else "bomb.png", size)
    if png is not None:
        return png
    ss = 3
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = S * 0.48, S * 0.56, S * 0.34
    body = (200, 34, 52) if kind == SUPER else (44, 42, 62)
    d.ellipse([cx - r, cy - r + S * 0.03, cx + r, cy + r + S * 0.03], fill=mix(body, (0, 0, 0), 0.6))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=body)
    d.ellipse([cx - r * 0.62, cy - r * 0.7, cx - r * 0.1, cy - r * 0.25], fill=(255, 255, 255, 110))
    # chóp và dây ngòi
    d.rounded_rectangle([cx + r * 0.25, cy - r * 1.12, cx + r * 0.75, cy - r * 0.72], radius=S * 0.02,
                        fill=(150, 150, 170))
    fx, fy = cx + r * 0.5, cy - r * 1.12
    pts = [(fx + S * 0.08 * t, fy - S * 0.1 * math.sin(t * 2.6)) for t in np.linspace(0, 1, 12)]
    d.line(pts, fill=(170, 120, 60), width=int(S * 0.035))
    sx, sy = pts[-1]
    spark = shape_points("star", sx, sy, S * 0.09)
    d.polygon(spark, fill=(255, 210, 60))
    d.polygon(shape_points("star", sx, sy, S * 0.045), fill=(255, 255, 220))
    if kind == SUPER:
        d.ellipse([cx - r * 0.78, cy - r * 0.78, cx + r * 0.78, cy + r * 0.78], outline=(255, 214, 80),
                  width=int(S * 0.03))
        d.polygon(shape_points("star", cx, cy, r * 0.5), fill=(255, 236, 140))
    return img.resize((size, size), Image.LANCZOS)


_sprite_cache = {}


def item_colors():
    return T.ITEM_SETS[_TPL["items"]]["colors"]


def sprite(piece, size):
    size = max(4, int(size) // 2 * 2)
    items = _TPL["items"]
    key = (items if piece < BOMB else "", piece, size)
    if key not in _sprite_cache:
        if piece >= BOMB:
            _sprite_cache[key] = bomb_sprite(piece, size)
        elif items == "kim-cuong":
            _sprite_cache[key] = gem_sprite(piece, size)
        else:
            png = load_png_asset(f"{items}/item_{piece}.png", size)
            _sprite_cache[key] = png if png is not None else T.item_sprite(items, piece, size)
    return _sprite_cache[key]


# ============================================================================
# Mô phỏng game -> dòng thời gian (timeline) các bước
# ============================================================================
class Step:
    __slots__ = ("kind", "start", "n", "data")

    def __init__(self, kind, start, n, data):
        self.kind, self.start, self.n, self.data = kind, start, n, data


class GemGame:
    def __init__(self, cfg):
        self.cfg = cfg
        self.R, self.C = cfg["rows"], cfg["cols"]
        self.rng = random.Random(cfg["seed"])
        self.fps = cfg["fps"]
        self.speed = max(0.25, float(cfg.get("speed", 1.0)))
        self.total = int(cfg["duration"] * self.fps)                    # số khung hình video
        end_card = 0 if cfg.get("nen") else cfg["end_card"]              # chế độ nền: không có end card
        self.end_frame = self.total - int(end_card * self.fps)
        # Game mô phỏng theo nhịp gốc; khi render, 1 khung video = `speed` khung game.
        self.base_total = int(self.total * self.speed)
        self.base_end = int(self.end_frame * self.speed)
        self.steps = []
        self.events = []      # (frame, tên âm thanh, tham số)
        self.frame = 0
        self.score = 0
        self.stats = {"moves": 0, "explosions": 0, "max_combo": 0, "max_chain": 0}
        self.board = self.new_board()
        self.cursor = ((self.R - 1) / 2, (self.C - 1) / 2)   # vị trí ngón tay (hàng, cột)

    # ---------- bàn cờ ----------
    def new_board(self):
        b = [[None] * self.C for _ in range(self.R)]
        for r in range(self.R):
            for c in range(self.C):
                while True:
                    p = self.rng.randrange(len(GEM_COLORS))
                    if c >= 2 and b[r][c - 1] == p == b[r][c - 2]:
                        continue
                    if r >= 2 and b[r - 1][c] == p == b[r - 2][c]:
                        continue
                    break
                b[r][c] = p
        return b

    def spawn(self):
        x = self.rng.random()
        if x < self.cfg["super_spawn"]:
            return SUPER
        if x < self.cfg["super_spawn"] + self.cfg["bomb_spawn"]:
            return BOMB
        return self.rng.randrange(len(GEM_COLORS))

    def inside(self, r, c):
        return 0 <= r < self.R and 0 <= c < self.C

    def find_runs(self, b=None):
        b = b or self.board
        runs = []
        for r in range(self.R):
            c = 0
            while c < self.C:
                p = b[r][c]
                e = c
                if p is not None and p < BOMB:
                    while e + 1 < self.C and b[r][e + 1] == p:
                        e += 1
                    if e - c + 1 >= 3:
                        runs.append([(r, k) for k in range(c, e + 1)])
                c = e + 1
        for c in range(self.C):
            r = 0
            while r < self.R:
                p = b[r][c]
                e = r
                if p is not None and p < BOMB:
                    while e + 1 < self.R and b[e + 1][c] == p:
                        e += 1
                    if e - r + 1 >= 3:
                        runs.append([(k, c) for k in range(r, e + 1)])
                r = e + 1
        return runs

    def copy_board(self):
        return [row[:] for row in self.board]

    # ---------- timeline ----------
    def add_step(self, kind, n, **data):
        data.setdefault("board", self.copy_board())
        data.setdefault("score0", self.score)
        data.setdefault("score1", self.score)
        self.steps.append(Step(kind, self.frame, n, data))
        self.frame += n

    def sound(self, name, frame=None, **kw):
        self.events.append((self.frame if frame is None else frame, name, kw))

    # ---------- bot chọn nước đi ----------
    def bombs_near(self, r, c, radius):
        n = 0
        for rr in range(r - radius, r + radius + 1):
            for cc in range(c - radius, c + radius + 1):
                if (rr, cc) != (r, c) and self.inside(rr, cc) and (self.board[rr][cc] or 0) >= BOMB:
                    n += 1
        return n

    def best_move(self):
        """Chọn nước đi. Với xác suất `skill` chọn nước tốt nhất, còn lại chọn một nước hợp lệ bất kỳ
        (như người thật: không phải lúc nào cũng thấy nước hay nhất)."""
        b = self.board
        moves = []
        for r in range(self.R):
            for c in range(self.C):
                for dr, dc in ((0, 1), (1, 0)):
                    r2, c2 = r + dr, c + dc
                    if not self.inside(r2, c2):
                        continue
                    pa, pb = b[r][c], b[r2][c2]
                    if pa >= BOMB or pb >= BOMB:
                        score = 0
                        for (rr, cc), p in (((r2, c2), pa), ((r, c), pb)):
                            if p >= BOMB:
                                rad = 2 if p == SUPER else 1
                                score += 5 + 4 * rad + 7 * self.bombs_near(rr, cc, rad)
                    else:
                        b[r][c], b[r2][c2] = pb, pa
                        runs = self.find_runs()
                        b[r][c], b[r2][c2] = pa, pb
                        if not runs:
                            continue
                        score = sum(len(run) + (4 if len(run) >= 4 else 0) for run in runs)
                        # thích nước đi ở nửa dưới (dễ tạo dây chuyền rơi)
                        score += 0.15 * max(r, r2)
                    score += self.rng.random() * 2.5
                    moves.append((score, (r, c), (r2, c2)))
        if not moves:
            return None
        if self.rng.random() < self.cfg["skill"]:
            return max(moves)
        return self.rng.choice(moves)

    # ---------- xử lý vỡ / nổ ----------
    def resolve(self, trigger=()):
        combo = 0
        pending = list(trigger)
        while combo < 40:
            runs = self.find_runs()
            matched = {cell for run in runs for cell in run}
            heap = [(0, pos) for pos in pending]
            for (r, c) in matched:
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if self.inside(rr, cc) and self.board[rr][cc] >= BOMB:
                        heap.append((CHAIN_DELAY, (rr, cc)))
            pending = []
            if not matched and not heap:
                break
            combo += 1
            heapq.heapify(heap)

            delay = {cell: 0 for cell in matched}
            explosions = []
            seen = set()
            while heap:
                t, (r, c) = heapq.heappop(heap)
                if (r, c) in seen:
                    continue
                seen.add((r, c))
                rad = 2 if self.board[r][c] == SUPER else 1
                explosions.append(((r, c), rad, t))
                delay[(r, c)] = min(delay.get((r, c), 999), t)
                for rr in range(r - rad, r + rad + 1):
                    for cc in range(c - rad, c + rad + 1):
                        if not self.inside(rr, cc) or (rr, cc) in seen:
                            continue
                        if self.board[rr][cc] >= BOMB:
                            heapq.heappush(heap, (t + CHAIN_DELAY, (rr, cc)))
                        else:
                            delay[(rr, cc)] = min(delay.get((rr, cc), 999), t + 1)

            specials = {}
            for run in runs:
                if len(run) >= 5:
                    specials[run[len(run) // 2]] = SUPER
                elif len(run) == 4:
                    specials.setdefault(run[1], BOMB)

            blasted = len(delay) - len(matched)
            gained = (len(matched) * 10 + blasted * 20 + len(explosions) * 50) * combo
            n = max(delay.values()) + CLEAR_FRAMES + (4 if combo >= 2 else 0)
            start = self.frame
            self.add_step("clear", n, delay=delay, explosions=explosions, specials=specials,
                          combo=combo, gained=gained, score1=self.score + gained)
            if matched:
                self.sound("pop", start, pitch=1 + 0.12 * (combo - 1))
            for pos, rad, t in explosions:
                self.sound("boom", start + t, big=rad == 2)
            if combo >= 3 or specials:
                self.sound("coin", start + 3)

            self.score += gained
            self.stats["explosions"] += len(explosions)
            self.stats["max_combo"] = max(self.stats["max_combo"], combo)
            self.stats["max_chain"] = max(self.stats["max_chain"], len(explosions))
            for (r, c) in delay:
                self.board[r][c] = None
            for (r, c), p in specials.items():
                self.board[r][c] = p
            self.fall()

    def fall(self):
        moves = []
        max_d = 0
        new = [[None] * self.C for _ in range(self.R)]
        for c in range(self.C):
            w = self.R - 1
            for r in range(self.R - 1, -1, -1):
                p = self.board[r][c]
                if p is not None:
                    moves.append((p, r, w, c))
                    new[w][c] = p
                    max_d = max(max_d, w - r)
                    w -= 1
            missing = w + 1
            for target in range(w, -1, -1):
                p = self.spawn()
                moves.append((p, target - missing, target, c))
                new[target][c] = p
            max_d = max(max_d, missing)
        if max_d == 0:
            return
        self.add_step("fall", min(14, 5 + 2 * max_d), moves=moves)
        self.sound("land")
        self.board = new

    # ---------- mưa bom ----------
    def bomb_rain(self):
        self.add_step("warn", 36)
        self.sound("alarm", self.frame - 36)
        cells = [(r, c) for r in range(self.R) for c in range(self.C) if self.board[r][c] < BOMB]
        picks = self.rng.sample(cells, min(self.cfg["rain_count"], len(cells)))
        drops = [(pos, SUPER if i == 0 and self.rng.random() < 0.35 else BOMB) for i, pos in enumerate(picks)]
        self.add_step("rain", 16, drops=drops)
        self.sound("land")
        for (r, c), p in drops:
            self.board[r][c] = p
        self.resolve(trigger=[pos for pos, _ in drops])

    # ---------- nhịp người chơi ----------
    def think(self, a):
        """Ngón tay rê trên bàn (đôi khi ghé viên khác) rồi dừng ở viên sẽ chạm."""
        cfg = self.cfg
        n = int(self.rng.uniform(cfg["think_min"], cfg["think_max"]) * self.fps)
        path = [self.cursor]
        if self.rng.random() < cfg["decoy_chance"]:
            r = min(self.R - 1, max(0, a[0] + self.rng.choice((-2, -1, 1, 2))))
            c = min(self.C - 1, max(0, a[1] + self.rng.choice((-2, -1, 1, 2))))
            path.append((r, c))
            n += int(0.25 * self.fps)
        path.append(a)
        self.add_step("think", max(4, n), path=path)

    # ---------- chạy cả ván ----------
    def play(self):
        fps = self.fps
        rain_every = self.cfg["rain_every"]
        next_rain = rain_every * fps if rain_every else None
        self.add_step("idle", int(0.8 * fps))
        while self.frame < self.base_end - 20:
            if next_rain is not None and self.frame >= next_rain:
                self.bomb_rain()
                next_rain += rain_every * fps
                continue
            move = self.best_move()
            if move is None:   # hết nước đi: xáo lại bàn
                self.board = self.new_board()
                self.add_step("idle", 10)
                continue
            _, a, b = move
            if self.rng.random() < 0.5:     # người thật có thể chạm viên nào trước cũng được
                a, b = b, a
            self.think(a)
            swipe = max(2, round(self.cfg["swipe_time"] * self.fps))
            self.add_step("select", max(2, round(self.cfg["touch_time"] * self.fps)), a=a, b=b)
            self.add_step("swap", swipe, a=a, b=b)
            self.sound("swap", self.frame - swipe)
            (r1, c1), (r2, c2) = a, b
            self.board[r1][c1], self.board[r2][c2] = self.board[r2][c2], self.board[r1][c1]
            trigger = [p for p in (a, b) if self.board[p[0]][p[1]] >= BOMB]
            self.stats["moves"] += 1
            self.cursor = b
            before = len(self.steps)
            self.resolve(trigger)
            combos = sum(1 for st in self.steps[before:] if st.kind == "clear")
            self.add_step("idle", 3 + 2 * min(combos, 3))   # dây chuyền dài thì dừng xem lâu hơn
        self.add_step("idle", max(1, self.base_total - self.frame))
        self.starts = [s.start for s in self.steps]
        return self

    def step_at(self, base_frame):
        i = bisect.bisect_right(self.starts, base_frame) - 1
        return self.steps[max(0, i)]


# ============================================================================
# Vẽ khung hình
# ============================================================================
class Renderer:
    def __init__(self, game, cfg):
        self.g, self.cfg = game, cfg
        self.th = set_template(cfg.get("theme", "dem"), cfg.get("items", "kim-cuong"))
        self.W, self.H = cfg["width"], cfg["height"]
        self.cell = (self.W - 120) // game.C
        self.bx = (self.W - self.cell * game.C) // 2
        self.by = 560
        self.bw, self.bh = self.cell * game.C, self.cell * game.R
        self.piece_size = int(self.cell * 0.9)
        self.bg = self.build_background()
        self.clip_top = self.by  # viên mới rơi từ trên xuống bị che dưới mép bàn
        self.bg_top = self.bg.crop((0, 0, self.W, self.clip_top))
        self.nen = bool(cfg.get("nen"))
        # Chế độ nền không có hook: chỗ đó để trống cho bên dựng video đặt tên truyện.
        self.hook_img = None if self.nen or not cfg.get("hook") else text_image(
            wrap_text(cfg["hook"], load_font(80), self.W - 100), load_font(80),
            self.th["text"], stroke_fill=self.th["stroke"])
        self.level = int(cfg.get("level") or 0) or (cfg["seed"] % 20) + 1
        self.top = self.leaderboard()
        # khung hình (video) lúc điểm của người chơi vượt từng hạng, để hiện "VƯỢT TOP n!"
        self.pass_frame = {}
        for st in game.steps:
            if st.kind != "clear":
                continue
            for i, v in enumerate(self.top):
                if i not in self.pass_frame and st.data["score0"] < v <= st.data["score1"]:
                    self.pass_frame[i] = int((st.start + st.n * 0.5) / game.speed)

    def leaderboard(self):
        """Điểm Top 1-3. Tự động: Top 3 đặt quanh điểm cuối ván để người xem hồi hộp chờ vượt."""
        raw = str(self.cfg.get("leaderboard") or "").strip()
        if raw:
            parts = re.split(r"[;|/\s]+", raw)
            if len(parts) == 1:
                parts = raw.split(",")
            vals = [int(re.sub(r"\D", "", x)) for x in parts if re.sub(r"\D", "", x)]
            if len(vals) >= 3:
                return sorted(vals[:3], reverse=True)
        rng = random.Random(self.cfg["seed"] * 9973 + 11)
        t3 = max(100, self.g.score) * rng.uniform(0.82, 1.12)
        t2 = t3 * rng.uniform(1.06, 1.18)
        t1 = t2 * rng.uniform(1.06, 1.2)
        return [int(round(v, -1)) for v in (t1, t2, t3)]

    def rank_of(self, score):
        if score < self.top[2]:
            return None
        return 1 + sum(1 for v in self.top if v > score)

    def build_background(self):
        W, H = self.W, self.H
        t = np.linspace(0, 1, H)[:, None]
        th = self.th
        top, bot = np.array(th["bg"][0]), np.array(th["bg"][1])
        grad = (top * (1 - t) + bot * t)[:, None, :].repeat(W, axis=1)
        img = Image.fromarray(grad.astype(np.uint8).reshape(H, W, 3), "RGB")
        d = ImageDraw.Draw(img, "RGBA")
        T.draw_deco(d, th, W, H, random.Random(3))
        pad = 18
        d.rounded_rectangle([self.bx - pad, self.by - pad, self.bx + self.bw + pad, self.by + self.bh + pad],
                            radius=34, fill=th["board"], outline=th["board_line"], width=4)
        for r in range(self.g.R):
            for c in range(self.g.C):
                x, y = self.bx + c * self.cell, self.by + r * self.cell
                d.rounded_rectangle([x + 3, y + 3, x + self.cell - 3, y + self.cell - 3], radius=14,
                                    fill=th["cells"][(r + c) % 2])
        return img

    def cell_center(self, r, c):
        return self.bx + c * self.cell + self.cell / 2, self.by + r * self.cell + self.cell / 2

    def paste(self, img, piece, x, y, scale=1.0):
        if scale <= 0.05:
            return
        spr = sprite(piece, self.piece_size * scale)
        img.paste(spr, (int(x - spr.width / 2), int(y - spr.height / 2)), spr)

    def piece_scale(self, piece, frame):
        return 1 + 0.05 * math.sin(frame * 0.35) if piece >= BOMB else 1.0

    def draw_board(self, img, board, frame, ox=0, oy=0, skip=()):
        for r in range(self.g.R):
            for c in range(self.g.C):
                p = board[r][c]
                if p is None or (r, c) in skip:
                    continue
                x, y = self.cell_center(r, c)
                self.paste(img, p, x + ox, y + oy, self.piece_scale(p, frame))

    def shake(self, step, local, frame):
        if step.kind != "clear":
            return 0, 0
        amp = 0
        for _, rad, t in step.data["explosions"]:
            k = local - t
            if 0 <= k < 8:
                amp = max(amp, (8 + 8 * rad) * (1 - k / 8))
        return amp * math.sin(frame * 1.9), amp * math.cos(frame * 2.7)

    def render(self, frame):
        g = self.g
        step = g.step_at(frame * g.speed)
        local = frame * g.speed - step.start
        t = clamp01(local / max(1, step.n))
        img = self.bg.copy()
        d = ImageDraw.Draw(img, "RGBA")
        data = step.data
        board = data["board"]
        ox, oy = self.shake(step, local, frame)
        fx = []   # hiệu ứng vẽ sau lớp cắt phía trên

        if step.kind in ("idle", "warn"):
            self.draw_board(img, board, frame)
        elif step.kind == "think":
            self.draw_board(img, board, frame)
            path = data["path"]
            segs = len(path) - 1
            move = clamp01(t / 0.75)                  # 75% thời gian đầu: rê tay; còn lại: dừng
            i = min(segs - 1, int(move * segs))
            k = ease_out(clamp01(move * segs - i))
            (r0, c0), (r1, c1) = path[i], path[i + 1]
            x, y = self.cell_center(r0 + (r1 - r0) * k, c0 + (c1 - c0) * k)
            wob = 4 * math.sin(frame * 0.3)
            fx.append(("cursor", x + 20 + wob, y + 26))
        elif step.kind == "select":
            self.draw_board(img, board, frame)
            r, c = data["a"]
            x, y = self.bx + c * self.cell, self.by + r * self.cell
            d.rounded_rectangle([x + 2, y + 2, x + self.cell - 2, y + self.cell - 2], radius=16,
                                outline=(255, 255, 255, int(160 + 95 * ease_out(t))), width=6)
            ax, ay = self.cell_center(*data["a"])
            fx.append(("cursor", ax + 20, ay + 26 - 10 * ease_out(t)))
        elif step.kind == "swap":
            a, b = data["a"], data["b"]
            self.draw_board(img, board, frame, skip=(a, b))
            ax, ay = self.cell_center(*a)
            bx_, by_ = self.cell_center(*b)
            k = ease_out(t)
            pa, pb = board[a[0]][a[1]], board[b[0]][b[1]]
            self.paste(img, pb, bx_ + (ax - bx_) * k, by_ + (ay - by_) * k, self.piece_scale(pb, frame))
            self.paste(img, pa, ax + (bx_ - ax) * k, ay + (by_ - ay) * k, 1.12)
            fx.append(("cursor", ax + (bx_ - ax) * k + 20, ay + (by_ - ay) * k + 16))
        elif step.kind == "clear":
            self.render_clear(img, d, step, local, t, frame, ox, oy, fx)
        elif step.kind == "fall":
            k = ease_in(t)
            for p, r0, r1, c in data["moves"]:
                x, y = self.cell_center(r0 + (r1 - r0) * k, c)
                self.paste(img, p, x, y, self.piece_scale(p, frame))
        elif step.kind == "rain":
            self.draw_board(img, board, frame)
            for i, ((r, c), p) in enumerate(data["drops"]):
                kk = ease_in(clamp01(t * 1.3 - i * 0.05))
                x, y = self.cell_center(r, c)
                self.paste(img, p, x, y - (1 - kk) * (self.by + self.cell * (r + 2)), 1.15)

        img.paste(self.bg_top, (0, 0))
        self.draw_fx(img, d, fx)
        if self.cfg.get("hud", True):
            self.draw_hud(img, d, step, t, frame)
        self.draw_hook(img, frame)
        if step.kind == "warn":
            self.draw_warning(img, d, local)
        if not self.nen:
            self.draw_flash(d, step, local)
        if frame >= g.end_frame and not self.nen:
            self.draw_end_card(img, frame)
        return img

    def render_clear(self, img, d, step, local, t, frame, ox, oy, fx):
        data = step.data
        board, delay = data["board"], data["delay"]
        for r in range(self.g.R):
            for c in range(self.g.C):
                p = board[r][c]
                if p is None:
                    continue
                x, y = self.cell_center(r, c)
                x, y = x + ox, y + oy
                if (r, c) not in delay:
                    self.paste(img, p, x, y, self.piece_scale(p, frame))
                    continue
                k = local - delay[(r, c)]
                if k < 0:
                    self.paste(img, p, x, y, self.piece_scale(p, frame))
                elif k < 6:
                    self.paste(img, p, x, y, (1 + 0.2 * math.sin(k / 6 * math.pi)) * (1 - k / 6))
                if 0 <= k < 16:
                    fx.append(("burst", x, y, p, k, step.start * 131 + r * 17 + c))
        # viên đặc biệt vừa tạo thì hiện dần lên
        for (r, c), p in data["specials"].items():
            if t > 0.5:
                x, y = self.cell_center(r, c)
                self.paste(img, p, x + ox, y + oy, ease_out_back(clamp01((t - 0.5) * 2)))
        for (r, c), rad, tt in data["explosions"]:
            k = local - tt
            if 0 <= k < 14:
                x, y = self.cell_center(r, c)
                fx.append(("blast", x + ox, y + oy, rad, k))
        if data["gained"]:
            cells = list(delay)
            cx = sum(self.cell_center(*p)[0] for p in cells) / len(cells)
            cy = sum(self.cell_center(*p)[1] for p in cells) / len(cells)
            fx.append(("points", cx, cy - 70 * ease_out(t), f"+{fmt_num(data['gained'])}", t))
        if data["combo"] >= 2:
            fx.append(("combo", data["combo"], t))

    def draw_fx(self, img, d, fx):
        for item in fx:
            kind = item[0]
            if kind == "cursor":
                _, x, y = item
                d.ellipse([x - 46, y - 46, x + 46, y + 46], fill=(255, 255, 255, 60))
                d.ellipse([x - 28, y - 28, x + 28, y + 28], fill=(255, 255, 255, 240),
                          outline=self.th["cursor_line"] + (255,), width=6)
            elif kind == "burst":
                _, x, y, p, k, seed = item
                rng = random.Random(seed)
                col = (255, 190, 70) if p >= BOMB else item_colors()[p]
                for _ in range(7):
                    ang = rng.uniform(0, 2 * math.pi)
                    spd = rng.uniform(5, 13)
                    px = x + math.cos(ang) * spd * k
                    py = y + math.sin(ang) * spd * k + 0.9 * k * k
                    s = max(1.0, rng.uniform(7, 13) * (1 - k / 16))
                    d.polygon(shape_points("diamond", px, py, s), fill=col + (int(255 * (1 - k / 16)),))
            elif kind == "blast":
                _, x, y, rad, k = item
                kk = k / 14
                R = self.cell * (0.4 + (rad + 0.7) * ease_out(kk))
                a = int(230 * (1 - kk))
                d.ellipse([x - R, y - R, x + R, y + R], outline=(255, 200, 80, a), width=max(2, int(20 * (1 - kk))))
                if k < 5:
                    core = self.cell * (0.9 + 0.3 * rad) * (1 - k / 5)
                    d.ellipse([x - core, y - core, x + core, y + core], fill=(255, 245, 200, 200))
                    d.ellipse([x - core * 0.6, y - core * 0.6, x + core * 0.6, y + core * 0.6],
                              fill=(255, 140, 40, 200))
            elif kind == "points":
                _, x, y, text, t = item
                a = int(255 * (1 - clamp01((t - 0.65) / 0.35)))
                d.text((x, y), text, font=load_font(64), fill=(255, 236, 120, a), anchor="mm",
                       stroke_width=6, stroke_fill=(60, 20, 10, a))
            elif kind == "combo":
                _, combo, t = item
                s = ease_out_back(clamp01(t * 3))
                font = load_font(max(10, int(110 * s)))
                col = [(255, 236, 120), (255, 160, 60), (255, 90, 90), (255, 110, 230)][min(3, (combo - 2) // 2)]
                d.text((self.W / 2, self.by + self.bh / 2), f"COMBO x{combo}!", font=font, fill=col, anchor="mm",
                       stroke_width=9, stroke_fill=self.th["stroke"])

    def draw_hud(self, img, d, step, t, frame):
        """HUD trên cùng: Top 1-3 (trái) · Level + đồng hồ (giữa) · You (phải).
        Phần dưới bàn cờ để trống cho phụ đề / quảng cáo."""
        g, th = self.g, self.th
        stroke = th["stroke"]
        score = step.data["score0"] + (step.data["score1"] - step.data["score0"]) * ease_out(t)
        rank = self.rank_of(score)

        x0, x1, y0, y1 = 30, self.W - 30, 34, 262
        d.rounded_rectangle([x0, y0, x1, y1], radius=34, fill=th["hud"], outline=th["hud_line"], width=3)
        rows = [82, 148, 214]
        medal = [(255, 200, 50), (200, 210, 230), (220, 140, 80)]
        f_row = load_font(50)
        for i, (v, y) in enumerate(zip(self.top, rows)):
            beaten = score >= v
            a = 110 if beaten else 255
            d.rounded_rectangle([56, y - 24, 164, y + 24], radius=24, fill=medal[i] + (a,))
            d.text((110, y + 1), f"TOP {i + 1}", font=load_font(32), fill=(30, 16, 50, a), anchor="mm")
            d.text((184, y + 2), fmt_num(v), font=f_row, fill=th["text"] + (a,), anchor="lm",
                   stroke_width=4, stroke_fill=stroke + (a,))

        # giữa: Level + đồng hồ đếm ngược
        cx = 590
        d.rounded_rectangle([cx - 105, rows[0] - 28, cx + 105, rows[0] + 28], radius=28, fill=th["level"],
                            outline=th["level_line"], width=3)
        d.text((cx, rows[0] + 1), f"Level {self.level}", font=load_font(40), fill=(255, 255, 255), anchor="mm")
        left = max(0, math.ceil((g.end_frame - frame) / g.fps))
        warn = 0 < left <= 10 and not self.nen
        col = (255, 90, 90) if warn else th["text"]
        s = 1 + 0.08 * max(0.0, math.sin(frame / g.fps * math.pi * 2)) if warn else 1
        clk_y = rows[1] + 30
        r = 25 * s
        cxc = cx - 104
        d.ellipse([cxc - r, clk_y - r, cxc + r, clk_y + r], outline=col, width=6)
        d.line([(cxc, clk_y), (cxc, clk_y - r * 0.6)], fill=col, width=5)
        d.line([(cxc, clk_y), (cxc + r * 0.45, clk_y + r * 0.2)], fill=col, width=5)
        d.text((cx + 28, clk_y + 2), f"{left // 60}:{left % 60:02d}", font=load_font(int(78 * s)), fill=col,
               anchor="mm", stroke_width=5, stroke_fill=stroke)

        # phải: điểm của người chơi
        rx0 = 730
        d.line([(rx0 - 24, y0 + 30), (rx0 - 24, y1 - 30)], fill=th["hud_line"], width=3)
        rcx = (rx0 + x1) / 2
        d.text((rcx, rows[0] - 2), "YOU", font=load_font(40), fill=th["you"], anchor="mm",
               stroke_width=3, stroke_fill=stroke)
        d.text((rcx, rows[1] + 4), fmt_num(score), font=load_font(72), fill=th["text"], anchor="mm",
               stroke_width=5, stroke_fill=stroke)
        fresh = [i for i, f0 in self.pass_frame.items() if 0 <= frame - f0 < int(1.6 * g.fps)]
        if fresh:
            i = min(fresh)
            k = frame - self.pass_frame[i]
            sc = ease_out_back(clamp01(k / 8))
            d.text((rcx, rows[2]), f"VƯỢT TOP {i + 1}!", font=load_font(max(10, int(44 * sc))),
                   fill=th["accent"], anchor="mm", stroke_width=5, stroke_fill=stroke)
        elif rank:
            d.text((rcx, rows[2]), f"Hạng #{rank}", font=load_font(42), fill=th["accent"], anchor="mm",
                   stroke_width=3, stroke_fill=stroke)
        else:
            d.text((rcx, rows[2]), f"Còn {fmt_num(self.top[2] - score)} vào top",
                   font=load_font(30, "Bold"), fill=th["muted"], anchor="mm")

    def draw_hook(self, img, frame):
        """Câu hook (nảy lên lúc đầu). Tách khỏi draw_hud để tắt HUD vẫn còn hook."""
        if self.hook_img is None:
            return
        s = ease_out_back(clamp01(frame / 12)) if frame < 12 else 1 + 0.02 * math.sin(frame * 0.12)
        hook = self.hook_img
        if abs(s - 1) > 0.005:
            hook = hook.resize((max(1, int(hook.width * s)), max(1, int(hook.height * s))), Image.BILINEAR)
        img.paste(hook, (int(self.W / 2 - hook.width / 2), int(405 - hook.height / 2)), hook)

    def draw_warning(self, img, d, local):
        if self.nen:
            # bản dịu: băng hẹp, mờ hơn, không phủ đỏ cả màn, không nhấp nháy
            y = self.by + self.bh / 2
            a = int(170 * min(1.0, local / 6, (36 - local) / 6))
            if a <= 0:
                return
            d.rounded_rectangle([self.W * 0.2, y - 52, self.W * 0.8, y + 52], radius=30,
                                fill=(150, 30, 40, a))
            d.text((self.W / 2, y), "MƯA BOM", font=load_font(72), fill=(255, 240, 150, a),
                   anchor="mm", stroke_width=5, stroke_fill=(60, 0, 0, a))
            return
        on = (local // 6) % 2 == 0
        d.rectangle([0, 0, self.W, self.H], fill=(255, 40, 40, 34 if on else 12))
        y = self.by + self.bh / 2
        d.rectangle([0, y - 90, self.W, y + 90], fill=(180, 20, 30, 220))
        s = ease_out_back(clamp01(local / 8))
        d.text((self.W / 2, y), "MƯA BOM!", font=load_font(max(10, int(140 * s))), fill=(255, 240, 120),
               anchor="mm", stroke_width=10, stroke_fill=(60, 0, 0))

    def draw_flash(self, d, step, local):
        # chớp sáng nhẹ và rất ngắn (thân thiện với người nhạy cảm ánh sáng)
        if step.kind != "clear":
            return
        for _, rad, t in step.data["explosions"]:
            if rad == 2 and 0 <= local - t < 2:
                d.rectangle([0, 0, self.W, self.H], fill=(255, 240, 210, 40))
                return

    def draw_end_card(self, img, frame):
        g = self.g
        k = clamp01((frame - g.end_frame) / 10)
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([0, 0, self.W, self.H], fill=(8, 4, 24, int(175 * k)))
        s = ease_out_back(k)
        if s < 0.05:
            return
        cy = self.H / 2
        pw, ph = 900 * s, 820 * s
        th = self.th
        d.rounded_rectangle([self.W / 2 - pw / 2, cy - ph / 2, self.W / 2 + pw / 2, cy + ph / 2], radius=50,
                            fill=th["end"], outline=th["end_line"], width=6)
        f = lambda size: load_font(max(10, int(size * s)))
        d.text((self.W / 2, cy - 300 * s), "HẾT GIỜ!", font=f(110), fill=th["accent"], anchor="mm",
               stroke_width=8, stroke_fill=th["stroke"])
        d.text((self.W / 2, cy - 170 * s), "Tổng điểm", font=f(52), fill=th["muted"], anchor="mm")
        d.text((self.W / 2, cy - 70 * s), fmt_num(g.score), font=f(130), fill=th["text"], anchor="mm",
               stroke_width=8, stroke_fill=th["stroke"])
        rank = self.rank_of(g.score)
        msg = f"Hạng #{rank} bảng xếp hạng!" if rank else f"Thiếu {fmt_num(self.top[2] - g.score)} điểm để vào Top 3"
        d.text((self.W / 2, cy + 45 * s), msg, font=f(50), fill=th["you"], anchor="mm",
               stroke_width=3, stroke_fill=th["stroke"])
        lines = wrap_text(self.cfg["question"], f(58), pw - 60)
        draw_lines(d, self.W / 2, cy + 215 * s, lines, f(58), th["accent"], stroke=6, stroke_fill=th["stroke"])


# ============================================================================
# Âm thanh tự tổng hợp
# ============================================================================
def _t(dur):
    return np.arange(int(SR * dur)) / SR


def s_pop(pitch=1.0):
    t = _t(0.14)
    f = (520 + 700 * t / t[-1]) * pitch
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28) * 0.55


def s_swap():
    t = _t(0.09)
    noise = np.random.default_rng(1).normal(0, 1, len(t))
    noise = np.convolve(noise, np.ones(12) / 12, mode="same")
    return noise * np.sin(np.pi * t / t[-1]) * 0.35


@lru_cache(maxsize=None)
def s_boom(big=False):
    dur = 0.9 if big else 0.6
    t = _t(dur)
    rng = np.random.default_rng(7 if big else 5)
    noise = np.convolve(rng.normal(0, 1, len(t)), np.ones(30) / 30, mode="same") * 3
    thump = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t * 6) + 38) / SR)
    out = (noise * 0.8 + thump * 0.9) * np.exp(-t * (5 if big else 8))
    return out * (0.95 if big else 0.7)


def s_coin():
    a, b = _t(0.08), _t(0.22)
    sq = lambda f, t: np.sign(np.sin(2 * np.pi * f * t)) * 0.25 + np.sin(2 * np.pi * f * t) * 0.35
    return np.concatenate([sq(988, a) * np.exp(-a * 10), sq(1319, b) * np.exp(-b * 12)]) * 0.5


def s_alarm():
    t = _t(1.2)
    f = 720 + 260 * np.sin(2 * np.pi * 3 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.minimum(1, t * 30) * np.minimum(1, (t[-1] - t) * 8)
    return (np.sin(ph) * 0.6 + np.sign(np.sin(ph)) * 0.12) * env * 0.5


def s_land():
    t = _t(0.1)
    return np.sin(2 * np.pi * 140 * t) * np.exp(-t * 40) * 0.35


def music(total_sec):
    """Nhạc nền đơn giản tự tạo (không bản quyền). Thay bằng nhạc thư viện của nền tảng khi đăng."""
    bpm = 112
    beat = 60 / bpm
    t = _t(total_sec)
    out = np.zeros_like(t)
    chords = [(261.6, 329.6, 392.0), (196.0, 246.9, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 349.2)]
    bar = beat * 4
    for i, start in enumerate(np.arange(0, total_sec, bar)):
        s, e = int(start * SR), min(len(t), int((start + bar) * SR))
        tt = t[s:e] - start
        env = np.minimum(1, tt * 4) * np.minimum(1, (bar - tt) * 4)
        for f in chords[i % 4]:
            out[s:e] += np.sin(2 * np.pi * f * tt) * 0.09 * env
        root = chords[i % 4][0] / 2
        for k in range(4):   # bass + trống
            bs = int((start + k * beat) * SR)
            if bs >= len(t):
                break
            tb = t[bs:min(len(t), bs + int(beat * SR))] - t[bs]
            out[bs:bs + len(tb)] += np.sin(2 * np.pi * root * tb) * np.exp(-tb * 4) * 0.25
            out[bs:bs + len(tb)] += np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-tb * 30)) / SR) \
                * np.exp(-tb * 14) * 0.45
    fade = np.minimum(1, np.minimum(t / 0.5, (total_sec - t) / 1.5))
    return out * fade


def build_audio(game, cfg, path):
    total_sec = game.total / game.fps
    n = int(total_sec * SR)
    mixbuf = np.zeros(n)
    if cfg["music_volume"] > 0:
        mixbuf += music(total_sec) * cfg["music_volume"]
    makers = {"pop": s_pop, "swap": s_swap, "boom": s_boom, "coin": s_coin, "alarm": s_alarm, "land": s_land}
    per_frame = {}
    for frame, name, kw in game.events:
        if frame >= game.base_total:
            continue
        if name == "boom":   # nhiều vụ nổ cùng lúc thì bớt âm lượng
            per_frame[frame] = per_frame.get(frame, 0) + 1
            if per_frame[frame] > 3:
                continue
        snd = makers[name](**kw) * cfg["sfx_volume"]
        s = int(frame / (game.fps * game.speed) * SR)
        e = min(n, s + len(snd))
        mixbuf[s:e] += snd[:e - s]
    mixbuf = np.tanh(mixbuf * 1.1)
    peak = np.max(np.abs(mixbuf)) or 1
    pcm = (mixbuf / peak * 0.92 * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


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
    ap = argparse.ArgumentParser(description="Kim Cương TEE — game tự chơi xuất video dọc")
    ap.add_argument("--seed", type=int, help="số ván (mỗi seed ra một ván khác)")
    ap.add_argument("--out", help="tên file video; chỉ có tên file thì lưu vào output/")
    ap.add_argument("--preview", help="xuất ảnh ở các giây này, ví dụ 5,20,36")
    ap.add_argument("--hook", help="câu hook hiện ở đầu video")
    ap.add_argument("--question", help="câu hỏi cuối video")
    ap.add_argument("--duration", type=float, help="độ dài video (giây)")
    ap.add_argument("--speed", type=float, help="tốc độ chơi: 1 = gốc, 1.3 = nhanh hơn một chút, 2 = rất nhanh")
    ap.add_argument("--theme", choices=list(T.THEMES), help="giao diện: " + ", ".join(
        f"{k} ({v['name']})" for k, v in T.THEMES.items()))
    ap.add_argument("--items", choices=list(T.ITEM_SETS), help="bộ icon: " + ", ".join(
        f"{k} ({v['name']})" for k, v in T.ITEM_SETS.items()))
    ap.add_argument("--set", action="append", default=[], metavar="KHÓA=GIÁ_TRỊ",
                    help="đổi bất kỳ tham số CONFIG, ví dụ --set think_max=2 --set skill=0.4")
    ap.add_argument("--nen", action="store_true",
                    help="chế độ NỀN cho video đọc truyện: không hook, không end card, hiệu ứng dịu")
    args = ap.parse_args()

    cfg = dict(CONFIG)
    if args.nen:
        cfg["nen"] = True
    for key in ("seed", "hook", "question", "duration", "speed", "theme", "items"):
        if getattr(args, key) is not None:
            cfg[key] = getattr(args, key)
    for item in args.set:
        key, _, val = item.partition("=")
        if key not in CONFIG:
            sys.exit(f"Không có tham số '{key}' trong CONFIG.")
        if isinstance(CONFIG[key], bool):
            cfg[key] = val.strip().lower() in ("1", "true", "yes", "co", "có")
        elif isinstance(CONFIG[key], (int, float)):
            cfg[key] = type(CONFIG[key])(float(val))
        else:
            cfg[key] = val

    t0 = time.time()
    game = GemGame(cfg).play()
    renderer = Renderer(game, cfg)
    st = game.stats
    print(f"Ván số {cfg['seed']}: {fmt_num(game.score)} điểm · {st['moves']} nước · {st['explosions']} vụ nổ · "
          f"combo cao nhất x{st['max_combo']} · nổ liên hoàn tối đa {st['max_chain']} · "
          f"{T.THEMES[cfg['theme']]['name']} + {T.ITEM_SETS[cfg['items']]['name']}")

    if args.preview:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for sec in [float(s) for s in args.preview.split(",") if s.strip()]:
            f = min(game.total - 1, int(sec * cfg["fps"]))
            p = OUTPUT / f"kim-cuong_seed{cfg['seed']}_{sec:g}s.png"
            renderer.render(f).save(p)
            print(f"  Đã lưu {p}")
        return

    out = resolve_out(args.out, f"kim-cuong_seed{cfg['seed']}.mp4")
    export_video(game, renderer, cfg, out)
    print(f"Xong: {out}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
