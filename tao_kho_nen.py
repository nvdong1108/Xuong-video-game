#!/usr/bin/env python3
"""tao_kho_nen.py — làm KHO CLIP NỀN (game tự chơi) cho video đọc truyện.

Bên dựng video truyện (video-ticktok / project_5) KHÔNG render game lúc dựng: một
tập 2 tiếng mà vẽ game trực tiếp là thêm ~90 phút CPU (đo thật: 0,74 giây CPU cho
mỗi giây game). Nên làm sẵn một kho clip 3 phút ở đây MỘT LẦN, bên kia chỉ bốc
clip trong kho ra nối lại — ghép như thế chỉ chậm hơn ảnh tĩnh ~18%.

    python tao_kho_nen.py --so 6               # làm thêm 6 clip (chạy lại là làm TIẾP, không làm lại)
    python tao_kho_nen.py --so 9 --vong 10     # 10 vòng × 9 clip = 90 clip, chạy một lần qua đêm
    python tao_kho_nen.py --so 30 --xem        # chỉ in kế hoạch, không render
    python tao_kho_nen.py --liet-ke            # kho đang có gì, tổng bao nhiêu phút
    python tao_kho_nen.py --so 6 --khong-hud   # bỏ bảng TOP/Level/điểm trên cùng

Kết quả: kho-nen/kim-cuong/
    kc_<giao diện>_<bộ icon>_s<seed>.mp4   clip 1080×1920, không tiếng
    ….json                                 cấu hình + tóm tắt ván của clip đó
    ….jpg                                  một khung hình để lướt xem
    manifest.json                          DANH SÁCH CHÍNH THỨC — bên dùng kho chỉ đọc file này

⚠️ Bên dùng kho phải đọc manifest.json, ĐỪNG quét *.mp4: clip đang render dở mang
tên `_dang_….mp4`, chỉ khi render xong mới đổi tên và vào manifest.

=== LÀM SAO CHO NHIỀU MẪU, KHÔNG TRÙNG ===
Mỗi clip khác nhau ở 4 lớp, lớp nào cũng đổi được mà không tốn công vẽ:
  1. Template: 3 giao diện × 3 bộ icon = 9 kiểu nhìn — xoay ĐỀU (kiểu nào ít
     clip nhất thì làm trước), nên 9 clip đầu đã đủ 9 kiểu.
  2. Seed: mỗi seed một ván khác hẳn (bàn cờ, nước đi, bom). Không bao giờ dùng
     lại seed đã có trong kho.
  3. Nhịp chơi: tốc độ, độ giỏi, thời gian nghĩ, mưa bom thưa/dày/tắt — bốc
     ngẫu nhiên trong khoảng an toàn cho từng clip.
  4. Chọn lọc: mô phỏng một ván chỉ mất 0,08 giây, nên với MỖI clip thử `--do`
     seed (mặc định 40) rồi render ván kịch tính nhất — ván nhạt không bao giờ
     vào kho.
Giới hạn thật chỉ là thời gian render (~2 phút CPU cho 1 clip 3 phút).
"""
import argparse
import json
import os
import random
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEM_DIR = ROOT / "kim-cuong"
KHO_MAC_DINH = ROOT / "kho-nen"

sys.path.insert(0, str(GEM_DIR))
import gem_bot as G          # noqa: E402  — chỉ dùng để MÔ PHỎNG chọn seed; render chạy tiến trình riêng
import gem_templates as T    # noqa: E402

# Khoảng bốc ngẫu nhiên cho nhịp chơi. Để nền cho người NGHE truyện nên nghiêng
# về chậm và đều: speed <1, mưa bom thưa. Sửa ở đây là đổi cho mọi clip mới.
KHOANG_NHIP = {
    "speed": (0.7, 0.95),
    "skill": (0.45, 0.9),
    "think_min": (0.5, 0.8),
    "think_max": (1.2, 1.9),
    "decoy_chance": (0.2, 0.5),
    "bomb_spawn": (0.025, 0.045),
}
MUA_BOM = [0, 20, 30, 45]          # giây giữa hai trận mưa bom (0 = tắt)


