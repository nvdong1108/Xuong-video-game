#!/bin/bash
# Bấm đúp để chạy trên macOS (Apple Silicon M1/M2/M3 hoặc Intel).
# Lần đầu cần Internet: tự tải uv + Python + thư viện vào .runtime/ (~200 MB).
# Không cài gì vào máy, xoá thư mục là sạch.
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"

# Bỏ cờ "tải từ Internet" của macOS cho cả thư mục, kẻo Gatekeeper chặn từng file.
xattr -dr com.apple.quarantine "$HERE" 2>/dev/null

export UV_UNMANAGED_INSTALL="$HERE/.runtime/uv"
export UV_PYTHON_INSTALL_DIR="$HERE/.runtime/python"
export UV_CACHE_DIR="$HERE/.runtime/cache"
UV="$HERE/.runtime/uv/uv"

if [ ! -x "$UV" ]; then
    echo "Lần đầu chạy: đang tải uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [ ! -x "$UV" ]; then
    echo
    echo "Không tải được uv. Kiểm tra kết nối Internet rồi chạy lại."
    read -r -p "Nhấn Enter để đóng..."
    exit 1
fi

echo "Đang mở giao diện (lần đầu mất vài phút để tải Python + thư viện)..."
"$UV" run --no-project --managed-python --python 3.12 --with-requirements requirements.txt app.py "$@"
read -r -p "Nhấn Enter để đóng..."
