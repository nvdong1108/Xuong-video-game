#!/usr/bin/env python3
"""Xương - video - game · giao diện quản lý chạy trên máy (local).

Chạy:
    python app.py              # mở http://127.0.0.1:8765 trong trình duyệt
    python app.py --port 9000 --workers 3 --no-browser

Chỉ dùng thư viện chuẩn của Python (+ pillow/numpy mà các bot đã cần).
"""
import argparse
import base64
import csv
import importlib.util
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
PREVIEW_DIR = OUTPUT / "_preview"
TEMPLATE_DIR = OUTPUT / "_templates"
UI_FILE = ROOT / "ui" / "index.html"
HOOKS_FILE = ROOT / "data" / "hooks.txt"
STATS_FILE = ROOT / "data" / "so-lieu.csv"

GAMES = {
    "kim-cuong": {"name": "Kim Cương TEE", "script": ROOT / "kim-cuong" / "gem_bot.py", "cls": "GemGame"},
    "nong-trai": {"name": "Nông Trại Của TEE", "script": ROOT / "nong-trai" / "farm_bot.py", "cls": "FarmGame"},
    "ve-tranh": {"name": "Vẽ Tranh TEE", "script": ROOT / "ve-tranh" / "draw_bot.py", "cls": "DrawGame"},
}
TRANH_DIR = ROOT / "assets" / "ve-tranh" / "tranh"      # ảnh nguồn cho game vẽ tranh
TRANH_EXT = (".jpg", ".jpeg", ".png", ".webp")
VE_TRANH_CAI_DAT = ROOT / "data" / "ve-tranh.json"   # thư mục thêm để dò ảnh đã vẽ
TEN_TRANH = re.compile(r'^[^\\/:*?"<>|]+\.(jpe?g|png|webp)$', re.I)
MAX_SCAN = 100
# Tham số nhịp chơi chỉnh được từ giao diện (chỉ áp dụng nếu game có khóa đó trong CONFIG)
TUNE_KEYS = ("think_min", "think_max", "touch_time", "swipe_time", "skill", "decoy_chance", "rain_every")


# ============================================================================
# Nạp module game (tự nạp lại khi file bot được sửa)
# ============================================================================
_modules = {}
_render_lock = threading.Lock()


