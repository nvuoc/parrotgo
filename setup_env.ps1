# ==============================================================================
# ParrotGo - Automated Environment Setup Script (PowerShell for Windows)
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host ">>> [1/6] Kiem tra moi truong Python..." -ForegroundColor Cyan

# Find python executable
$PythonCmd = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} else {
    Write-Error "Khong tim thay Python tren he thong. Vui long cai dat Python >= 3.10."
}

$PyVersion = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "Da tim thay Python version: $PyVersion (qua '$PythonCmd')" -ForegroundColor Green

# 2. Virtual Environment
Write-Host ""
Write-Host ">>> [2/6] Thiet lap moi truong ao (.venv)..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    Write-Host "Dang tao moi truong ao tai .venv..." -ForegroundColor Yellow
    & $PythonCmd -m venv .venv
    Write-Host "Tao moi truong ao thanh cong!" -ForegroundColor Green
} else {
    Write-Host "Moi truong ao .venv da ton tai san." -ForegroundColor Green
}

$VenvPython = ".venv\Scripts\python.exe"
$VenvPip = ".venv\Scripts\pip.exe"

# 3. Upgrade Pip & Build tools
Write-Host ""
Write-Host ">>> [3/6] Cap nhat pip va cong cu build..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip setuptools wheel --quiet

# 4. Install Dependencies
Write-Host ""
Write-Host ">>> [4/6] Cai dat dependencies tu requirements.txt..." -ForegroundColor Cyan
& $VenvPip install -r requirements.txt
& $VenvPip install -e . --no-deps

# 5. Environment Config (.env)
Write-Host ""
Write-Host ">>> [5/6] Kiem tra cau hinh .env..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Write-Host "Tao file .env tu .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Da tao .env. Vui long cap nhat API keys neu dung adapter that." -ForegroundColor Green
} else {
    Write-Host "File .env da san sang." -ForegroundColor Green
}

# 6. Smoke Test Verification
Write-Host ""
Write-Host ">>> [6/6] Kiem tra tinh toan ven (Smoke test)..." -ForegroundColor Cyan
& $VenvPython -c "import chromadb, rapidfuzz, langgraph, pydantic, rich, httpx, zoneinfo; print('>> Tat ca thu vien cot loi da duoc nap thanh cong!')"
& $VenvPython -m pytest -q

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host " THIET LAP MOI TRUONG PARROTGO THANH CONG!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "De kich hoat moi truong ao trong PowerShell:" -ForegroundColor White
Write-Host "   .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "De khoi chay CLI dam thoai:" -ForegroundColor White
Write-Host '   python -m src.cli.runner --phone 0988888888 --name "Khach Hang" --city "Ha Noi"' -ForegroundColor Yellow
Write-Host ""