def _in(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------
def doc_kho(kho: Path) -> list:
    """Đọc các file .json cạnh mp4 — đó là nguồn sự thật; manifest chỉ là bản gộp.
    Clip mất mp4 thì bỏ qua (người dùng xoá tay một clip xấu là chuyện thường)."""
    ds = []
    for j in sorted(kho.glob("kc_*.json")):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (kho / d.get("file", "")).is_file():
            ds.append(d)
    return ds


def ghi_manifest(kho: Path) -> dict:
    ds = doc_kho(kho)
    m = {
        "phien_ban": 1,
        "game": "kim-cuong",
        "khung": [G.CONFIG["width"], G.CONFIG["height"]],
        "fps": G.CONFIG["fps"],
        "so_clip": len(ds),
        "tong_giay": round(sum(d.get("giay", 0) for d in ds), 1),
        "cap_nhat": time.strftime("%Y-%m-%d %H:%M:%S"),
        "clip": ds,
    }
    tam = kho / f"manifest.{os.getpid()}.{threading.get_ident()}.tmp"
    tam.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tam, kho / "manifest.json")      # ghi kiểu đổi tên: bên đọc không vớ file viết dở
    return m


# ---------------------------------------------------------------------------
# lập kế hoạch
# ---------------------------------------------------------------------------
def diem_kich_tinh(stats: dict) -> float:
    """Càng nhiều vụ nổ, nổ liên hoàn càng dài, combo càng cao thì càng đáng xem."""
    return stats["explosions"] + 15 * stats["max_chain"] + 10 * stats["max_combo"] + stats["moves"]


def bot_nhip(rng: random.Random) -> dict:
    t = {k: round(rng.uniform(*v), 3) for k, v in KHOANG_NHIP.items()}
    if t["think_max"] < t["think_min"] + 0.4:
        t["think_max"] = round(t["think_min"] + 0.4, 3)
    t["rain_every"] = rng.choice(MUA_BOM)
    t["rain_count"] = rng.randint(4, 6)
    return t


def lap_ke_hoach(so: int, kho: Path, giay: float, do: int, hud: bool, rng: random.Random,
                 moi_clip=None) -> list:
    co = doc_kho(kho)
    da_dung = {d["seed"] for d in co}
    dem = {(th, it): 0 for th in T.THEMES for it in T.ITEM_SETS}
    for d in co:
        k = (d.get("theme"), d.get("items"))
        if k in dem:
            dem[k] += 1

    ke_hoach = []
    for _ in range(so):
        it_nhat = min(dem.values())
        th, it = rng.choice([k for k, v in dem.items() if v == it_nhat])
        dem[(th, it)] += 1
        nhip = bot_nhip(rng)

        tot = None
        for _ in range(do):
            seed = rng.randint(1, 999_999)
            if seed in da_dung:
                continue
            cfg = dict(G.CONFIG, seed=seed, duration=giay, theme=th, items=it, nen=True, hud=hud, **nhip)
            stats = G.GemGame(cfg).play().stats
            diem = diem_kich_tinh(stats)
            if tot is None or diem > tot[0]:
                tot = (diem, seed, stats, cfg)
        diem, seed, stats, cfg = tot
        da_dung.add(seed)
        ke_hoach.append({
            "ten": f"kc_{th}_{it}_s{seed}",
            "seed": seed, "theme": th, "items": it, "hud": hud,
            "giay_dat": giay, "nhip": nhip, "stats": stats, "diem": round(diem),
        })
        if moi_clip:
            moi_clip(len(ke_hoach), so, ke_hoach[-1])
    return ke_hoach


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------
_CON = set()          # tiến trình con đang chạy — Ctrl+C thì giết hết
_KHOA = threading.Lock()


