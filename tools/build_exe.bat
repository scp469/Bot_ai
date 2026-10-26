@echo off
chcp 65001 > nul
echo ========================================================
echo  CHAOS ZERO NIGHTMARE AI BOT — BIÊN DỊCH FILE EXE
echo ========================================================
cd /d "%~dp0\.."
python tools\build_exe.py
pause