def game_module(key):
    script = GAMES[key]["script"]
    # nạp lại khi file bot hoặc file phụ cùng thư mục (vd gem_templates.py) được sửa
    mtime = max(p.stat().st_mtime for p in script.parent.glob("*.py"))
    cached = _modules.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    for name, m in list(sys.modules.items()):
        f = getattr(m, "__file__", None)
        if f and Path(f).resolve().parent == script.parent.resolve():
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location(f"bot_{key.replace('-', '_')}", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _modules[key] = (mtime, mod)
    return mod


def build_cfg(mod, params):
    cfg = dict(mod.CONFIG)
    if params.get("seed") not in (None, ""):
        cfg["seed"] = int(params["seed"])
    for k in ("hook", "question"):
        if params.get(k):
            cfg[k] = params[k]
    if params.get("duration"):
        cfg["duration"] = float(params["duration"])
    if params.get("speed") and "speed" in cfg:
        cfg["speed"] = float(params["speed"])
    for k, v in clean_tune(cfg, params.get("tune")).items():
        cfg[k] = v
    for k, v in clean_board(cfg, params).items():
        cfg[k] = v
    for k, v in clean_template(mod, params).items():
        cfg[k] = v
    for k, v in clean_art(cfg, params).items():
        cfg[k] = v
    return cfg


def tranh_path(name):
    """Ảnh trong thư mục tranh — chỉ nhận TÊN FILE trần."""
    name = str(name or "").strip()
    if not TEN_TRANH.match(name) or name.startswith("."):
        raise ValueError("Tên ảnh không hợp lệ")
    p = TRANH_DIR / name
    if not p.is_file():
        raise ValueError(f"Không thấy ảnh {name} trong {TRANH_DIR}")
    return p


def clean_art(cfg, params):
    """Tham số riêng game vẽ tranh (chỉ game có khóa `anh`)."""
    out = {}
    if "anh" not in cfg:
        return out
    if params.get("anh"):
        out["anh"] = str(tranh_path(params["anh"]))
    cat = re.findall(r"\d+(?:\.\d+)?", str(params.get("cat") or ""))
    if cat:
        top, bot = (min(30.0, float(x)) for x in (cat + ["0"])[:2])
        out["cat"] = f"{top:g},{bot:g}"
    if params.get("toc_do") not in (None, ""):
        out["toc_do"] = max(0.3, min(5.0, float(params["toc_do"])))
    if params.get("chi_render") not in (None, "", 0):
        out["chi_render"] = max(5.0, float(params["chi_render"]))
    return out


def thu_muc_da_ve() -> list:
    """Nơi tìm video vẽ tranh ĐÃ render: `output/` + các thư mục khai ở
    `data/ve-tranh.json` {"thu_muc_them": [...]} — video thường được chép sang kho
    nền (vd H:/KHO-VIDEO/2-ve-tranh) rồi xoá khỏi output, không tìm ở đó thì
    ảnh đã vẽ lại hiện là "chưa vẽ"."""
    ds = [OUTPUT]
    try:
        them = json.loads(VE_TRANH_CAI_DAT.read_text(encoding="utf-8")).get("thu_muc_them") or []
        ds += [Path(x) for x in them if x]
    except (OSError, ValueError):
        pass
    return ds


def dem_da_ve() -> dict:
    """{tên ảnh: số video đã vẽ}. Đọc trường `tranh` trong file .json cạnh mỗi mp4
    (app ghi lúc render xong). Đếm theo TÊN FILE video để một video vừa nằm ở
    output vừa được chép sang kho không bị tính hai lần."""
    thay = {}
    for d in thu_muc_da_ve():
        if not d.is_dir():
            continue
        for j in d.rglob("ve-tranh*.json"):
            if j.parent.name.startswith("_") or not j.with_suffix(".mp4").is_file():
                continue
            try:
                ten = json.loads(j.read_text(encoding="utf-8")).get("tranh")
            except (OSError, ValueError):
                continue
            if ten:
                thay.setdefault(ten, set()).add(j.stem)
    return {k: len(v) for k, v in thay.items()}


def list_tranh(jobs=None):
    TRANH_DIR.mkdir(parents=True, exist_ok=True)
    da_ve = dem_da_ve()
    # Đang chờ / đang render: tính riêng để bấm "chưa vẽ" hai lần không xếp trùng.
    dang = {}
    for j in (jobs.list() if jobs else []):
        a = (j.get("params") or {}).get("anh")
        if j.get("game") == "ve-tranh" and a and j.get("status") in ("queued", "running"):
            dang[a] = dang.get(a, 0) + 1
    out = []
    for p in sorted(TRANH_DIR.iterdir(), key=lambda x: x.name.lower()):
        if p.suffix.lower() in TRANH_EXT and p.is_file():
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime,
                        "da_ve": da_ve.get(p.name, 0), "dang_ve": dang.get(p.name, 0),
                        "url": "/assets/ve-tranh/tranh/" + quote(p.name) + f"?v={int(st.st_mtime)}"})
    return out


def save_tranh(name, data_b64):
    name = re.sub(r'[\\/:*?"<>|]+', "_", Path(str(name or "")).name).strip() or "tranh.jpg"
    if not TEN_TRANH.match(name):
        raise ValueError("Chỉ nhận ảnh .jpg, .png, .webp")
    raw = base64.b64decode(str(data_b64 or "").split(",")[-1])
    if len(raw) > 40 * 1024 * 1024:
        raise ValueError("Ảnh quá lớn (tối đa 40 MB)")
    TRANH_DIR.mkdir(parents=True, exist_ok=True)
    p = TRANH_DIR / name
    stem, n = p.stem, 2
    while p.exists():                     # trùng tên thì thêm số, không ghi đè
        p = TRANH_DIR / f"{stem}-{n}{p.suffix}"
        n += 1
    p.write_bytes(raw)
    return p.name


def clean_template(mod, params):
    """Giao diện + bộ icon (chỉ game có module template)."""
    tpl = getattr(mod, "T", None)
    out = {}
    if tpl is None:
        return out
    if params.get("theme") in tpl.THEMES:
        out["theme"] = params["theme"]
    if params.get("items") in tpl.ITEM_SETS:
        out["items"] = params["items"]
    return out


def clean_board(cfg, params):
    """Level và điểm Top 1-3 trên HUD (chỉ game có các khóa này)."""
    out = {}
    if "level" in cfg and str(params.get("level") or "").strip():
        out["level"] = int(float(params["level"]))
    if "leaderboard" in cfg and params.get("leaderboard"):
        out["leaderboard"] = re.sub(r"[^0-9 ,.;]", "", str(params["leaderboard"])).strip()
    return out


def clean_tune(cfg, tune):
    out = {}
    for k, v in (tune or {}).items():
        if k in TUNE_KEYS and k in cfg and v not in (None, ""):
            out[k] = type(cfg[k])(float(v))
    return out


