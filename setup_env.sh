#!/usr/bin/env bash
# ==============================================================================
# ParrotGo - Automated Environment Setup Script (Bash / Linux / macOS / WSL)
# ==============================================================================

set -e

echo -e "\n\033[1;36m>>> [1/5] Kiểm tra môi trường Python...\033[0m"
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo -e "\033[1;31mKhông tìm thấy Python. Vui lòng cài đặt Python >= 3.10.\033[0m"
        exit 1
    fi
fi

echo -e "\n\033[1;36m>>> [2/5] Thiết lập môi trường ảo (.venv)...\033[0m"
if [ ! -d ".venv" ]; then
    echo "Đang tạo môi trường ảo tại .venv..."
    $PYTHON_CMD -m venv .venv
else
    echo "Môi trường ảo .venv đã tồn tại sẵn."
fi

VENV_PYTHON=".venv/bin/python"
VENV_PIP=".venv/bin/pip"
if [ ! -f "$VENV_PYTHON" ]; then
    # Windows fallback if running under Git Bash
    VENV_PYTHON=".venv/Scripts/python.exe"
    VENV_PIP=".venv/Scripts/pip.exe"
fi

echo -e "\n\033[1;36m>>> [3/5] Cập nhật pip và cài đặt dependencies...\033[0m"
$VENV_PYTHON -m pip install --upgrade pip setuptools wheel --quiet
$VENV_PIP install -r requirements.txt
$VENV_PIP install -e . --no-deps

echo -e "\n\033[1;36m>>> [4/5] Kiểm tra cấu hình .env...\033[0m"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Đã tạo file .env từ .env.example."
fi

echo -e "\n\033[1;36m>>> [5/5] Kiểm tra smoke test...\033[0m"
$VENV_PYTHON -c "import chromadb, rapidfuzz, langgraph, pydantic, rich, httpx, zoneinfo; print('>> Tất cả thư viện cốt lõi đã nạp thành công!')"
$VENV_PYTHON -m pytest -q

echo -e "\n\033[1;32m==============================================================================\033[0m"
echo -e "\033[1;32m THIẾT LẬP MÔI TRƯỜNG PARROTGO THÀNH CÔNG!\033[0m"
echo -e "\033[1;32m==============================================================================\033[0m"
echo -e "Kích hoạt môi trường ảo:"
echo -e "   source .venv/bin/activate\n"
