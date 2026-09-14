"""Arayüz metinleri (Türkçe)."""

APP_TITLE = "pdf2md — Akademik PDF İşleme"

SCOPES = (
    ("auto", "Otomatik (prompta göre)"),
    ("document", "Her PDF ayrı"),
    ("single", "Tek PDF"),
    ("group", "Seçili grup"),
    ("collection", "Tüm koleksiyon"),
)
MODES = (
    ("fast", "FAST", "Yalnızca taranmış sayfalar görsel modele gider; en hızlı."),
    ("balanced", "BALANCED", "Tutarsız tablolar, formüller ve başlıksız şekiller görsel modelle işlenir."),
    ("full", "FULL", "Tüm tablo, formül ve şekil adayları görsel modelle işlenir; en yavaş."),
)
STAGES = {
    "parse": "Ayrıştırma", "ocr": "OCR", "vision": "Görsel model", "assets": "Görseller", "llm": "Bilgi çıkarımı",
    "validation": "Doğrulama", "write": "Yazma", "inventory": "Envanter", "synthesis": "Koleksiyon sentezi",
}
STATUSES = {
    "completed": "Tamamlandı", "completed_with_warnings": "Uyarılı", "failed": "Başarısız", "skipped": "Atlandı",
    "pending": "Bekliyor", "processing": "İşleniyor",
}
CHECKS = {
    "python": "Python", "virtualenv": "Sanal ortam", "dependencies": "Python paketleri", "config": "Yapılandırma",
    "input": "Giriş", "output": "Çıktı klasörü", "disk": "Disk alanı", "ocr": "Tesseract OCR", "ollama": "Ollama",
    "model_text": "Metin modeli", "model_vision": "Görsel model", "gpu": "GPU", "xlsx": "Excel çıktısı",
    "collection_output": "Koleksiyon çıktısı",
}

PROMPT_HINT = "Boş bırakılırsa her PDF'in tam Markdown dönüşümü yapılır."
OUTPUT_HINT = "Boşsa: {default}"
GROUP_HINT = "İşlenecek PDF'leri seçin (Ctrl/Shift ile çoklu seçim)."

ERR_INPUT_MISSING = "Giriş klasörü veya PDF seçin."
ERR_INPUT_NOT_FOUND = "Seçilen yol bulunamadı."
ERR_SINGLE_NOT_PDF = "Tek PDF kapsamında bir .pdf dosyası seçilmelidir."
ERR_NEEDS_FOLDER = "Bu kapsam için bir klasör seçilmelidir."
ERR_OUTPUT_INSIDE = "Çıktı klasörü giriş klasörüyle aynı veya onun içinde olamaz."
ERR_OUTPUT_IS_FILE = "Çıktı yolu bir dosya; klasör seçin."
ERR_GROUP_EMPTY = "Seçili grup için en az bir PDF seçin."
ERR_GROUP_AMBIGUOUS = "Seçilen dosyalardan biriyle aynı adı taşıyan başka PDF'ler de seçime girer: {names}"
ERR_COLLECTION_PROMPT = "Koleksiyon kapsamı bir istek gerektirir; prompt alanını doldurun."

RUNNING_CLOSE_TITLE = "İşlem sürüyor"
RUNNING_CLOSE_MESSAGE = ("İşlem devam ediyor. Güvenli durdurup kapatmak ister misiniz?\n\n"
                         "Evet: mevcut aşama bitince durulur, durum kaydedilir ve pencere kapanır. Aynı ayarlarla "
                         "yeniden başlatınca kaldığı yerden devam edilir.\nHayır: çalışmaya devam edilir.")
CANCEL_TITLE = "İptal"
CANCEL_MESSAGE = "İşlem güvenli bir noktada durdurulsun mu? Yeniden başlatınca kaldığı yerden devam edilir."
LOCK_TITLE = "Çıktı klasörü kullanımda"
PREFLIGHT_TITLE = "Başlangıç kontrolleri başarısız"
PREFLIGHT_MESSAGE = "İşlem başlatılamadı:\n\n{error}\n\nAyrıntılar ve çözüm komutları 'Başlangıç kontrolleri' sekmesinde."
CRASH_TITLE = "Beklenmeyen hata"
