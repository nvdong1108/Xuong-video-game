#!/usr/bin/env python3
"""Vẽ Tranh TEE — tự vẽ lại một bức tranh (phác nét → tô mảng → tô chi tiết), xuất video dọc 1080x1920.

Video KHÔNG tiếng, không chữ: chỉ có nội dung vẽ, để ghép và lồng nhạc.

Cách chạy:
    python draw_bot.py --anh tranh.jpg                     # video dài tự nhiên (nhịp tay người) vào output/
    python draw_bot.py --anh tranh.jpg --chi-render 30     # chỉ xuất 30 giây đầu để duyệt nhịp
    python draw_bot.py --anh tranh.jpg --duration 180      # ép vừa 3 phút (vẽ nhanh hơn)
    python draw_bot.py --anh tranh.jpg --preview 5,40,100,170   # xem nhanh vài ảnh
    python draw_bot.py --anh tranh.jpg --cat 5,6           # cắt 5% trên, 6% dưới (bỏ watermark)
    python draw_bot.py --seed 3                            # không ghi --anh: lấy ảnh thứ (seed) trong
                                                           #   assets/ve-tranh/tranh/

Quy trình một video:
    1. Bút chì đi TỪNG NÉT một như tay người: đặt bút chậm, giữa nét nhanh, cuối nét chậm lại,
       nhấc bút sang nét sau, thỉnh thoảng dừng ngắm. Nét dài (dáng chính) trước, nét ngắn sau.
    2. Cọ tô từng vùng màu liền nhau (vùng rộng trước), vẫn giữ nét chì.
    3. Cọ quét lần hai để lộ dần màu và chi tiết thật của tranh, nét chì mờ đi.
    4. Giữ tranh hoàn chỉnh vài giây.

Nét và mảng màu được tách tự động từ ảnh. Tranh càng rõ viền, nền càng đơn giản
thì nét càng sạch.
"""
import argparse
import math
import random
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

# ============================================================================
# CONFIG — chỉnh ở đây
# ============================================================================
CONFIG = {
    "game_name": "VẼ TRANH TEE",
    "hook": "",               # để trống: video vẽ tranh không có chữ
    "question": "",
    "anh": "",                # đường dẫn ảnh; trống = ảnh thứ (seed) trong assets/ve-tranh/tranh/
    "cat": "0,0",             # cắt bỏ bao nhiêu % ở trên, dưới ảnh (ví dụ "5,6" để bỏ watermark)
    "duration": 0,            # giây; 0 = tự tính theo tốc độ tay người (tranh càng nhiều nét càng dài)
    "chi_render": 0,          # >0: chỉ xuất N giây đầu (để duyệt nhịp nhanh)
    "fps": 30,
    "width": 1080,
    "height": 1920,
    "seed": 7,                # đổi seed = đổi thứ tự vẽ, vệt cọ
    "pic_width": 960,         # bề ngang tranh trên màn hình (px)
    "intro": 2.0,             # giây đầu: bút đi vào
    "hold": 7.0,              # giây cuối: giữ tranh hoàn chỉnh
    "toc_do": 1.0,            # nhân tốc độ cả video: 1 = như người thật, 1.5 = nhanh hơn, 0.8 = chậm hơn
    "toc_do_but": 170,        # bút chì đi bao nhiêu điểm ảnh / giây (trên tranh rộng 960)
    "toc_do_co": 650,         # cọ quét bao nhiêu điểm ảnh / giây
    "net_dai": 45,            # nét dài hơn N điểm ảnh là "dáng chính", vẽ trước
    "so_mau": 10,             # số mảng màu ở bước tô mảng
    "net_nho_nhat": 20,       # bỏ nét vụn ít hơn N điểm ảnh
    "do_dam_net": 0.9,        # 0–1
    "audio": False,           # game này luôn không tiếng
    "crf": 20,
}

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"
PIC_DIR = ASSETS / "ve-tranh" / "tranh"
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

PAPER = np.array([246, 241, 230], np.float32)
INK = np.array([54, 48, 58], np.float32)
MARGIN = 38               # lề giấy quanh tranh
SOFT_LINE, SOFT_FLAT, SOFT_DET = 0.06, 0.28, 0.4


