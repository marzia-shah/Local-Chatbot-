@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    AI Document Chatbot Smart Launcher
echo ========================================
echo.

:: Function to check if port is in use
:check_port
netstat -an | find ":%1 " >nul
if %errorlevel% == 0 (
    exit /b 1
) else (
    exit /b 0
)
exit /b 0

:: Function to kill processes on specific ports
:kill_port_processes
echo Checking port %1...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":%1 "') do (
    if not "%%a"=="0" (
        echo   Killing process %%a using port %1
        taskkill /PID %%a /F >nul 2>&1
    )
)
exit /b 0

:: Function to check if Ollama is running
:check_ollama
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% == 0 (
    exit /b 0
) else (
    exit /b 1
)
exit /b 0

echo [1/4] Resolving port conflicts...
call :kill_port_processes 11434
call :kill_port_processes 8002
call :kill_port_processes 8003
call :kill_port_processes 5000

echo [2/4] Waiting for ports to be released...
timeout /t 5 >nul

echo [3/4] Starting services...

:: Check if virtual environment exists
if exist "chatbot_env\Scripts\activate.bat" (
    echo Activating chatbot_env virtual environment...
    call chatbot_env\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else (
    echo Virtual environment not found, using system Python...
)

set PYTHONIOENCODING=utf-8

:: Start Ollama in background
echo Starting Ollama service...
start /B ollama serve

:: Wait and check if Ollama started successfully
echo Waiting for Ollama to initialize...
set /a attempts=0
:wait_ollama
set /a attempts+=1
timeout /t 2 >nul
call :check_ollama
if %errorlevel% == 0 (
    echo ✓ Ollama service is running
    goto start_app
)
if %attempts% geq 10 (
    echo ⚠ Ollama service may not be available, continuing anyway...
    goto start_app
)
goto wait_ollama

:start_app
echo [4/4] Starting AI Document Chatbot...

:: Check if main.py exists
if not exist "main.py" (
    echo ❌ Error: main.py not found in current directory
    echo Please ensure you're running this script from the project root directory
    pause
    exit /b 1
)

:: Start the FastAPI application
python main.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Error starting the application
    echo Please check the error messages above
    echo.
    echo Troubleshooting tips:
    echo 1. Ensure Python is installed and in PATH
    echo 2. Install dependencies: pip install -r requirements.txt
    echo 3. Check if port 8003 is available
    echo 4. Run fix_ports_enhanced.bat if needed
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo ✓ Chatbot started successfully!
echo Access at: http://localhost:8000
echo ========================================
pause