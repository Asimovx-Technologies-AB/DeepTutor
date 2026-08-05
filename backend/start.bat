@echo off
echo.
echo ================================================
echo   DeepTutor Backend - GraphRAG + Ollama
echo ================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

REM Create virtualenv if needed
if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
)

REM Activate
call .venv\Scripts\activate.bat

REM Install deps
echo [2/4] Installing dependencies...
pip install -r requirements.txt -q

REM Check Ollama
echo [3/4] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARNING] Ollama is not running!
    echo   Start it with: ollama serve
    echo   Pull a model:  ollama pull llama3.1
    echo   Pull embeddings: ollama pull nomic-embed-text
    echo.
    echo   The server will start anyway - connect Ollama before chatting.
    echo.
)

REM Start FastAPI
echo [4/4] Starting FastAPI server on http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
