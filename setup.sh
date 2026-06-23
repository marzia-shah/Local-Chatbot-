#!/bin/bash

echo "========================================"
echo "  Lotte Chemical AI Chatbot Setup"
echo "========================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 is not installed"
    echo "Please install Python 3.8+ using your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  macOS: brew install python"
    echo "  CentOS/RHEL: sudo yum install python3 python3-pip"
    exit 1
fi

echo "✅ Python found"
python3 --version

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "❌ ERROR: pip3 is not available"
    echo "Please install pip3 using your package manager"
    exit 1
fi

echo "✅ pip found"
echo

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv chatbot_env
if [ $? -ne 0 ]; then
    echo "❌ ERROR: Failed to create virtual environment"
    exit 1
fi

echo "✅ Virtual environment created"

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source chatbot_env/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ ERROR: Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed"

# Create required directories
echo "📁 Creating required directories..."
mkdir -p uploads logs cache static

echo "✅ Directories created"

# Check if Ollama is installed
echo "🤖 Checking Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "⚠️  WARNING: Ollama is not installed"
    echo "Please install Ollama from https://ollama.ai"
    echo "After installation, run: ollama pull llama2"
    echo
else
    echo "✅ Ollama found"
    ollama --version
    echo
    echo "📥 Downloading required AI models..."
    echo "This may take several minutes..."
    ollama pull llama2
    if [ $? -ne 0 ]; then
        echo "⚠️  Warning: Failed to download llama2 model"
        echo "You can download it later with: ollama pull llama2"
    else
        echo "✅ llama2 model downloaded"
    fi
fi

echo
echo "========================================"
echo "  🎉 Setup Complete!"
echo "========================================"
echo
echo "To start the chatbot:"
echo "1. Make sure Ollama is running: ollama serve"
echo "2. Run: ./start_chatbot.sh"
echo
echo "The chatbot will be available at: http://localhost:8002"
echo