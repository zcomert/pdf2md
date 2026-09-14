# Faz 13 — Masaüstü Grafik Kullanıcı Arayüzü

**İlgili bölümler:** §41
**Önkoşul:** Faz 12 (batch işlemcisinin olay arayüzü, iptal/duraklatma tokenı ve preflight sonuç nesneleri hazır)
**Tahmini büyüklük:** Orta–Büyük

## Amaç

Terminal kullanmadan klasör, prompt ve mod seçip işlemi başlatabilen, ilerlemeyi ve hataları anlaşılır gösteren, sonuç dosyalarını açabilen yerel bir masaüstü arayüzü sunmak. GUI, CLI ile **aynı çekirdeği** kullanır; iş mantığı tekrar yazılmaz.

## Teknoloji Kararı — verildi

**tkinter + ttk.** Python ile gelir, ek bağımlılık gerektirmez (§34 "global paket yok" ilkesi), `requirements.txt` değişmedi. Görünüm sade; Windows'ta "Segoe UI" (Türkçe glifli) yazı tipi. PySide6 (~200 MB, LGPL) gerekmedi.

## Modüller

```text
src/runner.py              # çekirdek: RunOptions → RunResult (CLI ve GUI ortak)
src/cli.py                 # argparse → RunOptions, tqdm olayları (ince sarmalayıcı)
src/gui/
├── __init__.py
├── app.py                 # ana pencere, düzen, olay işleme, kapatma
├── worker.py              # arka plan iş parçacığı, olay kuyruğu köprüsü
├── form.py                # doğrulama, RunOptions eşlemesi, ilerleme/kalan süre (tkinter'sız)
├── settings_store.py      # kullanıcı ayarları
├── widgets.py             # kontroller, ilerleme, hata/uyarı, sonuçlar, günlük panelleri
└── strings_tr.py          # arayüz metinleri
process_papers_gui.py      # giriş noktası
```

**Karar (modül):** Doğrulama ve ilerleme hesabı `form.py`'ye ayrıldı; tkinter içermediği için birim testleriyle doğrulanır.

## Görevler

### 1. Çekirdek hazırlığı (GUI'den bağımsız refactor)

- [x] `runner.run(options: RunOptions, events, cancel_token, console) -> RunResult` — `cli.main()` artık argümanları `RunOptions`'a çevirip bunu çağıran ince bir sarmalayıcı; argparse bağımlılığı yok. Kullanıcıya gösterilen kısa satırlar `console(metin, hata_mı)` geri çağrısıyla (CLI: stdout/stderr, GUI: Günlük paneli)
- [x] `RunResult`: çıkış kodu, çıktı klasörü, log yolu, özet, başlangıç kontrolleri, hata + öneri, iptal/durdurma, koleksiyon yolu, belge sonuçları (yol, durum, çıktı, hata), plan satırları
- [x] Başlangıç kontrolleri `events.on_checks(results)` ile bildirilir; hata olsa da `RunResult.checks` dolu
- [x] Olaylar: `on_checks`, `on_document_failed(yol, aşama, hata_türü, mesaj)`, `on_document_warnings(yol, aşama, uyarılar)`, `on_collection_output(yol)` (mevcut `on_run_start`, `on_document_start`, `on_stage`, `on_document_end`, `on_run_end` korundu)
  - Karar: faz planındaki `on_progress(done, total, …)` yerine ilerleme arayüzde mevcut olaylardan hesaplanır (`ProgressTracker`); çekirdeğe arayüze özgü hesap eklenmedi
- [x] `CancelToken.pause()/resume()` belge ve aşama sınırlarında bekler (Faz 04); model çağrısı ortasında kesilmez
- [x] Konsol log işleyicisi `console_logging=False` veya `sys.stderr is None` (pythonw) ise eklenmez
- [x] Tüm CLI testleri refactor sonrası değişmeden yeşil (testlerin yama noktası `src.cli.create_model_backend` → `src.runner.create_model_backend`)

### 2. Ana ekran (§41.1)

