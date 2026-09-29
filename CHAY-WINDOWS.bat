@echo off
rem Bam dup de chay. Lan dau can Internet: tu tai uv + Python + thu vien vao .runtime\ (~200 MB).
rem Khong cai gi vao may, xoa thu muc la sach.
chcp 65001 >nul
cd /d "%~dp0"

set "RT=%~dp0.runtime"
set "UV_UNMANAGED_INSTALL=%RT%\uv"
set "UV_PYTHON_INSTALL_DIR=%RT%\python"
set "UV_CACHE_DIR=%RT%\cache"
set "UV=%RT%\uv\uv.exe"

if not exist "%UV%" (
    echo Lan dau chay: dang tai uv...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
if not exist "%UV%" (
    echo.
    echo Khong tai duoc uv. Kiem tra ket noi Internet roi chay lai.
    pause
    exit /b 1
)

echo Dang mo giao dien (lan dau mat vai phut de tai Python + thu vien)...
"%UV%" run --no-project --managed-python --python 3.12 --with-requirements requirements.txt app.py %*
pause
