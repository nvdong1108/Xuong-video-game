"""Template giao diện cho game kim cương: 3 giao diện (màu + font) × 3 bộ icon = 9 template.

- THEMES: màu nền, bàn cờ, HUD, font chữ.
- ITEM_SETS: 6 loại viên (kim cương / đồ ăn / trái cây), tất cả vẽ bằng code — không dùng ảnh
  hay emoji của bên thứ ba nên không lo bản quyền.

Muốn thay icon bằng ảnh tự làm: đặt PNG vuông nền trong suốt vào assets/kim-cuong/<mã bộ>/item_0.png … item_5.png
(riêng bộ kim cương vẫn đọc được assets/kim-cuong/gem_0.png … như cũ).
"""
import math

from PIL import Image, ImageDraw, ImageFilter

# ============================================================================
# Giao diện: màu + font
# ============================================================================
THEMES = {
    "dem": {
        "name": "Đêm tím", "font": "Baloo2.ttf", "weight": "ExtraBold", "font_scale": 1.0,
        "bg": ((46, 22, 92), (12, 18, 54)), "deco": "sparkle",
        "board": (0, 0, 0, 120), "board_line": (255, 255, 255, 60),
        "cells": ((255, 255, 255, 22), (255, 255, 255, 10)),
        "hud": (8, 4, 26, 150), "hud_line": (255, 255, 255, 45),
        "level": (124, 92, 255), "level_line": (200, 185, 255),
        "you": (120, 230, 255), "accent": (255, 220, 60), "text": (255, 255, 255),
        "muted": (200, 195, 235), "stroke": (22, 10, 44),
        "end": (40, 20, 84, 240), "end_line": (255, 214, 90), "cursor_line": (40, 20, 70),
    },
    "keo": {
        "name": "Kẹo ngọt", "font": "PaytoneOne.ttf", "weight": None, "font_scale": 0.88,
        "bg": ((255, 190, 220), (255, 234, 200)), "deco": "bubbles",
        "board": (196, 58, 130, 120), "board_line": (255, 255, 255, 230),
        "cells": ((255, 255, 255, 46), (255, 255, 255, 22)),
        "hud": (214, 64, 140, 230), "hud_line": (255, 255, 255, 170),
        "level": (255, 160, 30), "level_line": (255, 230, 160),
        "you": (255, 240, 120), "accent": (255, 236, 90), "text": (255, 255, 255),
        "muted": (255, 222, 238), "stroke": (128, 26, 78),
        "end": (214, 64, 140, 245), "end_line": (255, 255, 255), "cursor_line": (150, 40, 100),
    },
    "neon": {
        "name": "Neon", "font": "ChakraPetch-Bold.ttf", "weight": None, "font_scale": 1.0,
        "bg": ((8, 12, 34), (2, 4, 14)), "deco": "grid",
        "board": (0, 18, 38, 190), "board_line": (0, 229, 255, 170),
        "cells": ((0, 229, 255, 24), (255, 0, 200, 16)),
        "hud": (0, 12, 28, 215), "hud_line": (0, 229, 255, 150),
        "level": (230, 0, 160), "level_line": (255, 140, 230),
        "you": (0, 229, 255), "accent": (255, 232, 0), "text": (255, 255, 255),
        "muted": (150, 200, 230), "stroke": (0, 0, 0),
        "end": (4, 10, 30, 245), "end_line": (0, 229, 255), "cursor_line": (0, 120, 160),
    },
}