# ============================================================================
# Tiện ích
# ============================================================================
def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def noise_field(rng, h, w, cell, lo=-1.0, hi=1.0):
    """Nhiễu mượt (tần số thấp), giá trị trong [lo, hi]."""
    small = rng.random((h // cell + 2, w // cell + 2)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    a = np.asarray(img, np.float32) / 255
    a = (a - a.min()) / max(1e-6, a.max() - a.min())
    return lo + (hi - lo) * a


def pick_picture(cfg):
    if cfg.get("anh"):
        p = Path(cfg["anh"])
        if not p.is_file():
            sys.exit(f"Không thấy ảnh: {p}")
        return p
    pics = sorted(p for p in PIC_DIR.glob("*") if p.suffix.lower() in IMG_EXT) if PIC_DIR.exists() else []
    if not pics:
        sys.exit(f"Chưa có ảnh. Ghi --anh <file> hoặc thả ảnh vào {PIC_DIR}")
    return pics[cfg["seed"] % len(pics)]


def load_picture(cfg, path):
    img = Image.open(path).convert("RGB")
    top, bot = (float(x) for x in (str(cfg["cat"]).replace(";", ",").split(",") + ["0"])[:2])
    y0, y1 = int(img.height * top / 100), int(img.height * (1 - bot / 100))
    img = img.crop((0, y0, img.width, max(y0 + 10, y1)))
    w = cfg["pic_width"]
    h = int(round(img.height * w / img.width))
    max_h = cfg["height"] - 2 * MARGIN - 260
    if h > max_h:
        h, w = max_h, int(round(img.width * max_h / img.height))
    return img.resize((w, h), Image.LANCZOS)


def lineart(gray):
    """XDoG: tách nét kiểu bút chì / bút mực từ ảnh màu. Trả về độ đậm 0..1."""
    g1 = ndi.gaussian_filter(gray, 1.0)
    g2 = ndi.gaussian_filter(gray, 1.6)
    d = g1 - 0.98 * g2
    e = np.where(d >= 0.0, 1.0, 1 + np.tanh(60 * d))
    line = np.clip(((1 - np.clip(e, 0, 1)) - 0.15) / 0.6, 0, 1)
    lab, n = ndi.label(line > 0.3)
    sizes = ndi.sum(np.ones_like(line), lab, range(1, n + 1))
    keep = np.isin(lab, np.nonzero(sizes >= 25)[0] + 1)
    return (line * ndi.binary_dilation(keep, iterations=1)).astype(np.float32)


def thin(mask):
    """Làm mảnh nét còn 1 điểm ảnh (Zhang-Suen) để lấy 'xương' của nét."""
    img = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            c = img[1:-1, 1:-1]
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9 = img[1:-1, :-2], img[:-2, :-2]
            B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                m = ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
            else:
                m = ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
            rem = (c == 1) & (B >= 2) & (B <= 6) & (A == 1) & m
            if rem.any():
                c[rem] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def trace_strokes(skel):
    """Chia xương nét thành các nét bút liền (danh sách mảng toạ độ theo thứ tự đi bút)."""
    h, w = skel.shape
    Wp = w + 2
    g = np.zeros((h + 2, Wp), np.uint8)
    g[1:-1, 1:-1] = skel
    deg = sum(np.roll(np.roll(g, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
              if dy or dx) * g
    flat = g.ravel()
    grid = bytearray(flat.tobytes())
    nbs = (-Wp, 1, Wp, -1, -Wp - 1, -Wp + 1, Wp - 1, Wp + 1)   # ưu tiên 4 hướng rồi mới chéo

    def walk(p):
        out = []
        while True:
            for o in nbs:
                q = p + o
                if grid[q]:
                    grid[q] = 0
                    out.append(q)
                    p = q
                    break
            else:
                return out

    pix = np.flatnonzero(flat)
    dflat = deg.ravel()[pix]
    starts = np.concatenate([pix[dflat == 1], pix[dflat != 1]])   # đầu mút trước
    strokes = []
    for s in starts:
        s = int(s)
        if not grid[s]:
            continue
        grid[s] = 0
        fwd = walk(s)
        back = walk(s)
        path = back[::-1] + [s] + fwd
        if len(path) >= 3:
            a = np.array(path)
            strokes.append(np.stack([a % Wp - 1, a // Wp - 1], 1).astype(np.float32))   # (x, y)
    return strokes


def human_progress(n=64):
    """Tiến độ theo thời gian của một nét: đặt bút chậm, giữa nhanh, cuối chậm lại."""
    tau = np.linspace(0, 1, n)
    return tau, 0.25 * tau + 0.75 * (3 * tau ** 2 - 2 * tau ** 3)


# ============================================================================
# Mô phỏng: tính trước thời điểm mỗi điểm ảnh được vẽ + đường đi của bút / cọ
# ============================================================================
class DrawGame:
    def __init__(self, cfg):
        self.cfg = cfg
        self.fps = cfg["fps"]
        self.rng = random.Random(cfg["seed"])
        self.nrng = np.random.default_rng(cfg["seed"])
        self.path = pick_picture(cfg)
        self.pic = load_picture(cfg, self.path)
        self.w, self.h = self.pic.size
        self.stats = {}

    # ---------- giấy ----------
    def build_paper(self):
        sh, sw = self.h + 2 * MARGIN, self.w + 2 * MARGIN
        grain = self.nrng.normal(0, 3.2, (sh, sw, 1)).astype(np.float32)
        blot = noise_field(self.nrng, sh, sw, 60, -3, 3)[..., None]
        yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
        vig = (((xx / sw - 0.5) ** 2 + (yy / sh - 0.5) ** 2) * -16)[..., None]
        self.sheet = np.clip(PAPER + grain + blot + vig, 0, 255).astype(np.float32)
        self.P = self.sheet[MARGIN:MARGIN + self.h, MARGIN:MARGIN + self.w].reshape(-1, 3).copy()

    # ---------- bước 1: nét (thời gian tính từ 0, chưa co giãn) ----------
    def build_sketch(self):
        c = self.cfg
        w, h = self.w, self.h
        arr = np.asarray(self.pic, np.float32) / 255
        line = lineart(arr @ np.array([0.299, 0.587, 0.114], np.float32))
        mask = line > 0.08
        lab, n = ndi.label(mask, structure=np.ones((3, 3)))
        small = np.bincount(lab.ravel(), minlength=n + 1) < c["net_nho_nhat"]
        small[0] = True
        mask &= ~small[lab]
        line *= mask
        strokes = trace_strokes(thin(line > 0.25))
        lens = [float(np.hypot(*np.diff(s, axis=0).T).sum()) for s in strokes]

        # thứ tự: nét dài (dáng chính) trước, nét ngắn (chi tiết) sau; trong mỗi nhóm đi tới nét gần nhất
        n = len(strokes)
        heads = np.array([s[0] for s in strokes]); tails = np.array([s[-1] for s in strokes])
        long_ = np.array(lens) >= c["net_dai"]
        left = np.ones(n, bool)
        pen = np.array([w * 0.5, h * 0.3])
        tau, prog = human_progress()
        V = c["toc_do_but"]
        skel_T = np.full(w * h, np.inf, np.float32)
        tr_t, tr_x, tr_y, iv0, iv1 = [], [], [], [], []
        t = 0.0
        next_look = self.rng.randint(25, 45)
        for i in range(n):
            pool = left & long_ if (left & long_).any() else left
            dh = np.hypot(*(heads - pen).T); dt_ = np.hypot(*(tails - pen).T)
            d = np.minimum(dh, dt_) + self.nrng.random(n) * 12
            d[~pool] = np.inf
            k = int(np.argmin(d))
            left[k] = False
            s = strokes[k] if dh[k] <= dt_[k] else strokes[k][::-1]
            # nhấc bút, di chuyển tới đầu nét
            gap = float(np.hypot(*(s[0] - pen)))
            t += 0.05 + gap / 1400 + (self.rng.uniform(0.04, 0.14) if gap > 40 else 0)
            if i + 1 >= next_look:            # thỉnh thoảng dừng lại ngắm tranh
                t += self.rng.uniform(0.6, 1.2)
                next_look = i + 1 + self.rng.randint(25, 45)
            L = max(1.0, lens[k])
            v = V * self.rng.uniform(0.8, 1.2) * (1 + min(0.6, L / 500))   # nét dài đi nhanh tay hơn
            dur = L / v + 0.08
            seg = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(s, axis=0).T))]) / L
            ts = t + np.interp(seg, prog, tau) * dur
            xi, yi = s[:, 0].astype(int), s[:, 1].astype(int)
            skel_T[yi * w + xi] = ts
            step = max(1, len(s) // max(2, int(L / 3)))
            tr_t += list(ts[::step]) + [ts[-1]]
            tr_x += list(s[::step, 0]) + [s[-1, 0]]
            tr_y += list(s[::step, 1]) + [s[-1, 1]]
            iv0.append(t); iv1.append(t + dur)
            t += dur
            pen = s[-1]

        # mỗi điểm của nét dày lấy thời điểm của điểm xương gần nhất
        skel = np.isfinite(skel_T).reshape(h, w)
        dist, (iy, ix) = ndi.distance_transform_edt(~skel, return_indices=True)
        T = skel_T[(iy * w + ix).ravel()]
        near = (dist.ravel() <= 5) & (line.ravel() > 0)
        T[~near] = np.inf
        self.line = np.where(near, line.ravel(), 0).astype(np.float32)
        self.stats["net"] = n
        return {"T": T, "t": np.array(tr_t), "x": np.array(tr_x), "y": np.array(tr_y),
                "iv0": np.array(iv0), "iv1": np.array(iv1), "dur": t + 0.2}

    # ---------- chia vùng màu (dùng cho bước 2 và 3) ----------
    def build_regions(self):
        w, h = self.w, self.h
        k = self.cfg["so_mau"]
        small = self.pic.resize((max(1, w // 3), max(1, h // 3))).filter(ImageFilter.MedianFilter(5))
        q = small.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
        pal = np.array(q.getpalette()[:3 * 256], np.float32).reshape(-1, 3)
        lab_small = Image.fromarray(np.asarray(q)).filter(ImageFilter.ModeFilter(5))
        labels = np.asarray(lab_small.resize((w, h), Image.NEAREST))
        flat_img = Image.fromarray(pal[labels].astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
        self.F = np.asarray(flat_img, np.float32).reshape(-1, 3) * 0.88 + self.P * 0.12
        min_area = w * h * 0.002
        rid = np.zeros((h, w), np.int32)       # số vùng lớn của từng điểm ảnh (0 = mảng vụn)
        cols = [None]
        for u in np.unique(labels):
            cl, nc = ndi.label(labels == u)
            sizes = np.bincount(cl.ravel(), minlength=nc + 1)
            for j in np.nonzero(sizes >= min_area)[0]:
                if j == 0:
                    continue
                cols.append(tuple(int(v) for v in pal[u]))
                rid[cl == j] = len(cols) - 1
        # mảng vụn tô chung với vùng lớn nằm sát nó (khỏi quét cả bề ngang tranh cho vài điểm màu)
        _, (iy, ix) = ndi.distance_transform_edt(rid == 0, return_indices=True)
        rid = rid[iy, ix]
        area = np.bincount(rid.ravel())
        order = np.argsort(rid.ravel(), kind="stable")
        cuts = np.flatnonzero(np.diff(rid.ravel()[order])) + 1
        regions = []
        for grp in np.split(order, cuts):
            r = int(rid.ravel()[grp[0]])
            regions.append((area[r], grp // w, grp % w, cols[r]))
        regions.sort(key=lambda r: -r[0])      # vùng rộng tô trước
        self.stats["mau"] = len(np.unique(labels))
        self.stats["vung"] = len(regions)
        return [(ys, xs, col) for _, ys, xs, col in regions]

    # ---------- cọ quét zig-zag từng dải trong từng vùng ----------
    def sweep(self, regions, bh, speed):
        w, h = self.w, self.h
        T = np.full(w * h, np.inf, np.float32)
        tt, tx, ty, layer_t, colors = [], [], [], [], []
        t, pos, fwd = 0.0, None, True
        for yy, xx, col in regions:
            band = yy // bh
            order = np.argsort(band, kind="stable")
            yy, xx, band = yy[order], xx[order], band[order]
            cuts = np.flatnonzero(np.diff(band)) + 1
            first = True
            for ys, xs, b in zip(np.split(yy, cuts), np.split(xx, cuts), np.split(band, cuts)):
                xa, xb = int(xs.min()) - 8, int(xs.max()) + 8
                yc = (int(b[0]) + 0.5) * bh
                x0, x1 = (xa, xb) if fwd else (xb, xa)
                if pos is not None:
                    d = math.hypot(x0 - pos[0], yc - pos[1])
                    t += (0.35 + d / 1200) if first else d / (speed * 1.5)   # sang vùng mới: chấm màu
                if first:
                    layer_t.append(t); colors.append(col)
                    first = False
                span = (xb - xa) / speed
                along = (xs - xa) if fwd else (xb - xs)
                T[ys * w + xs] = t + along / speed
                tt += [t, t + span]; tx += [x0, x1]; ty += [yc, yc]
                t += span
                pos = (x1, yc)
                fwd = not fwd
        return {"T": T, "t": np.array(tt), "x": np.array(tx, float), "y": np.array(ty, float),
                "layer_t": np.array(layer_t), "colors": colors, "dur": t + 0.2, "bh": bh}

    def place_sweep(self, sw, t0, k, noise_amp):
        """Đặt một lượt quét vào dòng thời gian thật; thêm mép vệt cọ không thẳng."""
        h, w = self.h, self.w
        T = t0 + sw["T"] * k
        bh = sw["bh"]
        off = np.abs((np.repeat(np.arange(h), w) % bh) - bh / 2) / (bh / 2)
        T = np.maximum(T + noise_field(self.nrng, h, w, 40, 0, noise_amp).ravel() + off * 0.18, t0)
        return T.astype(np.float32), t0 + sw["t"] * k, sw["x"], sw["y"], t0 + sw["layer_t"] * k

    # ---------- dòng thời gian ----------
    def place(self, sk, fl, dt):
        c = self.cfg
        g1, g2 = 1.6, 1.2
        nat = sk["dur"] + fl["dur"] + dt["dur"]
        if c["duration"] and c["duration"] > 0:          # ép vừa độ dài cho trước
            usable = c["duration"] - c["intro"] - g1 - g2 - c["hold"]
            if usable < 10:
                sys.exit("duration quá ngắn (cần ít nhất ~25 giây).")
            k = usable / nat
        else:                                            # tự nhiên như tay người
            k = 1 / max(0.1, c["toc_do"])
        self.t_s0 = c["intro"]
        self.t_s1 = self.t_s0 + sk["dur"] * k
        self.t_f0 = self.t_s1 + g1
        self.t_f1 = self.t_f0 + fl["dur"] * k
        self.t_d0 = self.t_f1 + g2
        self.t_d1 = self.t_d0 + dt["dur"] * k
        self.duration = self.t_d1 + c["hold"]
        self.total = int(round(self.duration * self.fps))
        if c.get("chi_render"):
            self.total = min(self.total, int(c["chi_render"] * self.fps))

        self.T_line = self.t_s0 + sk["T"] * k
        self.sk_t, self.sk_x, self.sk_y = self.t_s0 + sk["t"] * k, sk["x"], sk["y"]
        self.sk_iv0, self.sk_iv1 = self.t_s0 + sk["iv0"] * k, self.t_s0 + sk["iv1"] * k
        self.T_flat, self.fl_t, self.fl_x, self.fl_y, self.fl_layer_t = self.place_sweep(fl, self.t_f0, k, 0.3)
        self.fl_color = fl["colors"]
        self.T_det, self.dt_t, self.dt_x, self.dt_y, _ = self.place_sweep(dt, self.t_d0, k, 0.4)
        self.stats["giay"] = self.duration
        self.stats["giay_net"] = self.t_s1 - self.t_s0

    # ---------- đường đi dụng cụ theo từng khung ----------
    def build_cursor(self):
        off = (self.w + 280.0, self.h * 0.9)
        n = self.total
        tool = np.zeros(n, np.int8)       # 0 không có, 1 bút chì, 2 cọ
        X, Y, LIFT = np.zeros(n), np.zeros(n), np.ones(n)
        COL = np.zeros((n, 3))
        sk0 = (self.sk_x[0], self.sk_y[0]); sk1 = (self.sk_x[-1], self.sk_y[-1])
        fl0 = (self.fl_x[0], self.fl_y[0]); fl1 = (self.fl_x[-1], self.fl_y[-1])
        dt0 = (self.dt_x[0], self.dt_y[0]); dt1 = (self.dt_x[-1], self.dt_y[-1])
        g1m = (self.t_s1 + self.t_f0) / 2
        lerp = lambda a, b, k: (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
        img = self.O.reshape(self.h, self.w, 3)
        for f in range(n):
            t = f / self.fps
            lift = 1.0
            col = (0, 0, 0)
            if t < self.t_s0:
                tl, p = 1, lerp(off, sk0, ease_out(clamp01(t / self.t_s0)))
            elif t < self.t_s1:
                tl = 1
                p = (np.interp(t, self.sk_t, self.sk_x), np.interp(t, self.sk_t, self.sk_y))
                i = np.searchsorted(self.sk_iv0, t, "right") - 1
                lift = 0.0 if i >= 0 and t <= self.sk_iv1[i] else 1.0
            elif t < g1m:
                tl, p = 1, lerp(sk1, off, ease_in_out(clamp01((t - self.t_s1) / (g1m - self.t_s1))))
            elif t < self.t_f0:
                tl, p = 2, lerp(off, fl0, ease_out(clamp01((t - g1m) / (self.t_f0 - g1m))))
                col = self.fl_color[0]
            elif t < self.t_f1:
                tl = 2
                p = (np.interp(t, self.fl_t, self.fl_x), np.interp(t, self.fl_t, self.fl_y))
                li = max(0, np.searchsorted(self.fl_layer_t, t, "right") - 1)
                col = self.fl_color[min(li, len(self.fl_color) - 1)]
                lift = 0.0
            elif t < self.t_d0:
                tl, p = 2, lerp(fl1, dt0, ease_in_out(clamp01((t - self.t_f1) / (self.t_d0 - self.t_f1))))
                col = self.fl_color[-1]
            elif t < self.t_d1:
                tl = 2
                p = (np.interp(t, self.dt_t, self.dt_x), np.interp(t, self.dt_t, self.dt_y))
                lift = 0.0
            elif t < self.t_d1 + 1.6:
                tl, p = 2, lerp(dt1, off, ease_in_out(clamp01((t - self.t_d1) / 1.6)))
            else:
                tl, p = 0, off
            if tl == 2 and self.t_d0 <= t < self.t_d1 + 1.6:
                xi = int(min(self.w - 1, max(0, p[0]))); yi = int(min(self.h - 1, max(0, p[1])))
                col = tuple(img[yi, xi])
            tool[f], X[f], Y[f], LIFT[f], COL[f] = tl, p[0], p[1], lift, col
        # làm mượt: tay người không giật cục
        sx, sy, sl, sc = X[0], Y[0], LIFT[0], COL[0].copy()
        for f in range(n):
            if f and tool[f] != tool[f - 1]:
                sx, sy = X[f], Y[f]
            sx += (X[f] - sx) * 0.55
            sy += (Y[f] - sy) * 0.55
            sl += (LIFT[f] - sl) * 0.35
            sc += (COL[f] - sc) * 0.2
            X[f], Y[f], LIFT[f], COL[f] = sx, sy, sl, sc
        self.cur_tool, self.cur_x, self.cur_y, self.cur_lift, self.cur_col = tool, X, Y, LIFT, COL

    def play(self):
        self.build_paper()
        self.O = np.asarray(self.pic, np.float32).reshape(-1, 3)
        sk = self.build_sketch()
        regions = self.build_regions()
        fl = self.sweep(regions, 44, self.cfg["toc_do_co"])
        dt = self.sweep(regions, 32, self.cfg["toc_do_co"] * 1.1)
        self.place(sk, fl, dt)
        self.build_cursor()
        # chỉ số sắp theo T để vẽ tăng dần (mỗi khung chỉ tính lại vùng vừa đổi)
        self.sorted_layers = []
        for T, soft in ((self.T_line, SOFT_LINE), (self.T_flat, SOFT_FLAT), (self.T_det, SOFT_DET)):
            idx = np.flatnonzero(np.isfinite(T))
            idx = idx[np.argsort(T[idx], kind="stable")]
            self.sorted_layers.append((idx, T[idx], soft))
        return self


# ============================================================================
# Vẽ khung hình
# ============================================================================
def build_polys(kind):
    """Hình bút chì / cọ vẽ bằng đa giác. Trục s chạy từ đầu ngòi lên phía đuôi."""
    a = math.radians(38)
    ux, uy = math.cos(a), -math.sin(a)
    nx, ny = math.sin(a), math.cos(a)
    P = lambda s, o: (s * ux + o * nx, s * uy + o * ny)
    quad = lambda s0, s1, o0, o1: [P(s0, o0), P(s1, o0), P(s1, o1), P(s0, o1)]
    polys = []           # (điểm, màu, là đầu cọ?)
    if kind == "pencil":
        polys.append(([P(16, 5), P(62, 15), P(62, -15), P(16, -5)], (232, 194, 148), False))
        polys.append(([P(0, 0), P(17, 5.5), P(17, -5.5)], (58, 56, 64), False))
        polys.append((quad(62, 360, -15, -5), (222, 150, 28), False))
        polys.append((quad(62, 360, -5, 5), (248, 186, 46), False))
        polys.append((quad(62, 360, 5, 15), (255, 214, 96), False))
        polys.append((quad(360, 394, -15.5, 15.5), (192, 192, 204), False))
        for s in (368, 378, 388):
            polys.append((quad(s, s + 3, -15.5, 15.5), (150, 150, 164), False))
        polys.append(([P(394, 15)] + [P(420 + 10 * math.sin(k / 20 * math.pi), 15 * math.cos(k / 20 * math.pi))
                                      for k in range(21)] + [P(394, -15)], (238, 128, 138), False))
    else:
        tip = [(0, 0), (10, 6), (30, 12), (50, 14), (72, 12)]
        polys.append(([P(s, o) for s, o in tip] + [P(s, -o) for s, o in reversed(tip)], (255, 255, 255), True))
        polys.append(([P(72, 12), P(112, 10), P(112, -10), P(72, -12)], (196, 198, 210), False))
        polys.append(([P(72, 4), P(112, 3), P(112, -1), P(72, -1)], (236, 238, 246), False))
        polys.append(([P(112, 9), P(420, 7), P(420, -7), P(112, -9)], (156, 36, 40), False))
        polys.append(([P(112, 4), P(420, 3), P(420, 1), P(112, 1)], (206, 90, 90), False))
        polys.append(([P(420, 7), P(432, 4), P(432, -4), P(420, -7)], (40, 30, 30), False))
    return polys


def make_tool(kind, ss=2, pad=30):
    polys = build_polys(kind)
    pts = [p for poly, _, _ in polys for p in poly]
    mnx, mny = min(p[0] for p in pts), min(p[1] for p in pts)
    mxx, mxy = max(p[0] for p in pts), max(p[1] for p in pts)
    W, H = int(mxx - mnx + 2 * pad), int(mxy - mny + 2 * pad)
    body = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    tipm = Image.new("L", (W * ss, H * ss), 0)
    db, dt = ImageDraw.Draw(body), ImageDraw.Draw(tipm)
    tr = lambda p: ((p[0] - mnx + pad) * ss, (p[1] - mny + pad) * ss)
    for poly, col, is_tip in polys:
        q = [tr(p) for p in poly]
        if is_tip:
            dt.polygon(q, fill=255)
        else:
            db.polygon(q, fill=col + (255,))
    body = body.resize((W, H), Image.LANCZOS)
    tipm = tipm.resize((W, H), Image.LANCZOS)
    a = np.asarray(body, np.float32) / 255
    tip_a = np.asarray(tipm, np.float32)[..., None] / 255
    alpha = np.maximum(a[..., 3:], tip_a)
    shadow = np.asarray(Image.fromarray((alpha[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(7)),
                        np.float32)[..., None] / 255 * 0.32
    return {"body": a, "tip": tip_a, "shadow": shadow, "anchor": (pad - mnx, pad - mny)}


def blit(dst, rgb, alpha, x, y):
    """Dán ảnh (rgb float 0..1 hoặc màu cố định) có alpha lên dst uint8 tại góc (x, y)."""
    H, W = dst.shape[:2]
    h, w = alpha.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    a = alpha[y0 - y:y1 - y, x0 - x:x1 - x]
    src = rgb[y0 - y:y1 - y, x0 - x:x1 - x] * 255 if isinstance(rgb, np.ndarray) and rgb.ndim == 3 else \
        np.asarray(rgb, np.float32)
    reg = dst[y0:y1, x0:x1].astype(np.float32)
    dst[y0:y1, x0:x1] = (reg * (1 - a) + src * a).astype(np.uint8)


class Renderer:
    def __init__(self, game, cfg):
        self.g, self.cfg = game, cfg
        self.W, self.H = cfg["width"], cfg["height"]
        g = game
        self.x0 = (self.W - g.w) // 2
        self.y0 = (self.H - g.h) // 2
        self.bg = self.build_background()
        self.tapes = self.build_tapes()
        self.tools = {1: make_tool("pencil"), 2: make_tool("brush")}
        self.canvas = None
        self.last_t = None

    def build_background(self):
        W, H, g = self.W, self.H, self.g
        rng = np.random.default_rng(11)
        t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        base = np.array([66, 51, 42], np.float32) * (1 - t) + np.array([44, 34, 29], np.float32) * t
        # thớ gỗ: vân ngang chạy dài, uốn nhẹ
        small = rng.random((H // 60 + 2, W // 300 + 2)).astype(np.float32)
        warp = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC),
                          np.float32) / 255 * 2.2
        yy = np.arange(H, dtype=np.float32)[:, None]
        grain = (np.sin(yy * 0.23 + warp * 3) * 2.2 + np.sin(yy * 0.047 + warp) * 3.5)[..., None]
        grain = grain + rng.normal(0, 1, (H, 1, 1)).repeat(W, 1) * 1.5
        img = np.clip(base + grain + rng.normal(0, 2.0, (H, W, 1)), 0, 255)
        sx0, sy0 = self.x0 - MARGIN, self.y0 - MARGIN
        sh, sw = g.sheet.shape[:2]
        sm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sm).rectangle([sx0 + 6, sy0 + 18, sx0 + sw + 6, sy0 + sh + 18], fill=255)
        sm = np.asarray(sm.filter(ImageFilter.GaussianBlur(20)), np.float32)[..., None] / 255
        img = img * (1 - sm * 0.6)
        img[sy0:sy0 + sh, sx0:sx0 + sw] = g.sheet
        return img.astype(np.uint8)

    def build_tapes(self):
        out = []
        sx0, sy0 = self.x0 - MARGIN, self.y0 - MARGIN
        sw = self.g.w + 2 * MARGIN
        for cx, ang in ((sx0 + 34, 38), (sx0 + sw - 34, -38)):
            im = Image.new("RGBA", (260, 80), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            teeth = [(k * 13, 0 if k % 2 else 5) for k in range(21)]
            poly = [(0, 12)] + [(x, 12 + y) for x, y in teeth] + [(260, 12)] + \
                   [(260, 68)] + [(260 - x, 68 - y) for x, y in teeth] + [(0, 68)]
            d.polygon(poly, fill=(232, 212, 172, 150))
            im = im.rotate(ang, expand=True, resample=Image.BICUBIC)
            a = np.asarray(im, np.float32) / 255
            out.append((a[..., :3], a[..., 3:], cx - im.width / 2, sy0 + 6 - im.height / 2))
        return out

    # ---------- tranh trên giấy ----------
    def compose(self, idx, t):
        g = self.g
        P = g.P[idx]
        af = np.clip((t - g.T_flat[idx]) / SOFT_FLAT, 0, 1)[:, None]
        base = P + (g.F[idx] - P) * af
        ad = np.clip((t - g.T_det[idx]) / SOFT_DET, 0, 1)[:, None]
        base += (g.O[idx] - base) * ad
        al = np.clip((t - g.T_line[idx]) / SOFT_LINE, 0, 1) * g.line[idx] * (1 - 0.92 * ad[:, 0])
        al = (al * self.cfg["do_dam_net"])[:, None]
        return np.clip(base * (1 - al) + INK * al, 0, 255).astype(np.uint8)

    def update_canvas(self, frame):
        g = self.g
        t = frame / g.fps
        if self.canvas is None or self.last_t is None or t < self.last_t:
            self.canvas = self.compose(np.arange(g.w * g.h), t)
        else:
            parts = []
            for idx, Ts, soft in g.sorted_layers:
                a = np.searchsorted(Ts, self.last_t - soft, "left")
                b = np.searchsorted(Ts, t, "right")
                if b > a:
                    parts.append(idx[a:b])
            if parts:
                ch = np.concatenate(parts)
                self.canvas[ch] = self.compose(ch, t)
        self.last_t = t

    def render(self, frame):
        g = self.g
        self.update_canvas(frame)
        img = self.bg.copy()
        img[self.y0:self.y0 + g.h, self.x0:self.x0 + g.w] = self.canvas.reshape(g.h, g.w, 3)
        for rgb, a, x, y in self.tapes:
            blit(img, rgb, a, x, y)
        tl = int(g.cur_tool[frame])
        if tl:
            spr = self.tools[tl]
            lift = float(g.cur_lift[frame])
            wob = math.sin(frame * 0.9) * 1.2 * (1 - lift)
            ax, ay = spr["anchor"]
            x = self.x0 + g.cur_x[frame] - ax + wob
            y = self.y0 + g.cur_y[frame] - ay - lift * 16
            blit(img, (0, 0, 0), spr["shadow"], x + 12 + lift * 26, y + 14 + lift * 34)
            blit(img, spr["body"][..., :3], spr["body"][..., 3:], x, y)
            if tl == 2:
                blit(img, tuple(g.cur_col[frame]), spr["tip"], x, y)
        return Image.fromarray(img)


# ============================================================================
# Xuất video / ảnh xem thử
# ============================================================================
def export_video(game, renderer, cfg, out_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("Không tìm thấy ffmpeg. Cài ffmpeg và thêm vào PATH (kiểm tra: ffmpeg -version).")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cfg['width']}x{cfg['height']}",
           "-r", str(cfg["fps"]), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(cfg["crf"]), "-pix_fmt", "yuv420p",
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
    ap = argparse.ArgumentParser(description="Vẽ Tranh TEE — tự vẽ lại tranh, xuất video dọc không tiếng")
    ap.add_argument("--anh", help="ảnh nguồn (jpg/png)")
    ap.add_argument("--cat", help="cắt %% trên,dưới ảnh, ví dụ 5,6")
    ap.add_argument("--seed", type=int, help="đổi thứ tự vẽ / vệt cọ; không có --anh thì chọn ảnh theo seed")
    ap.add_argument("--out", help="tên file video; chỉ có tên file thì lưu vào output/")
    ap.add_argument("--preview", help="xuất ảnh ở các giây này, ví dụ 5,40,100,170")
    ap.add_argument("--hook", help="(không dùng, để tương thích giao diện)")
    ap.add_argument("--question", help="(không dùng, để tương thích giao diện)")
    ap.add_argument("--duration", type=float, help="độ dài video (giây)")
    ap.add_argument("--chi-render", type=float, help="chỉ xuất N giây đầu, ví dụ 30 (để duyệt nhịp)")
    ap.add_argument("--set", action="append", default=[], metavar="KHÓA=GIÁ_TRỊ",
                    help="đổi bất kỳ tham số CONFIG, ví dụ --set so_mau=12")
    args = ap.parse_args()

    cfg = dict(CONFIG)
    for key in ("anh", "cat", "seed", "hook", "question", "duration", "chi_render"):
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
    game = DrawGame(cfg).play()
    renderer = Renderer(game, cfg)
    st = game.stats
    m, s_ = divmod(int(round(st["giay"])), 60)
    print(f"Ván số {cfg['seed']}: tranh {game.path.name} · {st['net']} nét · {st['vung']} vùng màu · "
          f"dài {m}:{s_:02d} (phác nét {st['giay_net'] / 60:.1f} phút)")
    print(f"  Chuẩn bị xong sau {time.time() - t0:.1f}s")
    if cfg.get("chi_render"):
        print(f"  Chỉ xuất {game.total / game.fps:g} giây đầu")

    stem = f"ve-tranh_{game.path.stem}_seed{cfg['seed']}"
    if args.preview:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for sec in [float(s) for s in args.preview.split(",") if s.strip()]:
            f = min(game.total - 1, int(sec * cfg["fps"]))
            p = OUTPUT / f"{stem}_{sec:g}s.png"
            renderer.render(f).save(p)
            print(f"  Đã lưu {p}")
        return

    out = resolve_out(args.out, f"{stem}.mp4")
    export_video(game, renderer, cfg, out)
    print(f"Xong: {out}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