- [x] Giriş alanı + "Klasör seç…" ve "Tek PDF seç…" (tek PDF seçilince kapsam "Tek PDF" olur)
- [x] Çıktı alanı + "Seç…"; boşken varsayılan `<giriş>_output` gri ipucu olarak
- [x] **Kapsam:** Otomatik (prompta göre) → `auto`; Her PDF ayrı → `document`; Tek PDF → giriş dosyası, `document`; Seçili grup → keşfedilen PDF'ler çoklu seçim listesiyle, seçim `--include` desenlerine (göreli yol) çevrilir, `collection`; Tüm koleksiyon → `collection`. Grup listesi "Alt klasörleri tara" değişince yenilenir
- [x] Çok satırlı prompt; "Boş bırakılırsa her PDF'in tam Markdown dönüşümü yapılır" ipucu; son 10 istek açılır listesi
- [x] Mod: FAST / BALANCED / FULL radyo düğmeleri, seçilenin kısa açıklaması
- [x] "Alt klasörleri tara", "Başarısızları yeniden dene", "Tamamlananları atla" (işaretsizse `force`)
- [x] **Başlat**, **Planı göster** (`--plan-only`), **Duraklat/Devam**, **İptal**; durum satırı

### 3. Doğrulama (§41.3)

- [x] Başlatmadan önce: giriş boş/yok; tek PDF kapsamında `.pdf` dosya; grup/koleksiyon kapsamında klasör; çıktı giriş klasörü içinde veya dosya; grupta en az bir seçim; grup/koleksiyonda prompt zorunlu (varsayılan prompt karşılaştırılamaz)
- [x] Grup seçiminde, seçilmeyen ama aynı adlı başka PDF'in de desenle eşleşeceği durum uyarılır (üst klasördeki `a.pdf` deseni alt klasördeki `a.pdf`'i de kapsar)
- [x] Hatalı alan kırmızı çerçeve + altında açıklama; ilk hatalı alana odak; hata yokken etiket yer kaplamaz
- [x] Başlangıç kontrolleri ayrı sekmede: kontrol, ✓/⚠/✗, mesaj; ilk sorunlu satır seçili, çözüm önerisi metni ve **"Komutu kopyala"** (önerideki `ollama pull …` / `` `ollama serve` `` komutu panoya) (§41.4 kriter 5)

### 4. İşlem izleme (§41.2)

- [x] Sayaçlar: toplam, tamamlanan, devam eden, uyarılı, başarısız, atlanan
- [x] Aktif PDF, aşama (Türkçe etiketler: Ayrıştırma, Görsel model, Bilgi çıkarımı, Doğrulama, Yazma, Envanter…), ilerleme çubuğu ve yüzde
- [x] Geçen süre ve tahmini kalan süre (işlenen, atlanmayan belgelerin ortalaması × kalan; aktif belgede geçen süre düşülür)
- [x] Hata/uyarı paneli: PDF, aşama, tür (`Hata: corrupt_pdf`, `Uyarı: vision_failed`), mesaj; hatalar kırmızı; satır seçilince ayrıntı
- [x] "Log dosyasını aç" ve "Log klasörünü aç" (`os.startfile` / `open` / `xdg-open`)
- [x] Günlük sekmesi: çekirdeğin konsol satırları (keşif, sonuç özeti, çıktı ve log yolu)

### 5. Arka plan yürütme

