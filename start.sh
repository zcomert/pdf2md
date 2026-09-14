#!/bin/bash
set -e

echo "[pdf2md] Başlıyor..."

# Ollama kontrol et
if ! pgrep -x "ollama" > /dev/null; then
    echo ""
    echo "[HATA] Ollama servisine ulaşılamıyor."
    echo "Çözüm: Terminal'de: ollama serve"
    echo ""
    exit 2
fi

# .venv var mı?
if [ ! -f ".venv/bin/python" ]; then
    echo ""
    echo "[HATA] Sanal ortam (.venv) bulunamadı."
    echo "Çözüm: Bu komutları çalıştırın:"
    echo "       python3 -m venv .venv"
    echo "       .venv/bin/python -m pip install -r requirements.txt"
    echo ""
    exit 2
fi

# GUI başlat
.venv/bin/python process_papers_gui.py &
if [ $? -eq 0 ]; then
    echo "[pdf2md] GUI açıldı."
    exit 0
else
    echo "[HATA] GUI başlatılamadı."
    exit 1
fi
