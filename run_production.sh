#!/bin/bash

# CopyDesk Production Server Launcher
# Uses gunicorn for production deployment

echo "🚀 Starting CopyDesk Production Server..."
echo "=========================================="

# Check if Poetry is installed
if ! command -v poetry &> /dev/null
then
    echo "❌ Poetry is not installed. Please install it first:"
    echo "   curl -sSL https://install.python-poetry.org | python3 -"
    exit 1
fi

# Check for API keys
if [ -z "$OPENAI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    echo "⚠️  Warning: No API keys found"
    echo "   Please set either OPENAI_API_KEY or GOOGLE_API_KEY environment variable"
    exit 1
fi

# Install dependencies including gunicorn
echo "📦 Installing dependencies..."
poetry add gunicorn --group production 2>/dev/null || poetry install

# Set production variables
export FLASK_ENV=production
export FLASK_DEBUG=false
PORT=${PORT:-8000}
WORKERS=${WORKERS:-4}

echo "🌐 Starting production server..."
echo "   URL: http://localhost:${PORT}"
echo "   Workers: ${WORKERS}"
echo "   Press Ctrl+C to stop"
echo "=========================================="

# Run with gunicorn
poetry run gunicorn \
    --worker-class eventlet \
    --workers ${WORKERS} \
    --bind 0.0.0.0:${PORT} \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    "app:app"