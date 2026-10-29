@echo off
cd /d "%~dp0"
python run_all.py
if errorlevel 1 (
  echo Checks failed. Read the error above.
  pause
  exit /b 1
)
echo All checks passed. Read CHECK_STATUS.md and project1\results\report.html
pause
