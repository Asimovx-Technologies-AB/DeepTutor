@echo off
echo.
echo ================================================
echo   IndieTutor Backend - GraphRAG + Ollama
echo ================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

REM Check virtualenv
if not exist ".venv" (
    echo [1/2] Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [2/2] Installing dependencies...
    pip install -r requirements.txt -q
) else (
    call .venv\Scripts\activate.bat
)

REM Start FastAPI
echo Starting FastAPI server on http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