- [x] Çekirdek ayrı `threading.Thread`'de; arayüz iş parçacığı hiç beklemez (§41.3)
- [x] Olaylar `queue.Queue` ile aktarılır; `after(100, poll)` ile tüketilir; beklenmeyen istisna `crashed` olayıyla arayüze gelir
- [x] Paralel ayrıştırma havuzu (spawn) iş parçacığından başlatıldığında çalışıyor (GUI testleri varsayılan `cpu_workers=4` ile); `process_papers_gui.py` `multiprocessing.freeze_support()` ve `__main__` korumalı
- [x] Sinyal işleyici yalnızca ana iş parçacığında kurulur (GUI worker'ında atlanır)
- [x] Kilit çakışması (başka çalıştırma aynı çıktı klasöründe) → "Çıktı klasörü kullanımda" diyaloğu

### 6. Sonuçlar (§41.3)

- [x] Sonuç listesi (PDF → durum → çıktı yolu veya hata); çift tık / Enter / "Markdown'ı aç"
- [x] Koleksiyon çalıştırmasında koleksiyon dosyası listenin üstünde ayrı ve kalın satırda + "Koleksiyon Markdown'ını aç"; koleksiyon yoksa bu satır gizli (§41.4 kriter 3)
- [x] "Çıktı klasörünü aç", "papers_summary.csv aç"

### 7. Kapatma ve güvenli durdurma

- [x] İşlem sürerken kapatma → "Güvenli durdurup kapatmak ister misiniz?" (Evet: durdur ve kapat, Hayır: devam)
- [x] Güvenli durdurma: iptal tokenı (duraklatılmışsa uyanır) → aşama sınırında durulur → state kaydı → kilit bırakılır → ayarlar kaydedilir → pencere kapanır
- [x] Sonraki açılışta ayarlar yüklenir, Başlat → resume: tamamlananlar `skipped`, başarısızlar denenmez, kalanlar işlenir (§41.4 kriter 4)

### 8. Kullanıcı ayarları

- [x] Son giriş/çıktı klasörü, kapsam, mod, seçenekler, son 10 prompt; grup seçimi oturuma özgüdür, saklanmaz
- [x] Konum: Windows `%APPDATA%\pdf2md\gui_settings.json`, diğerleri `$XDG_CONFIG_HOME` veya `~/.config/pdf2md/`
- [x] Atomik yazım; bozuk JSON veya yanlış türde değer → varsayılanlar; PDF içeriği, model çıktısı, log **saklanmaz**
- [x] Telemetri / ağ çağrısı yok (tek ağ erişimi çekirdeğin yerel Ollama bağlantısı)

### 9. Erişilebilirlik ve yerelleştirme

- [x] Tüm kontroller sekme sırasıyla klavyeden erişilebilir; `Enter` = Başlat (prompt alanı ve listelerde değil), `Esc` = İptal onayı
- [x] `Alt+` erişimleri: B Başlat, P Planı göster, D Duraklat, İ İptal, G Giriş, Ç Çıktı; etiketlerde altı çizili harfler
- [x] Türkçe karakterler: yollar, prompt ve arayüz metinleri (`Yorgunluk Çalışmaları İğüşöç` klasörüyle test)
- [x] Yüksek DPI: `SetProcessDpiAwareness(1)` (giriş noktasında)
- [x] Eksik Python paketi: `pythonw` altında konsol olmadığı için mesaj ve kurulum komutu pencerede gösterilir

## Test Ortamında Bulunan Sorunlar

- **Tk başlatma kararsızlığı (yalnızca testte):** Aynı pytest oturumunda art arda pencere açılırken Tcl ara sıra kendi kütüphane dosyalarını okuyamadı ("Can't find a usable init.tcl"). Denenen ve **işe yaramayan** açıklamalar: iş parçacığında çöp toplama, süreç havuzu (`cpu_workers=1` ile de oldu), süreç içi OCR, `TCL_LIBRARY` sabitleme. Yalıtılmış denemelerde (100 açılış, çalıştırıcı + OCR ardından açılış) hiç yeniden üretilemedi; `pytest -s` ile 8/8 hatasız. Sonuç: pytest'in dosya tanıtıcısı düzeyindeki çıktı yakalamasıyla etkileşim. Uygulama tek pencere açtığından etkilenmez; test fabrikası Tk oluşturmayı 5 kez dener (8 ardışık çalıştırmada atlama yok)
- **Windows `\\?\` öneki (çekirdek hatası):** Tüm paket çalışırken bir CLI testi `ValueError: Yol çıktı klasörünün dışında: \\?\C:\…\_cache\…` ile düştü. `Path.resolve()` klasör o anda başka süreç tarafından değiştirilirken uzun yol önekini bırakabiliyor (paralel ayrıştırma worker'ı `_cache` oluştururken). `paths.normalize` öneki kaldırır; test eklendi

## Görsel Kontrol (gerçek modellerle)

`tests\fixtures`'tan 4 PDF (biri bozuk, biri taranmış) `Makaleler\Yorgunluk Çalışmaları` klasörüne kopyalanıp pencere görünür açıldı, BALANCED ile başlatıldı (`gemma4:latest`, `minicpm-v4.5:8b`, Tesseract). Pencere görüntüleri `PrintWindow` ile alındı ve incelendi:

- İlerleme: `Toplam 4, Tamamlanan 1, Devam eden 1, Başarısız 1`, aktif PDF, aşama "Envanter", %50, geçen/kalan süre
- Hatalar ve uyarılar: `corrupt.pdf · Ayrıştırma · Hata: corrupt_pdf · PDF açılamadı…` (kırmızı)
- Sonuçlar: 3 `.md` yolu + başarısız belge hatası; "Çıktı klasörünü aç", "papers_summary.csv aç" etkin
- Başlangıç kontrolleri: Python, sanal ortam, paketler, giriş/çıktı, disk, Tesseract 5.4.0, Ollama (3 model), metin ve görsel model digest'leri, GPU RTX 4500 Ada — hepsi ✓
- Durum satırı: "Bitti: 3 tamamlandı, 1 başarısız, 0 atlandı."
- Görülüp düzeltilenler: ilk yerleşimde boş hata etiketleri yer kaplayıp log düğmelerini kesiyordu; koleksiyonsuz çalıştırmada pasif koleksiyon düğmesi görünüyordu

## Testler

- [x] `test_gui.py` (17):
  - Form doğrulama kuralları, grup seçiminde ad çakışması, `RunOptions` eşlemesi, ilerleme sayaçları ve kalan süre (sahte saat), süre biçimi, çözüm komutu ayıklama
  - Ayar deposu: gidiş-dönüş, grup seçimi saklanmaz, bozuk JSON ve yanlış türler → varsayılanlar, saklanan anahtarlar yalnızca form/son promptlar
  - Worker: olayların kuyruğa sırayla aktarılması, iptalin tokena iletilmesi, çökme bildirimi
  - **Pencereyle kabul senaryoları** (gerçek `MainWindow`, gerçek çekirdek, sahte model arka ucu):
    1. Klasör + mod seçip başlatma; sayaçlar; bozuk PDF hatasının panelde görünmesi; başlangıç kontrolleri; sonuçta `.md` yolu seçilip açma düğmesinin etkinleşmesi; CSV düğmesi; günlükte sonuç özeti (kriter 1–3)
    2. Geçersiz form (koleksiyon + boş prompt) → başlatılmaz, alan hatası
    3. İşlem sürerken kapatma → onay → güvenli durdurma → pencere kapanır, kilit bırakılır → aynı ayarlarla yeni pencere → tamamlananlar atlanır, başarısızlar denenmez, kalanlar işlenir (kriter 4)
    4. Ollama kapalı → çıkış 2, "Ollama ✗", çözüm önerisi, panoya `ollama serve`; metin modeli eksik → panoya `ollama pull gemma4:latest` (kriter 5)
    5. Kilit çakışması diyaloğu
    6. Türkçe karakterli giriş ve çıktı klasörü, duraklat/devam
    7. Planı göster (çıktı klasörü oluşmaz)
    8. Seçili grup koleksiyonu → koleksiyon dosyası ayrı gösterilir ve açılabilir (kriter 3)
- [x] `test_paths.py`: `\\?\` ve `\\?\UNC\` önek temizliği
- [x] Tüm CLI testleri refactor sonrası değişmeden yeşil

## Tamamlanma Kriterleri

- [ ] §41.4'teki 5 kabul kriteri **elle** doğrulanmış — elle tıklayarak yapılmadı. Beş kriterin her biri gerçek pencere ve çekirdekle otomatik senaryo olarak test ediliyor; kriter 1–3 ayrıca gerçek modellerle görünür çalıştırmanın ekran görüntüleriyle incelendi. Dosya seçme diyalogları ve "aç" düğmelerinin varsayılan uygulamayı başlatması yalnızca elle denenebilir
- [ ] GUI uzun batch sırasında donmuyor (pencere taşıma/yeniden boyutlandırma akıcı) — mimari olarak çekirdek ayrı iş parçacığında ve arayüz 100 ms'de bir kuyruğu okuyor; uzun (dakikalarca) gerçek batch'te elle taşıma/boyutlandırma denenmedi
- [x] `pytest` yeşil — 563 sahte arka uçla + 10 `requires_ollama`

**Çalıştırma:** `.venv\Scripts\pythonw.exe process_papers_gui.py` (konsolsuz) veya `.venv\Scripts\python.exe process_papers_gui.py`