def _thoi_luong(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return 0.0


def render_mot(kh: dict, kho: Path) -> dict:
    ten = kh["ten"]
    dang = kho / f"_dang_{ten}.mp4"
    ra = kho / f"{ten}.mp4"
    cmd = [sys.executable, "-u", str(GEM_DIR / "gem_bot.py"), "--nen",
           "--seed", str(kh["seed"]), "--duration", str(kh["giay_dat"]),
           "--theme", kh["theme"], "--items", kh["items"], "--out", str(dang)]
    for k, v in kh["nhip"].items():
        if k == "speed":
            cmd += ["--speed", str(v)]
        else:
            cmd += ["--set", f"{k}={v}"]
    if not kh["hud"]:
        cmd += ["--set", "hud=0"]

    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=str(GEM_DIR))
    with _KHOA:
        _CON.add(p)
    out, _ = p.communicate()
    with _KHOA:
        _CON.discard(p)
    if p.returncode != 0 or not dang.is_file():
        dang.unlink(missing_ok=True)
        duoi = out.decode("utf-8", "replace").replace("\r", "\n").strip().splitlines()[-5:]
        raise RuntimeError(f"{ten}: gem_bot lỗi (mã {p.returncode})\n      " + "\n      ".join(duoi))

    os.replace(dang, ra)
    anh = ra.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(min(60, kh["giay_dat"] / 2)), "-i", str(ra),
                    "-frames:v", "1", "-vf", "scale=360:-2", str(anh)], capture_output=True)
    d = {
        "file": ra.name, "anh": anh.name if anh.is_file() else "",
        "game": "kim-cuong", "seed": kh["seed"], "theme": kh["theme"], "items": kh["items"],
        "giao_dien": T.THEMES[kh["theme"]]["name"], "bo_icon": T.ITEM_SETS[kh["items"]]["name"],
        "hud": kh["hud"], "nhip": kh["nhip"], "stats": kh["stats"], "diem": kh["diem"],
        "giay": _thoi_luong(ra), "mb": round(ra.stat().st_size / 1048576, 1),
        "mat_giay": round(time.time() - t0), "tao_luc": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    ra.with_suffix(".json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def _mo_ta(kh: dict) -> str:
    n, s = kh["nhip"], kh["stats"]
    mua = f"mưa bom {n['rain_every']}s" if n["rain_every"] else "không mưa bom"
    kieu = f"{T.THEMES[kh['theme']]['name']} + {T.ITEM_SETS[kh['items']]['name']}"
    return (f"{kh['ten']:<30} {kieu:<22} "
            f"x{n['speed']:.2f} · {mua:<15} · {s['explosions']} nổ · liên hoàn {s['max_chain']} · điểm {kh['diem']}")


def liet_ke(kho: Path) -> int:
    ds = doc_kho(kho)
    if not ds:
        _in(f"Kho trống: {kho}")
        return 0
    tong = sum(d.get("giay", 0) for d in ds)
    mb = sum(d.get("mb", 0) for d in ds)
    _in(f"Kho {kho}: {len(ds)} clip · {tong / 60:.1f} phút KHÔNG TRÙNG · {mb:.0f} MB")
    dem = {}
    for d in ds:
        dem[(d["giao_dien"], d["bo_icon"])] = dem.get((d["giao_dien"], d["bo_icon"]), 0) + 1
    for (a, b), n in sorted(dem.items()):
        _in(f"  {a:<10} + {b:<10} {n} clip")
    thieu = len(T.THEMES) * len(T.ITEM_SETS) - len(dem)
    if thieu:
        _in(f"  (còn {thieu} kiểu chưa có clip nào)")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Làm kho clip game nền cho video đọc truyện")
    ap.add_argument("--so", type=int, default=6, help="số clip MỚI cần làm thêm (mặc định 6)")
    ap.add_argument("--vong", type=int, default=1,
                    help="lặp N vòng, mỗi vòng làm --so clip (vd --so 9 --vong 10 = 90 clip, bấm một lần)")
    ap.add_argument("--giay", type=float, default=180, help="độ dài mỗi clip (mặc định 180 = 3 phút)")
    ap.add_argument("--song-song", type=int, default=3, help="số clip render cùng lúc (mặc định 3)")
    ap.add_argument("--do", type=int, default=40, help="số seed thử cho mỗi clip để chọn ván kịch tính nhất")
    ap.add_argument("--khong-hud", action="store_true", help="bỏ bảng TOP/Level/điểm trên cùng")
    ap.add_argument("--kho", default=str(KHO_MAC_DINH / "kim-cuong"), help="thư mục kho")
    ap.add_argument("--xem", action="store_true", help="chỉ in kế hoạch, không render")
    ap.add_argument("--liet-ke", action="store_true", help="xem kho đang có gì")
    ap.add_argument("--ghi-manifest", action="store_true",
                    help="chỉ gộp lại manifest.json (sau khi xoá tay clip trong kho)")
    ap.add_argument("--gieo", type=int, help="hạt ngẫu nhiên của kế hoạch (để lặp lại đúng một kế hoạch)")
    a = ap.parse_args()

    kho = Path(a.kho).resolve()
    kho.mkdir(parents=True, exist_ok=True)
    if a.liet_ke:
        return liet_ke(kho)
    if a.ghi_manifest:
        m = ghi_manifest(kho)
        _in(f"✓ manifest: {m['so_clip']} clip · {m['tong_giay'] / 60:.1f} phút")
        return 0
    for rac in kho.glob("_dang_*.mp4"):        # lượt trước bị ngắt giữa chừng
        rac.unlink(missing_ok=True)

    rng = random.Random(a.gieo if a.gieo is not None else time.time_ns())
    vong = max(1, a.vong)
    if a.xem:
        vong = 1
    if vong > 1:
        uoc = vong * a.so * a.giay * 0.74 / max(1, min(a.song_song, a.so)) / 60
        _in(f"══ {vong} vòng × {a.so} clip = {vong * a.so} clip · ước ~{uoc:.0f} phút ══")

    def _dung(*_):
        with _KHOA:
            for p in _CON:
                p.kill()
        _in("\n■ Đã dừng. Clip render xong vẫn nằm trong kho; chạy lại để làm tiếp.")
        for rac in kho.glob("_dang_*.mp4"):
            try:
                rac.unlink()
            except OSError:
                pass
        ghi_manifest(kho)
        os._exit(130)

    if not a.xem:
        signal.signal(signal.SIGINT, _dung)

    # LÀM THEO TỪNG VÒNG (dò seed → render → vào manifest, rồi mới sang vòng sau),
    # KHÔNG dò trước cả 90 clip: dò mất ~4 giây/clip ⇒ 90 clip là 6 phút ngồi chờ mà
    # chưa có clip nào; và bấm Dừng giữa chừng thì các vòng đã xong vẫn nằm trong kho.
    # Vòng sau lập kế hoạch lại từ kho hiện tại ⇒ tự tránh seed vừa dùng, tự xoay tiếp
    # các kiểu giao diện còn ít clip.
    xong = loi = 0
    t_dau = time.time()
    for v in range(1, vong + 1):
        if vong > 1:
            _in(f"\n━━ Vòng {v}/{vong} ━━")
        t0 = time.time()
        # In TỪNG clip ngay khi dò xong (không đợi cả loạt) — im lặng lâu thì web tưởng treo.
        _in(f"Dò seed cho {a.so} clip × {a.giay:g}s (thử {a.do} seed/clip, chọn ván kịch tính nhất)…")
        kh = lap_ke_hoach(a.so, kho, a.giay, a.do, not a.khong_hud, rng,
                          lambda i, n, k: _in(f"  kế hoạch {i}/{n}: " + _mo_ta(k)))
        _in(f"Xong kế hoạch sau {time.time() - t0:.1f}s")
        if a.xem:
            return 0

        cung_luc = max(1, min(a.song_song, len(kh)))
        uoc = len(kh) * a.giay * 0.74 / cung_luc
        _in(f"Render {cung_luc} clip song song · ước ~{uoc / 60:.0f} phút (Ctrl+C để dừng, chạy lại là làm tiếp)")

        xong_vong = loi_vong = 0
        with ThreadPoolExecutor(max_workers=cung_luc) as ex:
            viec = {ex.submit(render_mot, k, kho): k for k in kh}
            for f in as_completed(viec):
                try:
                    d = f.result()
                    xong_vong += 1
                    ghi_manifest(kho)          # xong clip nào vào manifest clip đó
                    _in(f"  ✓ [{xong_vong + loi_vong}/{len(kh)}] {d['file']} · {d['giay']:.0f}s · {d['mb']} MB "
                        f"· {d['mat_giay']}s")
                except Exception as e:     # noqa: BLE001 — một clip hỏng không làm chết cả loạt
                    loi_vong += 1
                    _in(f"  ✗ [{xong_vong + loi_vong}/{len(kh)}] {e}")
        xong += xong_vong
        loi += loi_vong
        if xong_vong == 0:
            # Cả vòng hỏng = lỗi CHUNG (hết ổ đĩa, mất ffmpeg…): chạy tiếp chỉ đẻ thêm
            # vài chục lượt hỏng y hệt, mà người dùng thì đang ngủ không ai thấy.
            _in(f"✗ Vòng {v} hỏng toàn bộ — DỪNG, không chạy các vòng còn lại. Xem lỗi ở trên.")
            break

    m = ghi_manifest(kho)
    _in(f"\n✓ Xong {xong} clip" + (f", {loi} lỗi" if loi else "") + f" · mất {(time.time() - t_dau) / 60:.1f} phút")
    _in(f"  Kho: {m['so_clip']} clip · {m['tong_giay'] / 60:.1f} phút không trùng → {kho / 'manifest.json'}")
    return 1 if loi and not xong else 0


if __name__ == "__main__":
    raise SystemExit(main())