def simulate(key, cfg):
    mod = game_module(key)
    game = getattr(mod, GAMES[key]["cls"])(cfg).play()
    if key == "kim-cuong":
        summary = {"score": game.score, **game.stats}
    elif key == "ve-tranh":
        summary = {"giay": round(game.stats["giay"], 1), "giay_net": round(game.stats["giay_net"], 1),
                   "net": game.stats["net"], "vung": game.stats["vung"], "tranh": game.path.name}
    else:
        summary = {"money": game.money, "harvests": game.stats["harvests"], "plots": game.stats["plots"],
                   "best_sale": game.stats["best_sale"], "best_crop": mod.CROPS[game.best_crop][0]}
    return mod, game, summary


# ============================================================================
# Hàng đợi render
# ============================================================================
class Job:
    _next = 1
    _lock = threading.Lock()

    def __init__(self, game, params):
        with Job._lock:
            self.id = Job._next
            Job._next += 1
        self.game = game
        self.params = params
        self.status = "queued"
        self.progress = 0.0
        self.message = "Đang chờ"
        self.summary = ""
        self.out = None
        self.created = time.time()
        self.started = self.finished = None
        self.proc = None
        self.cancel = False

    def to_dict(self):
        return {"id": self.id, "game": self.game, "params": self.params, "status": self.status,
                "progress": self.progress, "message": self.message, "summary": self.summary,
                "out": self.out, "created": self.created, "started": self.started, "finished": self.finished}


class JobQueue:
    def __init__(self, workers):
        self.jobs = {}
        self.q = queue.Queue()
        self.lock = threading.Lock()
        for _ in range(workers):
            threading.Thread(target=self.worker, daemon=True).start()

    def add(self, game, params):
        job = Job(game, params)
        with self.lock:
            self.jobs[job.id] = job
        self.q.put(job)
        return job

    def list(self):
        with self.lock:
            return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: -j.id)]

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            return
        job.cancel = True
        if job.status == "queued":
            job.status, job.message = "cancelled", "Đã hủy"
        elif job.proc and job.proc.poll() is None:
            job.proc.terminate()

    def clear(self):
        with self.lock:
            for jid in [j.id for j in self.jobs.values() if j.status in ("done", "error", "cancelled")]:
                del self.jobs[jid]

    def worker(self):
        while True:
            job = self.q.get()
            if job.cancel:
                continue
            try:
                self.run(job)
            except Exception as e:  # không để một job lỗi làm chết worker
                job.status, job.message = "error", f"Lỗi: {e}"
                job.finished = time.time()

    def run(self, job):
        p = job.params
        seed = int(p.get("seed") or 1)
        day = time.strftime("%Y-%m-%d")
        out = OUTPUT / day / f"{job.game}_seed{seed}_{time.strftime('%H%M%S')}_{job.id}.mp4"
        cmd = [sys.executable, "-u", str(GAMES[job.game]["script"]), "--seed", str(seed), "--out", str(out)]
        for k in ("hook", "question", "duration"):
            if p.get(k):
                cmd += [f"--{k}", str(p[k])]
        if p.get("speed") and job.game == "kim-cuong":
            cmd += ["--speed", str(p["speed"])]
        mod_cfg = game_module(job.game).CONFIG
        art = clean_art(mod_cfg, p)
        if "anh" in art:
            cmd += ["--anh", art.pop("anh")]
        for k, v in {**clean_tune(mod_cfg, p.get("tune")), **clean_board(mod_cfg, p),
                     **clean_template(game_module(job.game), p), **art}.items():
            cmd += ["--set", f"{k}={v}"]
        job.status, job.started, job.message = "running", time.time(), "Đang mô phỏng ván"
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        job.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                    cwd=str(GAMES[job.game]["script"].parent))
        buf = b""
        tail = []
        while True:
            chunk = job.proc.stdout.read1(512)
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                m = re.search(r"render\s+([\d.]+)%", line)
                if m:
                    job.progress = float(m.group(1)) / 100
                    job.message = f"Đang render {m.group(1)}%"
                elif line.startswith("Ván số"):
                    job.summary = line
                else:
                    tail = (tail + [line])[-6:]
        code = job.proc.wait()
        job.finished = time.time()
        if job.cancel:
            job.status, job.message = "cancelled", "Đã hủy"
            for _ in range(10):
                try:
                    out.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.3)
            return
        if code != 0 or not out.exists():
            job.status, job.message = "error", " · ".join(tail[-3:]) or f"Mã lỗi {code}"
            return
        meta = {"game": job.game, "seed": seed, "hook": p.get("hook") or "", "question": p.get("question") or "",
                "duration": float(p.get("duration") or 0) or None, "speed": p.get("speed"), "tune": p.get("tune"),
                "theme": p.get("theme"), "items": p.get("items"), "summary": job.summary,
                "tranh": p.get("anh"), "cat": p.get("cat"), "toc_do": p.get("toc_do"),
                "chi_render": p.get("chi_render"),
                "created": time.strftime("%Y-%m-%d %H:%M"), "posted": False}
        out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        make_thumb(out)
        job.out = out.relative_to(OUTPUT).as_posix()
        job.status, job.progress = "done", 1.0
        job.message = f"Xong sau {job.finished - job.started:.0f} giây"


