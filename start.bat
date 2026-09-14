@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo [pdf2md] Başlıyor...

REM Ollama kontrol et
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I /N "ollama.exe">nul
if errorlevel 1 (
    echo.
    echo [HATA] Ollama servisine ulaşılamıyor.
    echo Çözüm: Ollama uygulamasını başlatın veya
    echo         PowerShell'de: ollama serve
    echo.
    pause
    exit /b 2
)

REM .venv var mı?
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [HATA] Sanal ortam (.venv) bulunamadı.
    echo Çözüm: Bu komutları çalıştırın:
    echo         python -m venv .venv
    echo         .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 2
)

REM GUI başlat
.venv\Scripts\pythonw.exe process_papers_gui.py
if errorlevel 1 (
    echo.
    echo [HATA] GUI başlatılamadı. Log:
    .venv\Scripts\python.exe process_papers_gui.py
    pause
    exit /b 1
)

echo [pdf2md] GUI açıldı.
exit /b 0
