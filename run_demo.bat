@echo off
chcp 65001 >nul
echo ==============================================================================
echo Khoi chay ParrotGo Demo CLI (Tong dai Voicebot Toan quoc)
echo ==============================================================================

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m src.cli.runner --debug %*
) else (
    py -m src.cli.runner --debug %*
)

pause
