@echo off
REM CopyDesk Web Application Launcher for Windows
REM This script sets up the environment and starts the Flask application

echo Starting CopyDesk Web Application...
echo ==================================

REM Check if Poetry is installed
where poetry >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: Poetry is not installed. Please install it first:
    echo   Visit: https://python-poetry.org/docs/#installation
    pause
    exit /b 1
)

REM Check for API keys
if "%OPENAI_API_KEY%"=="" if "%GOOGLE_API_KEY%"=="" (
    echo Warning: No API keys found
    echo   Please set either OPENAI_API_KEY or GOOGLE_API_KEY environment variable
    echo   Example: set OPENAI_API_KEY=your-key-here
    echo.
    set /p continue="Continue anyway? (y/N): "
    if /i not "%continue%"=="y" exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
poetry install

REM Start the web application
echo Starting web server...
echo   Open your browser to: http://localhost:5000
echo   Press Ctrl+C to stop
echo ==================================

REM Run the Flask app with Poetry
poetry run python app.py