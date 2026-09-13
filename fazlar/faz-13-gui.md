# Faz 13 — Masaüstü Grafik Kullanıcı Arayüzü

**İlgili bölümler:** §41
**Önkoşul:** Faz 12 (batch işlemcisinin olay arayüzü, iptal/duraklatma tokenı ve preflight sonuç nesneleri hazır)
**Tahmini büyüklük:** Orta–Büyük

## Amaç

Terminal kullanmadan klasör, prompt ve mod seçip işlemi başlatabilen, ilerlemeyi ve hataları anlaşılır gösteren, sonuç dosyalarını açabilen yerel bir masaüstü arayüzü sunmak. GUI, CLI ile **aynı çekirdeği** kullanır; iş mantığı tekrar yazılmaz.

## Teknoloji Kararı

| Seçenek | Artı | Eksi |
|---|---|---|
| **tkinter + ttk** (önerilen) | Python ile gelir, ek bağımlılık yok, §34 "global paket yok" ilkesine en uygun | Görünüm sade |
| PySide6 | Modern görünüm, zengin bileşenler | ~200 MB bağımlılık, LGPL |

Karar verildikten sonra `requirements.txt` (PySide6 seçilirse) ve README güncellenir. Aşağıdaki görevler teknolojiden bağımsızdır.

## Modüller

```text
src/gui/
├── __init__.py
├── app.py              # ana pencere, düzen
├── worker.py           # arka plan iş parçacığı, olay köprüsü
├── settings_store.py   # kullanıcı ayarları
├── widgets.py          # ilerleme paneli, hata listesi
└── strings_tr.py       # arayüz metinleri
process_papers_gui.py   # giriş noktası
```

## Görevler

### 1. Çekirdek hazırlığı (GUI'den bağımsız refactor)

- [ ] `run_batch(options: RunOptions, events, cancel_token) -> RunResult` — CLI `main()` bunun etrafında ince bir sarmalayıcı olur. `argparse` nesnesine bağımlılık olmamalı
- [ ] `run_preflight(options) -> list[CheckResult]` ayrı çağrılabilir
- [ ] Olaylara eklenecekler: `on_progress(done, total, current_doc, stage, percent)`, `on_warning(rel_path, stage, message)`, `on_error(rel_path, stage, message)`, `on_collection_output(path)`
- [ ] `CancelToken.pause()` / `resume()`: belge ve aşama sınırlarında bekler (model çağrısı ortasında kesilmez)

### 2. Ana ekran (§41.1)

- [ ] Giriş klasörü alanı + "Gözat" (klasör seçme); ayrıca "Tek PDF seç" düğmesi
- [ ] Çıktı klasörü alanı (isteğe bağlı; boşsa varsayılan `<giriş>_output` gri ipucu olarak gösterilir)
- [ ] **Kapsam:** `Tek PDF` / `Seçili grup` / `Tüm koleksiyon`
  - Tek PDF → giriş dosyası, `scope=document`
  - Seçili grup → keşfedilen PDF listesi onay kutularıyla; seçim `--include` glob'larına çevrilir, `scope=collection`
  - Tüm koleksiyon → `scope=collection`
  - Ek seçenek: "Otomatik (prompta göre)" → `scope=auto`, "Her PDF ayrı" → `document` (§21.1 ile uyum için)
- [ ] Çok satırlı prompt alanı; boşken "Boş bırakılırsa tam Markdown dönüşümü yapılır" ipucu
- [ ] Mod seçimi: FAST / BALANCED / FULL (radyo; kısa açıklamalarla)
- [ ] Onay kutuları: "Alt klasörleri tara", "Başarısızları yeniden dene", "Tamamlananları atla" (işaretsizse `force`)
- [ ] Düğmeler: **Başlat**, **Duraklat/Devam**, **İptal**, ayrıca "Planı göster" (`--plan-only` karşılığı)

### 3. Doğrulama (§41.3)

- [ ] Başlatmadan önce: giriş yolu var mı, çıktı giriş içinde mi, tek PDF modunda dosya `.pdf` mi, grup modunda en az bir seçim var mı
- [ ] Hatalı alan kırmızı çerçeve + altında açıklama; ilk hatalı alana odak
- [ ] Preflight sonuçları ayrı panelde: Ollama bağlantısı, metin/görsel model, Tesseract, GPU — her biri ✓ / ⚠ / ✗ ve **kopyalanabilir çözüm komutu** (`ollama pull minicpm-v4.5:8b`) (§41.4 kriter 5)

### 4. İşlem izleme (§41.2)

