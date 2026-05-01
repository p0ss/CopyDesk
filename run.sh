#!/bin/bash

# CopyDesk Web Application Launcher
# This script sets up the environment and starts the Flask application

echo "🚀 Starting CopyDesk Web Application..."
echo "=================================="

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
    echo "   Example: export OPENAI_API_KEY='your-key-here'"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]
    then
        exit 1
    fi
fi

# Install dependencies if needed
echo "📦 Checking dependencies..."
poetry install --quiet

# Start the web application
echo "🌐 Starting web server..."
echo "   Open your browser to: http://localhost:5000"
echo "   Press Ctrl+C to stop"
echo "=================================="

# Run the Flask app with Poetry
poetry run python app.py