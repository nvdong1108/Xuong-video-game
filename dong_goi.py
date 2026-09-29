#!/usr/bin/env python3
"""dong_goi.py — đóng cả thư mục thành MỘT file zip để gửi sang máy khác.

    python dong_goi.py                 # → dist/Xuong-video-game_<ngày>.zip
    python dong_goi.py --kem-output    # kèm cả video đã render trong output/
    python dong_goi.py --kem-kho       # kèm cả kho clip nền kho-nen/ (rất nặng)

Máy nhận: giải nén → bấm đúp CHAY-WINDOWS.bat hoặc CHAY-MAC.command (xem HUONG-DAN-CHAY.txt).

Vì sao không dùng "Send to → Compressed folder" của Windows: zip đó làm mất quyền
chạy (chmod +x) của CHAY-MAC.command, sang Mac bấm đúp sẽ không chạy. Ở đây ghi quyền
Unix vào từng mục zip, và ép đúng kiểu xuống dòng (.command phải LF, .bat phải CRLF).
"""
import argparse
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEN_GOC = "Xuong-video-game"

BO_THU_MUC = {".git", ".runtime", "dist", "__pycache__", ".venv", "venv", ".vscode", ".idea", ".claude"}
# Cấu hình trỏ tới đường dẫn tuyệt đối của máy này — sang máy khác là sai.
BO_FILE = {"data/ve-tranh.json", "data/kho-nen.json"}
BO_DUOI = {".pyc"}
BO_TEN = {"Thumbs.db", ".DS_Store"}
CHAY_DUOC = {".command", ".sh"}           # cần quyền +x trên Mac


def gom_file(kem_output: bool, kem_kho: bool):
    bo = set(BO_THU_MUC)
    if not kem_output:
        bo.add("output")
    if not kem_kho:
        bo.add("kho-nen")
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if any(part in bo for part in rel.parts) or not p.is_file():
            continue
        if rel.as_posix() in BO_FILE or p.suffix.lower() in BO_DUOI or p.name in BO_TEN:
            continue
        yield p, rel


def noi_dung(p: Path) -> bytes:
    data = p.read_bytes()
    if p.suffix in CHAY_DUOC:
        return data.replace(b"\r\n", b"\n")
    if p.suffix == ".bat":
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return data


def main():
    ap = argparse.ArgumentParser(description="Đóng gói thư mục thành file zip chạy được trên Windows và macOS")
    ap.add_argument("--kem-output", action="store_true", help="kèm video đã render trong output/")
    ap.add_argument("--kem-kho", action="store_true", help="kèm kho clip nền kho-nen/")
    ap.add_argument("--out", help="đường dẫn file zip (mặc định dist/Xuong-video-game_<ngày>.zip)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    out = Path(args.out) if args.out else ROOT / "dist" / f"{TEN_GOC}_{time.strftime('%Y-%m-%d')}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    so, tong = 0, 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p, rel in gom_file(args.kem_output, args.kem_kho):
            info = zipfile.ZipInfo(f"{TEN_GOC}/{rel.as_posix()}",
                                   date_time=time.localtime(max(p.stat().st_mtime, 315532800))[:6])
            info.create_system = 3                     # Unix → Mac đọc quyền bên dưới
            quyen = 0o755 if p.suffix in CHAY_DUOC else 0o644
            info.external_attr = (0o100000 | quyen) << 16
            # video/ảnh đã nén sẵn, nén lại chỉ tốn thời gian
            info.compress_type = (zipfile.ZIP_STORED if p.suffix.lower() in (".mp4", ".jpg", ".jpeg", ".png", ".webp")
                                  else zipfile.ZIP_DEFLATED)
            data = noi_dung(p)
            z.writestr(info, data)
            so += 1
            tong += len(data)
    print(f"Đã đóng gói {so} file ({tong / 1e6:.1f} MB) → {out}  [{out.stat().st_size / 1e6:.1f} MB]")


if __name__ == "__main__":
    main()
