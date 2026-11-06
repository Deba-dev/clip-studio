@echo off
REM Builds dist\ClipStudio\ClipStudio.exe for testing on this PC. Public releases are built by .github\workflows\release.yml.
cd /d "%~dp0"
if not exist .venv py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller==6.22.3
.venv\Scripts\python -m PyInstaller --noconfirm --windowed --noupx --name ClipStudio --icon assets\icon.ico --collect-all faster_whisper --collect-all ctranslate2 --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-submodules pytchat --exclude-module tkinter --exclude-module matplotlib main.py
