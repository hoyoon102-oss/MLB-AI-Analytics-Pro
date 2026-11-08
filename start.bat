@echo off
setlocal
cd /d "%~dp0"

set "APP_PYTHON=.venv\Scripts\python.exe"
"%APP_PYTHON%" -c "import streamlit" >nul 2>&1
if errorlevel 1 set "APP_PYTHON=.venv-test\Scripts\python.exe"
"%APP_PYTHON%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo ERROR: The virtual environment Python interpreter was not found.
    echo Expected: %~dp0.venv\Scripts\python.exe
    pause
    exit /b 1
)

"%APP_PYTHON%" -m streamlit run "app.py"

echo.
echo Streamlit has stopped.
pause
endlocal
