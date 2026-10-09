@echo off
chcp 65001 >nul
echo ==============================================================================
echo Khoi chay ParrotGo Web Interface (Thu nghiem ParrotGoLLM Voice & Chat)
echo ==============================================================================

if exist ".venv\Scripts\python.exe" (
    start http://127.0.0.1:8000
    .venv\Scripts\python.exe -m src.web.run
) else (
    start http://127.0.0.1:8000
    py -m src.web.run
)

pause
