@echo off
echo ========================================
echo  Lotte Chemical AI Chatbot Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo ✅ Python found
python --version

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available
    echo Please reinstall Python with pip included
    pause
    exit /b 1
)

echo ✅ pip found
echo.

REM Create virtual environment
echo 📦 Creating virtual environment...
python -m venv chatbot_env
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo ✅ Virtual environment created

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call chatbot_env\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo ✅ Dependencies installed

REM Create required directories
echo 📁 Creating required directories...
if not exist "uploads" mkdir uploads
if not exist "logs" mkdir logs
if not exist "cache" mkdir cache
if not exist "static" mkdir static

echo ✅ Directories created

REM Check if Ollama is installed
echo 🤖 Checking Ollama installation...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  WARNING: Ollama is not installed
    echo Please install Ollama from https://ollama.ai
    echo After installation, run: ollama pull llama2
    echo.
) else (
    echo ✅ Ollama found
    ollama --version
    echo.
    echo 📥 Downloading required AI models...
    echo This may take several minutes...
    ollama pull llama2
    if errorlevel 1 (
        echo ⚠️  Warning: Failed to download llama2 model
        echo You can download it later with: ollama pull llama2
    ) else (
        echo ✅ llama2 model downloaded
    )
)

echo.
echo ========================================
echo  🎉 Setup Complete!
echo ========================================
echo.
echo To start the chatbot:
echo 1. Make sure Ollama is running: ollama serve
echo 2. Run: start_chatbot.bat
echo.
echo The chatbot will be available at: http://localhost:8002
echo.
pause