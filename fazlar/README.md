# Uygulama Fazları

Bu klasör, [gereksinim-analizi.md](../gereksinim-analizi.md) belgesinin adım adım uygulanması için hazırlanmış faz planlarını içerir. Belgedeki §37 "Geliştirme Aşamaları" daha küçük ve kendi başına test edilebilir parçalara bölünmüştür.

## Genel Kurallar

- Fazlar **sırayla** uygulanır. Her faz bir öncekinin tamamlanma kriterlerini karşılamış olmasını varsayar.
- Her fazın sonunda `pytest` yeşil olmalı ve fazın "Tamamlanma Kriterleri" listesi elle kontrol edilmelidir.
- Her faz sonunda bir git commit'i atılması önerilir (örn. `faz-03: deterministik tam dönüşüm`).
- Bir fazda ileride genişletilecek bir yapı (şema, arayüz) tanımlanıyorsa, sonraki fazların ihtiyaçları baştan düşünülerek tasarlanır. İlgili notlar faz dosyalarında "İleriye dönük tasarım" başlığında yer alır.
- `§n` referansları gereksinim analizindeki bölüm numaralarıdır.

## Faz Listesi

| Faz | Dosya | Konu | Belge Aşaması | Ollama gerekir mi |
|---|---|---|---|:---:|
| 00 | [faz-00-proje-iskeleti.md](faz-00-proje-iskeleti.md) | Sanal ortam, bağımlılıklar, klasör yapısı, config, logger, CLI iskeleti | 1 | – |
| 01 | [faz-01-test-veri-seti.md](faz-01-test-veri-seti.md) | Test PDF'lerinin üretimi/toplanması, fixture altyapısı | 1 | – |
| 02 | [faz-02-kesif-state-kilit.md](faz-02-kesif-state-kilit.md) | PDF keşfi, SHA-256, state, kilit, atomik yazım, yol güvenliği, preflight (Ollama hariç) | 1 | – |
| 03 | [faz-03-pdf-ayristirma.md](faz-03-pdf-ayristirma.md) | PyMuPDF ayrıştırma, sayfa sınıflandırma, okuma sırası, başlık tespiti, `document.json`, önbellek | 1 | – |
| 04 | [faz-04-tam-donusum.md](faz-04-tam-donusum.md) | Deterministik Markdown üretimi, batch orkestrasyonu v1, uçtan uca varsayılan prompt | 1 | – |
| 05 | [faz-05-gorsel-aday-tablo-sekil.md](faz-05-gorsel-aday-tablo-sekil.md) | Tablo/formül/şekil aday tespiti, metin katmanından tablo, şekil çıkarımı, `assets/` | 2 | – |
| 06 | [faz-06-ocr-render.md](faz-06-ocr-render.md) | Tesseract OCR, metin/OCR birleştirme, render ve kırpma | 2 | – |
| 07 | [faz-07-ollama-gorsel-model.md](faz-07-ollama-gorsel-model.md) | Ollama istemci katmanı, model kuyruğu, MiniCPM entegrasyonu, çalışma modları, LaTeX doğrulama | 2 + 3 | ✓ |
| 08 | [faz-08-prompt-planlayici.md](faz-08-prompt-planlayici.md) | Prompt kaynakları, işleme planı, plan hash, `--plan-only`, Ollama preflight | 3 | ✓ |
| 09 | [faz-09-llm-cikarim-dogrulama.md](faz-09-llm-cikarim-dogrulama.md) | Gemma ile çıkarım, map-reduce, çıkarım şeması, kanıt/sayı doğrulama, prompt cevabı `A.md` | 3 | ✓ |
| 10 | [faz-10-saglamlik-resume.md](faz-10-saglamlik-resume.md) | Hata politikası, batch durdurma, atlama kuralı, history, paralellik, ayrıntılı log, çıkış kodları | 4 | ✓ |
| 11 | [faz-11-envanter-csv.md](faz-11-envanter-csv.md) | `papers_summary.csv/xlsx`, künye çıkarımı, `extra_fields`, çalıştırma özetleri | 5 | ✓ |
| 12 | [faz-12-koleksiyon.md](faz-12-koleksiyon.md) | Koleksiyon kapsamı, sentez, koleksiyon state'i | 5 | ✓ |
| 13 | [faz-13-gui.md](faz-13-gui.md) | Masaüstü GUI (§41) | – | ✓ |
| 14 | [faz-14-kabul-olcum-dokumantasyon.md](faz-14-kabul-olcum-dokumantasyon.md) | Kabul testleri, doğruluk/performans ölçümü, README | – | ✓ |

## Bağımlılık Grafiği

```text
00 → 01 → 02 → 03 → 04 ──► (Aşama 1 tamam: prompt'suz uçtan uca çalışan sistem)
                    │
                    ├─► 05 → 06 → 07 ──► (Aşama 2 tamam: görsel içerik + OCR + modlar)
                    │
                    └─► 08 → 09 ──► (Aşama 3 tamam: prompt tabanlı çıkarım)
                                │
                                └─► 10 → 11 → 12 → 13 → 14
```

08, teknik olarak 05–06'dan bağımsızdır ancak 07'deki Ollama istemci katmanına ihtiyaç duyar. Bu yüzden önerilen sıra doğrusal olarak 00 → 14'tür.

## Uygulama Öncesi Karara Bağlanması Gereken Noktalar

Gereksinim belgesinde tam netleşmemiş ve ilgili fazda karar verilmesi gereken konular:

| Konu | İlgili Faz | Öneri |
|---|---|---|
| §11.2 sınıflandırma tablosu, "az metin + düşük görsel oranı" (ör. boş sayfa) durumunu kapsamıyor | 03 | `text` sınıfı + `low_text_page` uyarısı |
| §16.3 / §38.2-4 "varsayılan promptta metin LLM'i çağrılmaz" ile §22.3 "künye için her belgede kısa LLM çağrısı" çelişiyor | 11 | Künye LLM çağrısını tam dönüşümden ayrı say; yalnızca metadata+regex ile eksik kalan alan varsa ve Ollama erişilebilirse yap. Kabul kriteri 4'ü "içerik üretimi için LLM çağrılmaz" olarak yorumla. Karar belgeye işlenmeli |
| §33 `src/` düz modül yapısı paket adı içermiyor | 00 | `src/` altında `__init__.py` ile paket; `process_papers.py` kökten `from src.cli import main` |
| GUI teknolojisi belirtilmemiş | 13 | Ek bağımlılık gerektirmeyen `tkinter` (ttk). Daha modern görünüm istenirse `PySide6` |
| GUI "duraklat" düğmesi batch'in işbirlikçi duraklatma desteklemesini gerektirir | 04, 10 | Batch işlemcisine baştan `cancel`/`pause` olayları ve ilerleme callback'i eklenir |