def draw_deco(d, theme, W, H, rng):
    """Họa tiết nền theo giao diện."""
    kind = theme["deco"]
    if kind == "sparkle":
        for _ in range(40):
            x, y, r = rng.randrange(W), rng.randrange(H), rng.randrange(4, 14)
            d.polygon([(x, y - r), (x + r * 0.8, y), (x, y + r), (x - r * 0.8, y)],
                      fill=(255, 255, 255, rng.randrange(18, 50)))
    elif kind == "bubbles":
        for _ in range(26):
            x, y, r = rng.randrange(W), rng.randrange(H), rng.randrange(16, 70)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rng.randrange(40, 90)))
        for _ in range(60):   # rắc cốm kẹo
            x, y = rng.randrange(W), rng.randrange(H)
            a = rng.uniform(0, math.pi)
            col = rng.choice([(255, 120, 170), (120, 200, 255), (255, 210, 80), (150, 230, 160)])
            d.line([(x, y), (x + 16 * math.cos(a), y + 16 * math.sin(a))], fill=col + (170,), width=6)
    elif kind == "grid":
        for x in range(0, W, 60):
            d.line([(x, 0), (x, H)], fill=(0, 229, 255, 18), width=2)
        for y in range(0, H, 60):
            d.line([(0, y), (W, y)], fill=(0, 229, 255, 18), width=2)
        for _ in range(30):
            x, y = rng.randrange(0, W, 60), rng.randrange(0, H, 60)
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 0, 200, 120))


# ============================================================================
# Bộ icon
# ============================================================================
ITEM_SETS = {
    "kim-cuong": {"name": "Kim cương", "labels": ["Đỏ", "Vàng", "Lục", "Lam", "Tím", "Ngọc"],
                  "colors": [(236, 62, 86), (255, 178, 36), (60, 204, 112), (54, 142, 246), (172, 92, 242),
                             (78, 226, 228)]},
    "do-an": {"name": "Đồ ăn", "labels": ["Bánh mì", "Bánh bao", "Đùi gà", "Trứng ốp la", "Donut", "Pizza"],
              "colors": [(226, 160, 80), (245, 238, 225), (196, 104, 40), (255, 204, 40), (255, 130, 180),
                         (236, 80, 50)]},
    "trai-cay": {"name": "Trái cây", "labels": ["Dưa hấu", "Cam", "Nho", "Chuối", "Dâu", "Táo xanh"],
                 "colors": [(240, 60, 70), (255, 150, 30), (150, 70, 200), (255, 222, 60), (225, 30, 60),
                            (140, 205, 60)]},
}


def darker(c, k=0.35):
    return tuple(int(v * (1 - k)) for v in c[:3])


def lighter(c, k=0.35):
    return tuple(int(v + (255 - v) * k) for v in c[:3])


def rot(points, cx, cy, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in points]


