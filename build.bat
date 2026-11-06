@echo off
REM Builds dist\ClipStudio\ClipStudio.exe. Needs Python 3.12. Put an LGPL FFmpeg in tools\ before a public release.
cd /d "%~dp0"
if not exist .venv py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller==6.22.3
.venv\Scripts\python -m PyInstaller --noconfirm --windowed --noupx --name ClipStudio --collect-all faster_whisper --collect-all ctranslate2 --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-submodules pytchat --exclude-module tkinter --exclude-module matplotlib main.py
if exist tools\ffmpeg.exe xcopy /y /i tools dist\ClipStudio\_internal\tools
