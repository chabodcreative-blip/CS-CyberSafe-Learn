@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -m venv .venv
    if errorlevel 1 python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Could not create the virtual environment. Install Python 3.11+ and try again.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
pause