def ellipse_pts(cx, cy, rx, ry, n=48, deg=0):
    pts = [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return rot(pts, cx, cy, deg) if deg else pts


# ---------- đồ ăn ----------
def food_banh_mi(d, S):
    cx, cy = S / 2, S / 2
    body = ellipse_pts(cx, cy, S * 0.46, S * 0.2, deg=-35)
    d.polygon(body, fill=(214, 146, 64))
    d.polygon(ellipse_pts(cx - S * 0.02, cy - S * 0.03, S * 0.42, S * 0.15, deg=-35), fill=(236, 174, 90))
    for k in (-0.22, 0, 0.22):   # vết khía trên vỏ
        x, y = cx + S * k * math.cos(math.radians(-35)), cy + S * k * math.sin(math.radians(-35))
        cut = ellipse_pts(x, y - S * 0.02, S * 0.07, S * 0.025, deg=20)
        d.polygon(cut, fill=(252, 222, 160))
    d.line(body + [body[0]], fill=(150, 90, 30), width=int(S * 0.016))


def food_banh_bao(d, S):
    cx, cy = S / 2, S * 0.56
    d.chord([cx - S * 0.42, cy - S * 0.4, cx + S * 0.42, cy + S * 0.3], 180, 360, fill=(250, 246, 236))
    d.rounded_rectangle([cx - S * 0.42, cy - S * 0.06, cx + S * 0.42, cy + S * 0.14], radius=S * 0.08,
                        fill=(250, 246, 236))
    d.ellipse([cx - S * 0.38, cy + S * 0.04, cx + S * 0.38, cy + S * 0.18], fill=(226, 218, 200))
    top = (cx, cy - S * 0.36)
    for k in range(-3, 4):   # nếp gấp
        d.line([top, (cx + k * S * 0.1, cy - S * 0.1)], fill=(214, 204, 186), width=int(S * 0.018))
    d.ellipse([cx - S * 0.045, cy - S * 0.4, cx + S * 0.045, cy - S * 0.31], fill=(230, 50, 60))
    d.ellipse([cx - S * 0.3, cy - S * 0.26, cx - S * 0.14, cy - S * 0.16], fill=(255, 255, 255))


def food_dui_ga(d, S):
    cx, cy = S * 0.42, S * 0.42
    # xương
    bx, by = S * 0.72, S * 0.72
    d.line([(cx, cy), (bx, by)], fill=(250, 244, 228), width=int(S * 0.1))
    for ox, oy in ((0.05, -0.02), (-0.02, 0.05)):
        r = S * 0.065
        d.ellipse([bx + S * ox - r, by + S * oy - r, bx + S * ox + r, by + S * oy + r], fill=(250, 244, 228))
    # thịt
    meat = ellipse_pts(cx, cy, S * 0.3, S * 0.23, deg=45)
    d.polygon(meat, fill=(186, 92, 34))
    d.polygon(ellipse_pts(cx - S * 0.03, cy - S * 0.03, S * 0.24, S * 0.16, deg=45), fill=(222, 132, 52))
    d.ellipse([cx - S * 0.16, cy - S * 0.16, cx - S * 0.04, cy - S * 0.08], fill=(255, 200, 130))
    d.line(meat + [meat[0]], fill=(130, 60, 20), width=int(S * 0.016))


def food_trung(d, S):
    cx, cy = S / 2, S / 2
    for a in range(0, 360, 60):   # lòng trắng hình bông
        x, y = cx + S * 0.14 * math.cos(math.radians(a)), cy + S * 0.14 * math.sin(math.radians(a))
        r = S * 0.24
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    d.ellipse([cx - S * 0.34, cy - S * 0.34, cx + S * 0.34, cy + S * 0.34], fill=(255, 255, 255))
    r = S * 0.16
    d.ellipse([cx - r, cy - r + S * 0.02, cx + r, cy + r + S * 0.02], fill=(240, 150, 20))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 196, 30))
    d.ellipse([cx - r * 0.55, cy - r * 0.6, cx - r * 0.05, cy - r * 0.15], fill=(255, 240, 180))


def food_donut(d, S):
    cx, cy = S / 2, S / 2
    R = S * 0.42
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(214, 150, 80))
    wave = [(cx + (R * 0.86 + S * 0.03 * math.sin(k * 0.9)) * math.cos(2 * math.pi * k / 40),
             cy + (R * 0.86 + S * 0.03 * math.sin(k * 0.9)) * math.sin(2 * math.pi * k / 40)) for k in range(40)]
    d.polygon(wave, fill=(255, 128, 180))
    h = S * 0.13
    d.ellipse([cx - h * 1.25, cy - h * 1.25, cx + h * 1.25, cy + h * 1.25], fill=(230, 100, 150))
    d.ellipse([cx - h, cy - h, cx + h, cy + h], fill=(0, 0, 0, 0))
    cols = [(255, 255, 255), (120, 210, 255), (255, 230, 80), (140, 230, 140)]
    for k in range(14):   # cốm
        a = 2 * math.pi * k / 14 + 0.3
        rr = S * (0.24 if k % 2 else 0.31)
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        d.line([(x, y), (x + S * 0.04 * math.cos(a * 3), y + S * 0.04 * math.sin(a * 3))], fill=cols[k % 4],
               width=int(S * 0.025))