- [ ] Sayaçlar: toplam, tamamlanan, devam eden, uyarılı, başarısız, atlanan
- [ ] Aktif PDF adı, mevcut aşama (`parse`, `ocr`, `vision`, `llm`, `validation`, `write` → Türkçe etiketler), ilerleme çubuğu (%)
- [ ] Geçen süre ve tahmini kalan süre (tamamlanan belgelerin ortalama süresi × kalan; atlananlar hariç)
- [ ] Hata/uyarı paneli: tablo (PDF adı, aşama, mesaj), satır seçilince ayrıntı
- [ ] "Log dosyasını aç" ve "Log klasörünü aç" (`os.startfile` Windows, `xdg-open`/`open` diğerleri)

### 5. Arka plan yürütme

- [ ] `run_batch` ayrı `threading.Thread`'de; UI thread'i asla bloklanmaz (§41.3)
- [ ] Olaylar `queue.Queue` üzerinden UI thread'ine aktarılır; tkinter'da `after(100, poll)` ile tüketilir
- [ ] `ProcessPoolExecutor` iş parçacığından başlatıldığında Windows `spawn` sorunları test edilir; `process_papers_gui.py` içinde `multiprocessing.freeze_support()` ve `__main__` koruması
- [ ] Kilit çakışması (başka CLI çalışıyor) → anlaşılır diyalog

### 6. Sonuçlar (§41.3)

- [ ] Tamamlanınca: sonuç listesi (belge → `A.md` yolu) + "Markdown'ı aç" ve "Çıktı klasörünü aç"
- [ ] Koleksiyon çalıştırmasında üretilen koleksiyon dosyası ayrı ve belirgin gösterilir (§41.4 kriter 3)
- [ ] `papers_summary.csv`'yi açma düğmesi

### 7. Kapatma ve güvenli durdurma

- [ ] İşlem sürerken pencere kapatılırsa diyalog: "Güvenli durdur ve kapat" / "Çalışmaya devam et"
- [ ] Güvenli durdurma: iptal tokenı → mevcut aşama sınırında durur → state kaydı → kilit bırakılır → pencere kapanır
- [ ] Sonraki açılışta aynı ayarlarla Başlat → resume (§41.4 kriter 4; çekirdekteki Faz 10 mantığı)

### 8. Kullanıcı ayarları

- [ ] Son kullanılan giriş/çıktı klasörü, mod, seçenekler, son prompt(lar)
- [ ] Konum: Windows `%APPDATA%\pdf2md\gui_settings.json`, diğerleri `~/.config/pdf2md/`
- [ ] Atomik yazım; PDF içeriği veya model çıktısı **saklanmaz**
- [ ] Hiçbir telemetri/ağ çağrısı yok (§41.3)

### 9. Erişilebilirlik ve yerelleştirme

- [ ] Tüm kontrollere klavye ile ulaşılabilir; sekme sırası mantıklı; `Enter` = Başlat, `Esc` = İptal onayı
- [ ] Kısayollar: `Alt+` harf erişimleri (`&Başlat`)
- [ ] Türkçe karakterler: yollar ve prompt alanında `ığüşöçİĞÜŞÖÇ` test edilir; font seçimi Türkçe glif destekli
- [ ] Yüksek DPI ölçekleme (Windows: `ctypes.windll.shcore.SetProcessDpiAwareness(1)`)

## Testler

- Çekirdek refactor: CLI testlerinin tamamı hâlâ yeşil
- `worker.py` birim testi: sahte `run_batch` olaylarının kuyruğa doğru aktarılması, iptalin iletilmesi
- Ayar deposu: bozuk JSON → varsayılanlarla açılış
- Elle kabul senaryoları (§41.4):
  1. Terminal açmadan klasör + prompt + mod seçip başlatma
  2. İşlem sırasında ilerleme ve bir bozuk PDF'in hatasının panelde görünmesi
  3. Tamamlanınca `A.md` ve koleksiyon Markdown'ının GUI'den açılması
  4. Ortada kapatma → güvenli durdurma → yeniden açıp başlatınca kalanların işlenmesi, tamamlananların `skipped`
  5. Ollama kapalıyken başlatma → çözüm önerisi ve komut
  6. Türkçe karakterli klasör adı (`D:\Makaleler\Yorgunluk Çalışmaları`)

## Tamamlanma Kriterleri

- [ ] §41.4'teki 5 kabul kriteri elle doğrulanmış
- [ ] GUI uzun batch sırasında donmuyor (pencere taşıma/yeniden boyutlandırma akıcı)
- [ ] `pytest` yeşil