def make_thumb(video):
    thumb = video.with_suffix(".jpg")
    ffmpeg = shutil.which("ffmpeg")
    if thumb.exists() or not ffmpeg:
        return
    if video.name.startswith("ve-tranh"):      # vẽ tranh: bìa là tranh đã xong (cuối video)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-sseof", "-1.5", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(thumb)], capture_output=True)
        if thumb.exists():
            return
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "18", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=360:-2", str(thumb)], capture_output=True)
    if not thumb.exists():   # video ngắn hơn 18 giây
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(thumb)], capture_output=True)


# ============================================================================
# Dữ liệu: hook, số liệu, thư viện
# ============================================================================
def parse_hooks(text):
    hooks = {k: [] for k in GAMES}
    section = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            low = s.lower()
            if "kim" in low:
                section = "kim-cuong"
            elif "nông" in low or "nong" in low:
                section = "nong-trai"
            continue
        for k in ([section] if section else GAMES):
            if s not in hooks[k]:
                hooks[k].append(s)
    return hooks


def read_stats():
    if not STATS_FILE.exists():
        return {"header": [], "rows": []}
    with open(STATS_FILE, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return {"header": rows[0] if rows else [], "rows": rows[1:]}


def write_stats(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    STATS_FILE.write_text(buf.getvalue(), encoding="utf-8-sig")


def safe_output_path(rel):
    p = (OUTPUT / rel).resolve()
    if OUTPUT.resolve() not in p.parents:
        raise ValueError("đường dẫn không hợp lệ")
    return p


def library():
    items = []
    if not OUTPUT.exists():
        return items
    for mp4 in OUTPUT.rglob("*.mp4"):
        if PREVIEW_DIR in mp4.parents:
            continue
        meta_file = mp4.with_suffix(".json")
        meta = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except ValueError:
                pass
        if not meta.get("game"):
            meta["game"] = next((k for k in GAMES if mp4.name.startswith(k)), "")
            m = re.search(r"seed(\d+)", mp4.name)
            meta["seed"] = int(m.group(1)) if m else None
        make_thumb(mp4)
        st = mp4.stat()
        rel = mp4.relative_to(OUTPUT).as_posix()
        thumb = mp4.with_suffix(".jpg")
        items.append({**meta, "path": rel, "name": mp4.name, "size": st.st_size, "mtime": st.st_mtime,
                      "thumb": thumb.relative_to(OUTPUT).as_posix() if thumb.exists() else None})
    items.sort(key=lambda x: -x["mtime"])
    return items


# ============================================================================
# KHO NỀN — clip game làm NỀN ĐỘNG cho video đọc truyện (video-ticktok › project_5)
#
# KHÁC HẲN "Tạo video" / "Render hàng loạt": hai nút đó làm video SHORTS để đăng
# (có hook, end card "HẾT GIỜ! Bình luận dự đoán", chớp sáng). Kho nền làm clip ở
# chế độ `--nen` (bỏ hết mấy thứ đó) vào MỘT THƯ MỤC RIÊNG, để dự án khác bốc ra
# nối làm nền cho giọng đọc truyện 1–2 tiếng.
#
# Web KHÔNG tự tính gì: mọi việc (dò seed, xoay template, render, manifest) nằm ở
# tao_kho_nen.py, web chỉ gọi nó như chạy dòng lệnh và đọc log. Chạy tay hay bấm
# nút đều ra cùng một kho.
#
# HỢP ĐỒNG với bên dùng kho: đọc `<kho>/manifest.json` (tên file TƯƠNG ĐỐI trong
# thư mục kho ⇒ chép cả thư mục đi đâu cũng dùng được). Đừng quét *.mp4 — clip
# đang render dở tên `_dang_…mp4`.
# ============================================================================
KHO_SCRIPT = ROOT / "tao_kho_nen.py"
KHO_CAI_DAT = ROOT / "data" / "kho-nen.json"
KHO_MAC_DINH = ROOT / "kho-nen" / "kim-cuong"
TEN_FILE_KHO = re.compile(r"^[\w.-]+\.(mp4|jpg|json)$")


def kho_hien_tai() -> Path:
    try:
        p = json.loads(KHO_CAI_DAT.read_text(encoding="utf-8")).get("kho")
        if p:
            return Path(p)
    except (OSError, ValueError):
        pass
    return KHO_MAC_DINH


def luu_kho(p: str) -> Path:
    p = (p or "").strip().strip('"')
    if not p:
        raise ValueError("Chưa nhập thư mục kho")
    kho = Path(os.path.expandvars(os.path.expanduser(p)))
    if not kho.is_absolute():
        raise ValueError("Cần đường dẫn đầy đủ, ví dụ D:\\KHO-VIDEO\\nen-game")
    kho.mkdir(parents=True, exist_ok=True)       # chưa có thì tạo luôn
    KHO_CAI_DAT.parent.mkdir(parents=True, exist_ok=True)
    KHO_CAI_DAT.write_text(json.dumps({"kho": str(kho)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return kho


def doc_manifest(kho: Path) -> dict:
    try:
        return json.loads((kho / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"so_clip": 0, "tong_giay": 0, "clip": []}


def chon_thu_muc_windows(ban_dau: str) -> str:
    """Mở hộp thoại chọn thư mục của Windows NGAY TRÊN MÁY chạy server.

    Trình duyệt không bao giờ đưa đường dẫn thật của thư mục cho trang web (chặn vì
    bảo mật), nên phải nhờ server — được vì server chạy trên chính máy này.
    tkinter chạy trong tiến trình con cho khỏi đụng luồng của server.
    """
    code = ("import tkinter as tk, tkinter.filedialog as fd, sys\n"
            "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
            "p = fd.askdirectory(initialdir=sys.argv[1] or None, title='Chọn thư mục KHO NỀN')\n"
            "sys.stdout.write(p or '')\n")
    r = subprocess.run([sys.executable, "-c", code, ban_dau], capture_output=True, text=True,
                       encoding="utf-8", timeout=600)
    if r.returncode != 0:
        raise ValueError("Không mở được hộp thoại chọn thư mục — dán đường dẫn vào ô nhập.")
    return (r.stdout or "").strip().replace("/", os.sep)


class KhoRunner:
    """MỘT lượt làm kho tại một thời điểm (hai lượt cùng kho sẽ xoá file dở của nhau)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.st = {"trang_thai": "nghi", "log": [], "xong": 0, "loi": 0, "tong": 0, "ke_hoach": 0,
                   "vong": 0, "so_vong": 0, "bat_dau": None, "ket_thuc": None, "kho": ""}

    def dang_chay(self):
        return self.proc is not None and self.proc.poll() is None

    def trang_thai(self):
        with self.lock:
            return {**self.st, "log": self.st["log"][-200:]}

    def bat_dau(self, kho: Path, so: int, giay: float, hud: bool, song_song: int, vong: int = 1):
        with self.lock:
            if self.dang_chay():
                raise ValueError("Đang có một lượt làm kho — đợi xong hoặc bấm Dừng.")
            so = max(1, min(200, so))
            vong = max(1, min(50, vong))
            cmd = [sys.executable, "-u", str(KHO_SCRIPT), "--so", str(so), "--vong", str(vong), "--giay", str(giay),
                   "--song-song", str(max(1, min(6, song_song))), "--kho", str(kho)]
            if not hud:
                cmd.append("--khong-hud")
            self.st = {"trang_thai": "chay", "log": [], "xong": 0, "loi": 0, "tong": so * vong, "ke_hoach": 0,
                       "vong": 1, "so_vong": vong, "so_moi_vong": so,
                       "bat_dau": time.time(), "ket_thuc": None, "kho": str(kho)}
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                         cwd=str(ROOT))
        threading.Thread(target=self._doc, args=(self.proc,), daemon=True).start()

    def _doc(self, proc):
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            with self.lock:
                self.st["log"].append(line)
                del self.st["log"][:-400]
                mv = re.match(r"━━ Vòng (\d+)/(\d+)", line)
                if mv:
                    self.st["vong"] = int(mv.group(1))
                if "kế hoạch " in line and "/" in line:
                    self.st["ke_hoach"] += 1
                if line.lstrip().startswith("✓ ["):
                    self.st["xong"] += 1
                elif line.lstrip().startswith("✗ ["):
                    self.st["loi"] += 1
        code = proc.wait()
        with self.lock:
            if self.st["trang_thai"] == "chay":
                self.st["trang_thai"] = "xong" if code == 0 else "loi"
            self.st["ket_thuc"] = time.time()

    def dung(self):
        with self.lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return False
            self.st["trang_thai"] = "dung"
        # /T: giết cả cây — tao_kho_nen đẻ ra gem_bot, gem_bot đẻ ra ffmpeg.
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.wait()
        kho = Path(self.st["kho"])
        for rac in kho.glob("_dang_*.mp4"):
            for _ in range(10):          # ffmpeg vừa bị giết có thể còn giữ file một nhịp
                try:
                    rac.unlink()
                    break
                except PermissionError:
                    time.sleep(0.3)
                except OSError:
                    break
        ghi_lai_manifest(kho)
        with self.lock:
            self.st["log"].append("■ Đã dừng. Clip render xong vẫn nằm trong kho — bấm Làm tiếp để làm thêm.")
        return True


def ghi_lai_manifest(kho: Path):
    subprocess.run([sys.executable, str(KHO_SCRIPT), "--kho", str(kho), "--ghi-manifest"],
                   capture_output=True, cwd=str(ROOT), env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def kho_info(runner: "KhoRunner") -> dict:
    kho = kho_hien_tai()
    m = doc_manifest(kho)
    dem = {}
    for c in m.get("clip", []):
        k = f"{c.get('giao_dien', '?')} + {c.get('bo_icon', '?')}"
        dem[k] = dem.get(k, 0) + 1
    return {"kho": str(kho), "mac_dinh": str(KHO_MAC_DINH), "co_thu_muc": kho.is_dir(),
            "manifest": str(kho / "manifest.json"),
            "so_clip": m.get("so_clip", 0), "tong_giay": m.get("tong_giay", 0),
            "mb": round(sum(c.get("mb", 0) for c in m.get("clip", [])), 1),
            "cap_nhat": m.get("cap_nhat"), "dem_kieu": dem,
            "clip": sorted(m.get("clip", []), key=lambda c: c.get("tao_luc", ""), reverse=True),
            "chay": runner.trang_thai()}


def open_in_explorer(path):
    if sys.platform.startswith("win"):
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ============================================================================
# HTTP
# ============================================================================
class Handler(BaseHTTPRequestHandler):
    jobs = None
    kho = None       # KhoRunner

    def log_message(self, *args):
        pass

    # ---------- trả về ----------
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, msg, code=400):
        self.send_json({"error": msg}, code)

    def send_file(self, path, cache=False):
        if not path.is_file():
            return self.send_error_json("Không tìm thấy file", 404)
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".ttf":
            ctype = "font/ttf"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ---------- định tuyến ----------
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                return self.send_file(UI_FILE)
            if path.startswith("/assets/"):
                p = (ROOT / path.lstrip("/")).resolve()
                if (ROOT / "assets").resolve() not in p.parents:
                    return self.send_error_json("Không hợp lệ", 403)
                return self.send_file(p, cache=True)
            if path.startswith("/files/"):
                return self.send_file(safe_output_path(path[len("/files/"):]))
            if path.startswith("/kho-file/"):
                # chỉ TÊN FILE trần trong thư mục kho — không nhận `..` hay đường dẫn con
                ten = path[len("/kho-file/"):]
                if not TEN_FILE_KHO.match(ten):
                    return self.send_error_json("Không hợp lệ", 403)
                return self.send_file(kho_hien_tai() / ten)
            if path == "/api/kho":
                return self.send_json(kho_info(self.kho))
            if path == "/api/kho/tien-do":
                return self.send_json(self.kho.trang_thai())
            if path == "/api/info":
                return self.send_json(self.info())
            if path == "/api/jobs":
                return self.send_json(self.jobs.list())
            if path == "/api/library":
                return self.send_json(library())
            if path == "/api/hooks":
                return self.send_json({"text": HOOKS_FILE.read_text(encoding="utf-8") if HOOKS_FILE.exists() else ""})
            if path == "/api/stats":
                return self.send_json(read_stats())
            if path == "/api/tranh":
                return self.send_json({"dir": str(TRANH_DIR), "items": list_tranh(self.jobs),
                                       "thu_muc_da_ve": [str(d) for d in thu_muc_da_ve()]})
            self.send_error_json("Không tìm thấy", 404)
        except Exception as e:
            self.send_error_json(str(e), 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.body()
            if path == "/api/jobs":
                items = data.get("items") or [data]
                ids = []
                for it in items:
                    if it.get("game") not in GAMES:
                        return self.send_error_json("Game không hợp lệ")
                    ids.append(self.jobs.add(it["game"], {k: it.get(k) for k in
                                                          ("seed", "hook", "question", "duration", "speed", "tune", "level",
                                                           "leaderboard", "theme", "items", "anh", "cat", "toc_do",
                                                           "chi_render")}).id)
                return self.send_json({"ids": ids})
            if path == "/api/kho/thu-muc":
                if self.kho.dang_chay():
                    return self.send_error_json("Đang làm kho — dừng lượt đang chạy rồi mới đổi thư mục.")
                kho = luu_kho(data.get("kho", ""))
                return self.send_json({"ok": True, "kho": str(kho)})
            if path == "/api/kho/chon":
                return self.send_json({"kho": chon_thu_muc_windows(str(kho_hien_tai()))})
            if path == "/api/kho/lam":
                kho = kho_hien_tai()
                kho.mkdir(parents=True, exist_ok=True)
                self.kho.bat_dau(kho, int(data.get("so") or 9), float(data.get("giay") or 180),
                                 bool(data.get("hud", True)), int(data.get("song_song") or 3),
                                 int(data.get("vong") or 1))
                return self.send_json({"ok": True})
            if path == "/api/kho/dung":
                return self.send_json({"ok": self.kho.dung()})
            if path == "/api/kho/mo":
                kho = kho_hien_tai()
                kho.mkdir(parents=True, exist_ok=True)
                open_in_explorer(kho)
                return self.send_json({"ok": True})
            if path == "/api/kho/xoa":
                if self.kho.dang_chay():
                    return self.send_error_json("Đang làm kho — đợi xong rồi hãy xoá clip.")
                ten = str(data.get("file") or "")
                if not TEN_FILE_KHO.match(ten) or not ten.endswith(".mp4"):
                    return self.send_error_json("Tên file không hợp lệ")
                kho = kho_hien_tai()
                for duoi in (".mp4", ".json", ".jpg"):
                    (kho / ten).with_suffix(duoi).unlink(missing_ok=True)
                ghi_lai_manifest(kho)
                return self.send_json({"ok": True})
            if path == "/api/tranh/upload":
                names = [save_tranh(f.get("name"), f.get("data")) for f in (data.get("files") or [])]
                return self.send_json({"ok": True, "names": names})
            if path == "/api/tranh/delete":
                tranh_path(data.get("name")).unlink()
                return self.send_json({"ok": True})
            if path == "/api/tranh/mo":
                TRANH_DIR.mkdir(parents=True, exist_ok=True)
                open_in_explorer(TRANH_DIR)
                return self.send_json({"ok": True})
            if path == "/api/jobs/cancel":
                self.jobs.cancel(int(data["id"]))
                return self.send_json({"ok": True})
            if path == "/api/jobs/clear":
                self.jobs.clear()
                return self.send_json({"ok": True})
            if path == "/api/preview":
                return self.send_json(self.preview(data))
            if path == "/api/scan":
                return self.send_json(self.scan(data))
            if path == "/api/templates":
                return self.send_json(self.templates())
            if path == "/api/library/meta":
                p = safe_output_path(data["path"]).with_suffix(".json")
                meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
                meta.update({k: v for k, v in data.items() if k in ("posted", "note")})
                p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                return self.send_json({"ok": True})
            if path == "/api/library/delete":
                p = safe_output_path(data["path"])
                for ext in (".mp4", ".json", ".jpg"):
                    p.with_suffix(ext).unlink(missing_ok=True)
                return self.send_json({"ok": True})
            if path == "/api/open-folder":
                target = safe_output_path(data["path"]).parent if data.get("path") else OUTPUT
                target.mkdir(parents=True, exist_ok=True)
                open_in_explorer(target)
                return self.send_json({"ok": True})
            self.send_error_json("Không tìm thấy", 404)
        except Exception as e:
            self.send_error_json(str(e), 500)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            data = self.body()
            if path == "/api/hooks":
                HOOKS_FILE.write_text(data.get("text", ""), encoding="utf-8")
                return self.send_json({"ok": True, "hooks": parse_hooks(data.get("text", ""))})
            if path == "/api/stats":
                write_stats(data["header"], data["rows"])
                return self.send_json({"ok": True})
            self.send_error_json("Không tìm thấy", 404)
        except Exception as e:
            self.send_error_json(str(e), 500)

    # ---------- xử lý ----------
    def info(self):
        games = {}
        for key, g in GAMES.items():
            cfg = game_module(key).CONFIG
            mod = game_module(key)
            games[key] = {"name": g["name"], "hook": cfg["hook"], "question": cfg["question"],
                          "duration": cfg["duration"], "seed": cfg["seed"],
                          "tune": {k: cfg[k] for k in TUNE_KEYS if k in cfg}}
            tpl = getattr(mod, "T", None)
            if tpl is not None:
                games[key]["themes"] = {k: v["name"] for k, v in tpl.THEMES.items()}
                games[key]["items"] = {k: v["name"] for k, v in tpl.ITEM_SETS.items()}
                games[key]["theme"], games[key]["item_set"] = cfg["theme"], cfg["items"]
            if "anh" in cfg:
                games[key]["toc_do"] = cfg["toc_do"]
        text = HOOKS_FILE.read_text(encoding="utf-8") if HOOKS_FILE.exists() else ""
        return {"games": games, "hooks": parse_hooks(text), "ffmpeg": bool(shutil.which("ffmpeg")),
                "workers": WORKERS, "output": str(OUTPUT)}

    def preview(self, data):
        key = data.get("game")
        if key not in GAMES:
            raise ValueError("Game không hợp lệ")
        mod = game_module(key)
        cfg = build_cfg(mod, data)
        with _render_lock:
            mod, game, summary = simulate(key, cfg)
            renderer = mod.Renderer(game, cfg)
            PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
            images = []
            stamp = int(time.time() * 1000)
            seconds = data.get("seconds") or [5, 20, 36]
            labels = [None] * len(seconds)
            if key == "ve-tranh":   # 4 khung theo đúng các bước: đang phác · phác xong · tô mảng · xong
                g = game
                seconds = [g.t_s0 + (g.t_s1 - g.t_s0) * 0.4, g.t_s1, (g.t_f0 + g.t_f1) / 2, g.duration - 1]
                labels = ["Đang phác nét", "Phác xong", "Tô mảng màu", "Hoàn thành"]
                if cfg.get("chi_render"):
                    seconds = [min(s, game.total / cfg["fps"] - 0.1) for s in seconds]
            for i, sec in enumerate(seconds):
                f = max(0, min(game.total - 1, int(float(sec) * cfg["fps"])))
                p = PREVIEW_DIR / f"{key}_{i}.jpg"
                renderer.render(f).convert("RGB").save(p, quality=85)
                images.append({"sec": round(float(sec), 1), "label": labels[i],
                               "url": f"/files/_preview/{p.name}?v={stamp}"})
        return {"images": images, "summary": summary, "seed": cfg["seed"]}

    def templates(self):
        """Ảnh thu nhỏ cho 9 template kim cương (tạo lại khi code template thay đổi)."""
        key = "kim-cuong"
        mod = game_module(key)
        stamp = max(p.stat().st_mtime for p in GAMES[key]["script"].parent.glob("*.py"))
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        out = []
        with _render_lock:
            for th in mod.T.THEMES:
                for it in mod.T.ITEM_SETS:
                    p = TEMPLATE_DIR / f"{th}_{it}.jpg"
                    if not p.exists() or p.stat().st_mtime < stamp:
                        cfg = dict(mod.CONFIG, seed=3, duration=20, theme=th, items=it, hook="Bạn đoán nước tiếp theo?")
                        game = mod.GemGame(cfg).play()
                        img = mod.Renderer(game, cfg).render(int(6.3 * cfg["fps"]))
                        img.crop((0, 0, cfg["width"], 1560)).resize((270, 390)).convert("RGB").save(p, quality=85)
                    out.append({"theme": th, "items": it, "url": f"/files/_templates/{p.name}?v={int(p.stat().st_mtime)}"})
        return out

    def scan(self, data):
        key = data.get("game")
        if key not in GAMES:
            raise ValueError("Game không hợp lệ")
        a, b = int(data.get("from", 1)), int(data.get("to", 20))
        if b < a:
            a, b = b, a
        b = min(b, a + MAX_SCAN - 1)
        mod = game_module(key)
        rows = []
        for seed in range(a, b + 1):
            cfg = build_cfg(mod, {**data, "seed": seed})
            _, _, summary = simulate(key, cfg)
            rows.append({"seed": seed, **summary})
        return {"rows": rows}


WORKERS = 2


def main():
    global WORKERS
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Giao diện quản lý Xương - video - game")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--workers", type=int, default=2, help="số video render cùng lúc")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    WORKERS = max(1, args.workers)
    OUTPUT.mkdir(exist_ok=True)
    Handler.jobs = JobQueue(WORKERS)
    Handler.kho = KhoRunner()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Xương - video - game đang chạy tại {url}  (Ctrl+C để tắt)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã tắt.")


if __name__ == "__main__":
    main()