def food_pizza(d, S):
    cx = S / 2
    top, tip = S * 0.14, S * 0.9
    tri = [(cx - S * 0.38, top), (cx + S * 0.38, top), (cx, tip)]
    d.polygon(tri, fill=(255, 208, 84))
    d.rounded_rectangle([cx - S * 0.43, top - S * 0.07, cx + S * 0.43, top + S * 0.07], radius=S * 0.07,
                        fill=(206, 140, 64))
    for x, y, r in ((0, 0.34, 0.075), (-0.14, 0.26, 0.06), (0.14, 0.27, 0.06), (0, 0.55, 0.055)):
        px, py, rr = cx + S * x, S * y, S * r
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(210, 50, 40))
        d.ellipse([px - rr * 0.5, py - rr * 0.6, px, py - rr * 0.1], fill=(240, 110, 90))
    d.line(tri[1:] + [tri[0]], fill=(220, 150, 40), width=int(S * 0.014))


# ---------- trái cây ----------
def fruit_dua_hau(d, S):
    cx, cy = S / 2, S * 0.36
    R = S * 0.44
    d.pieslice([cx - R, cy - R, cx + R, cy + R], 0, 180, fill=(46, 150, 60))
    d.pieslice([cx - R * 0.9, cy - R * 0.9, cx + R * 0.9, cy + R * 0.9], 0, 180, fill=(236, 248, 220))
    d.pieslice([cx - R * 0.82, cy - R * 0.82, cx + R * 0.82, cy + R * 0.82], 0, 180, fill=(240, 62, 72))
    for a, rr in ((40, 0.5), (75, 0.6), (110, 0.55), (140, 0.45), (90, 0.3), (60, 0.32), (120, 0.33)):
        x, y = cx + R * rr * math.cos(math.radians(a)), cy + R * rr * math.sin(math.radians(a))
        d.polygon(ellipse_pts(x, y, S * 0.018, S * 0.03, n=12, deg=a - 90), fill=(40, 20, 20))


def fruit_cam(d, S):
    cx, cy, R = S / 2, S * 0.54, S * 0.37
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(255, 146, 26))
    d.ellipse([cx - R * 0.9, cy - R * 0.92, cx + R * 0.8, cy + R * 0.8], fill=(255, 168, 50))
    for k in range(10):
        a = k * 2.4
        x, y = cx + R * 0.6 * math.cos(a), cy + R * 0.6 * math.sin(a)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(230, 120, 20))
    d.ellipse([cx - R * 0.55, cy - R * 0.6, cx - R * 0.15, cy - R * 0.3], fill=(255, 220, 160))
    d.polygon(ellipse_pts(cx + S * 0.1, cy - R - S * 0.02, S * 0.1, S * 0.045, deg=-25), fill=(70, 170, 60))
    d.line([(cx, cy - R + S * 0.03), (cx + S * 0.02, cy - R - S * 0.05)], fill=(110, 80, 40), width=int(S * 0.025))


def fruit_nho(d, S):
    cx = S / 2
    r = S * 0.1
    rows = [(0.34, 3), (0.5, 3), (0.65, 2), (0.79, 1)]
    for y, n in rows:
        for k in range(n):
            x = cx + (k - (n - 1) / 2) * r * 1.85
            yy = S * y
            d.ellipse([x - r, yy - r, x + r, yy + r], fill=(120, 50, 170))
            d.ellipse([x - r * 0.85, yy - r * 0.9, x + r * 0.7, yy + r * 0.7], fill=(160, 84, 210))
            d.ellipse([x - r * 0.55, yy - r * 0.6, x - r * 0.1, yy - r * 0.2], fill=(220, 190, 250))
    d.line([(cx, S * 0.23), (cx + S * 0.06, S * 0.1)], fill=(110, 80, 40), width=int(S * 0.03))
    d.polygon(ellipse_pts(cx - S * 0.1, S * 0.17, S * 0.11, S * 0.05, deg=-20), fill=(80, 170, 60))


