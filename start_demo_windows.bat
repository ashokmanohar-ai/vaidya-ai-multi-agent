@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run setup required. See README.md.
  echo Run: py -3.12 -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\preflight.py
if errorlevel 1 (pause & exit /b 1)
.venv\Scripts\python.exe scripts\run_demo.py
pause
