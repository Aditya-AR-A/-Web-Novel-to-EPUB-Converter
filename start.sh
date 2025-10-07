#!/bin/bash

# Web Novel to EPUB Converter - Startup Script
# This script helps you start the application with the correct configuration

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   📚 Web Novel to EPUB Converter - Startup Script           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "   Creating virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install/upgrade dependencies
echo "📦 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found!"
    echo "   Would you like to create one? (y/n)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        cp .env.example .env
        echo "✅ Created .env file from .env.example"
        echo "   Please edit .env with your configuration"
        echo ""
        echo "   Press Enter to continue with default settings (local storage)..."
        read -r
    else
        echo "   Continuing with environment variables..."
    fi
fi

# Load .env if it exists
if [ -f ".env" ]; then
    echo "📋 Loading configuration from .env..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set default storage backend if not set
if [ -z "$STORAGE_BACKEND" ]; then
    export STORAGE_BACKEND=local
    echo "ℹ️  Using default storage backend: local"
fi

# Display current configuration
echo ""
echo "🔧 Current Configuration:"
echo "   Storage Backend: $STORAGE_BACKEND"
echo "   Database URL: ${DATABASE_URL:-sqlite:///./data/epubs.db}"
if [ "$STORAGE_BACKEND" = "local" ]; then
    echo "   Local Storage Path: ${LOCAL_STORAGE_PATH:-books}"
fi
echo ""

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p books media data

# Check if the app can load
echo "✅ Validating application..."
if python -c "from api import app; print('Application loaded successfully')" 2>/dev/null; then
    echo "✅ Application validation successful!"
else
    echo "❌ Application validation failed!"
    echo "   Please check your configuration and dependencies"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                 🚀 Starting Application...                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📡 Server will be available at:"
echo "   • Web UI: http://localhost:8000"
echo "   • API Docs: http://localhost:8000/docs"
echo "   • Health: http://localhost:8000/health"
echo ""
echo "Press CTRL+C to stop the server"
echo ""

# Start the server
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