def fruit_chuoi(d, S):
    cx, cy = S * 0.5, S * 0.2
    outer = [(cx + S * 0.42 * math.cos(math.radians(a)), cy + S * 0.62 * math.sin(math.radians(a)))
             for a in range(20, 161, 5)]
    inner = [(cx + S * 0.3 * math.cos(math.radians(a)), cy + S * 0.44 * math.sin(math.radians(a)))
             for a in range(160, 19, -5)]
    shape = outer + inner
    d.polygon(shape, fill=(255, 218, 54))
    hl = [(cx + S * 0.37 * math.cos(math.radians(a)), cy + S * 0.55 * math.sin(math.radians(a)))
          for a in range(40, 141, 5)]
    d.line(hl, fill=(255, 240, 150), width=int(S * 0.03))
    d.line(shape + [shape[0]], fill=(200, 150, 20), width=int(S * 0.016))
    for p in (outer[0], outer[-1]):
        d.ellipse([p[0] - S * 0.035, p[1] - S * 0.035, p[0] + S * 0.035, p[1] + S * 0.035], fill=(110, 80, 30))


def fruit_dau(d, S):
    cx, cy = S / 2, S * 0.5
    body = [(cx - S * 0.34, cy - S * 0.14), (cx + S * 0.34, cy - S * 0.14), (cx + S * 0.22, cy + S * 0.2),
            (cx, cy + S * 0.4), (cx - S * 0.22, cy + S * 0.2)]
    d.polygon(body, fill=(226, 32, 62))
    d.ellipse([cx - S * 0.36, cy - S * 0.3, cx + S * 0.36, cy + S * 0.14], fill=(226, 32, 62))
    d.ellipse([cx - S * 0.3, cy - S * 0.26, cx + S * 0.1, cy + S * 0.05], fill=(244, 70, 96))
    for k in range(12):   # hạt, nằm trong thân quả (hẹp dần về đáy)
        y = cy - S * 0.12 + S * 0.035 * k
        half = S * 0.26 * (1 - max(0.0, (y - cy) / (S * 0.42)))
        x = cx + half * 0.8 * math.sin(k * 1.7)
        d.ellipse([x - S * 0.013, y - S * 0.02, x + S * 0.013, y + S * 0.02], fill=(255, 230, 120))
    for a in (-60, -20, 20, 60):   # lá
        x, y = cx + S * 0.12 * math.sin(math.radians(a)), cy - S * 0.3
        d.polygon(ellipse_pts(x, y, S * 0.12, S * 0.045, deg=a), fill=(60, 160, 60))


def fruit_tao(d, S):
    cx, cy = S / 2, S * 0.56
    R = S * 0.3
    d.ellipse([cx - R * 1.2, cy - R, cx + R * 0.35, cy + R * 1.1], fill=(128, 196, 50))
    d.ellipse([cx - R * 0.35, cy - R, cx + R * 1.2, cy + R * 1.1], fill=(128, 196, 50))
    d.ellipse([cx - R * 1.05, cy - R * 0.85, cx + R * 0.4, cy + R * 0.7], fill=(160, 220, 80))
    d.ellipse([cx - R * 0.8, cy - R * 0.7, cx - R * 0.35, cy - R * 0.3], fill=(230, 250, 190))
    d.line([(cx, cy - R + S * 0.02), (cx + S * 0.03, cy - R - S * 0.12)], fill=(110, 80, 40), width=int(S * 0.03))
    d.polygon(ellipse_pts(cx + S * 0.13, cy - R - S * 0.08, S * 0.11, S * 0.05, deg=-30), fill=(60, 150, 50))


DRAWERS = {
    "do-an": [food_banh_mi, food_banh_bao, food_dui_ga, food_trung, food_donut, food_pizza],
    "trai-cay": [fruit_dua_hau, fruit_cam, fruit_nho, fruit_chuoi, fruit_dau, fruit_tao],
}


def item_sprite(set_key, idx, size):
    """Vẽ icon (trừ bộ kim cương — do gem_bot tự vẽ) kèm bóng đổ mềm."""
    ss = 3
    S = size * ss
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    DRAWERS[set_key][idx](ImageDraw.Draw(layer), S)
    alpha = layer.getchannel("A")
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * 0.45)).filter(ImageFilter.GaussianBlur(S * 0.02)))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, int(S * 0.035)))
    out.alpha_composite(layer)
    return out.resize((size, size), Image.LANCZOS)
