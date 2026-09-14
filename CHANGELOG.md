# Değişiklik Günlüğü

## 1.0.0 — ilk sürüm

Yerel akademik PDF işleme, Markdown dönüştürme ve bilgi çıkarım sistemi. Gereksinim belgesi: `gereksinim-analizi.md`; uygulama kararları: `fazlar/` ve `docs/gereksinim-guncellemeleri.md`.

### Aşama 1 — Temel ayrıştırma ve tam dönüşüm (`v0.1-asama1`)

- Proje iskeleti, yapılandırma (CLI > `config.yaml` > varsayılan), başlangıç kontrolleri, günlükleme
- Keşif (SHA-256 kimliği, `--include` glob, `--recursive`), `processing_state.json`, işletim sistemi kilidi, atomik yazım
- PyMuPDF ayrıştırıcı: sayfa sınıflandırma (vektör metin tespiti dahil), üst/alt bilgi, çift sütun okuma sırası, başlık hiyerarşisi, liste, dipnot, kaynakça
- Deterministik tam Markdown dönüşümü (front matter, sayfa işaretleri, tireleme onarımı), `document.json` önbelleği

### Aşama 2 — Görsel içerik ve OCR (`v0.2-asama2`)

- Tablo (çizgili tablo + başlık güdümlü bölge), formül ve şekil adayları; `assets/` yalnızca referans verilen görseller
- Tesseract OCR (PyMuPDF), sütunlu OCR düzeni, OCR imzalı önbellek
- Ollama arka ucu (yalnızca loopback), MiniCPM-V görsel görevleri (tablo, formül, şekil, sayfa metni, sayfa düzeni), FAST/BALANCED/FULL tetikleyici tablosu, görsel sonuç önbelleği

### Aşama 3 — Prompt tabanlı çıkarım (`v0.3-asama3`)

- Alan kataloğu, prompt planlayıcı (Gemma, şemalı JSON), plan hash'i ve plan önbelleği, `--plan-only`
- Blok kimlikli bağlam, bölüm seçimi ve parçalama, şemalı çıkarım, deterministik birleştirme
- Kanıt doğrulama (sayı normalizasyonu, tablo satırı kuralı), kural tabanlı güven, `[unverified]`/`[source_not_found]` işaretleri, kaynak etiketleri, güvenlik ağı
- Prompt cevabı `A.md` (plan başlıkları, formül şablonu, `not_found`)

### Aşama 4 — Sağlamlık (`v0.4-asama4`)

- Tek merkezli hata politikası (§28), art arda yazma hatası ve disk kontrolü, `error_type`
- Paralel ayrıştırma (süreç havuzu), güvenli iptal (Ctrl+C / Ctrl+Break), kesinti + yeniden başlatma testi
- Belge başına ayrıntılı günlük

### Aşama 5 — Toplu çıktılar (`v0.5-asama5`)

- `papers_summary.csv` (BOM'lu UTF-8, isteğe bağlı XLSX), künye çıkarımı (metadata, DOI regex, doğrulanmış LLM adımı), analitik sütunlar
- Koleksiyon kapsamı: doğrulanmış çıkarımlardan makaleler arası sentez, makale kimlikli iddialar, deterministik bulgu tabloları, koleksiyon state'i ve atlama

### Masaüstü arayüzü ve kabul

- Ortak çalıştırma çekirdeği (`src/runner.py`); tkinter arayüzü (`process_papers_gui.py`): doğrulama, ilerleme ve kalan süre, hata/uyarı paneli, başlangıç kontrolleri ve kopyalanabilir çözüm komutları, sonuçları açma, güvenli kapatma ve devam
- Kabul matrisi (`tests/acceptance/`), referans veri (3 gerçek makale, taslak), doğruluk ve performans ölçüm araçları (`tools/evaluate.py`, `tools/benchmark.py`), README

### Bilinen sınırlamalar

- Tablo kanıtında metrik sütunu başlıklardan tek anlamlı belirlenemezse (ör. metrik adı birden çok sütuna eşit uyuyor) `verified` yalnızca satır düzeyindedir
- Çok düzeyli başlıklı tablolar görsel modelle her zaman yapılandırılamaz (`[table_structure_unavailable]`)
- Gerçek test setinde taranmış PDF ve yeterli tek sütunlu makale yok (§38.1)
- Referans veriler kullanıcı onayı bekliyor
