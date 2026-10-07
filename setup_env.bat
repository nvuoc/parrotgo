@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo ParrotGo - Automated Environment Setup Script (Windows CMD)
echo ==============================================================================

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PY_CMD=py
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set PY_CMD=python
    ) else (
        echo [ERROR] Khong tim thay Python tren he thong. Vui long cai dat Python ^>= 3.10.
        exit /b 1
    )
)

echo.
echo [1/5] Kiem tra moi truong ao (.venv)...
if not exist ".venv" (
    echo Dang tao moi truong ao .venv...
    %PY_CMD% -m venv .venv
) else (
    echo Moi truong ao .venv da ton tai san.
)

set VENV_PYTHON=.venv\Scripts\python.exe
set VENV_PIP=.venv\Scripts\pip.exe

echo.
echo [2/5] Cap nhat pip...
%VENV_PYTHON% -m pip install --upgrade pip setuptools wheel --quiet

echo.
echo [3/5] Cai dat dependencies tu requirements.txt...
%VENV_PIP% install -r requirements.txt
%VENV_PIP% install -e . --no-deps

echo.
echo [4/5] Kiem tra file .env...
if not exist ".env" (
    echo Sao chep .env tu .env.example...
    copy .env.example .env
)

echo.
echo [5/5] Kiem tra smoke test...
%VENV_PYTHON% -c "import chromadb, rapidfuzz, langgraph, pydantic, rich, httpx, zoneinfo; print('>> Tat ca thu vien cot loi da nap thanh cong!')"
%VENV_PYTHON% -m pytest -q

echo.
echo ==============================================================================
echo THIET LAP MOI TRUONG PARROTGO THANH CONG!
echo ==============================================================================
echo De kich hoat moi truong ao:
echo    call .venv\Scripts\activate.bat
echo.
echo De chay CLI:
echo    python -m src.cli.runner --phone 0988888888 --name "Khach Hang" --city "Ha Noi"
echo.
