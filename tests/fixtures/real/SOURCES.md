# Gerçek Test Makaleleri

§38.1'in istediği gerçekçi test seti. Konu ekseni: yorgunluk tespiti ve ses/konuşma analizi.

Aşağıdaki bilgiler PDF'lerin kendisinden çıkarılmıştır (PyMuPDF analizi, 2026-09-13): metadata, ilk sayfa metni, lisans ifadeleri, metin bloklarının yatay konumları, tablo/şekil başlıkları, numaralı formül satırları ve sayfa başına çizim/görsel yoğunluğu. Kaynak URL'ler PDF'lerde yazan DOI'lerden oluşturulmuştur.

## Dosya Listesi

| Dosya | Tür | Kaynak URL | Lisans | SHA-256 | Referans YAML |
|---|---|---|---|---|---|
| `2025_Berardi_Voice.pdf` | tek sütun | https://doi.org/10.1038/s41598-025-10565-2 | CC BY-NC-ND 4.0 | `4d087a46bf30ae23a01f8a4c02d5c0c4486a3084f4ced0a1af1458bc70837a59` | – |
| `2024_Imran_Designing.pdf` | çift sütun | https://doi.org/10.1016/j.jsr.2024.05.015 | CC BY 4.0 | `59abe4505a4aa66033a1310ebd1fcd1d32c85bd9fe64a62cf1f1bd7774397ee2` | – |
| `2024_Lambay_Machine.pdf` | çift sütun | https://doi.org/10.1016/j.dte.2024.100004 | CC BY 4.0 | `f9295e2e5056ac89f97ea958ec77f14863657adaca607072aae3746bc81a0130` | – |
| `2024_Pokorny_VocDoc.pdf` | çift sütun (tablo/formül) | https://doi.org/10.1016/j.bspc.2023.105595 | CC BY 4.0 | `84a21be50a9b2a23646cb5800036a23333439543c9bb50a3f2ebed79aa90699d` | önerilen: `pokorny_vocdoc.yaml` |
| `2025_Goodman_Approaches.pdf` | çift sütun (uzun tablolar) | https://doi.org/10.3758/s13428-025-02620-7 | CC BY 4.0 | `3704c69980d4c057ea81c037fd9c5c7e788d91fcb2c77ce392c5609546e7da80` | – |
| `2025_Polle_Meta.pdf` | çift sütun (formül) | https://doi.org/10.21437/Interspeech.2025-2055 | PDF'de lisans yok; ISCA yayını | `e4be237d19c263fc540e117a96d5223123d939988654532403266f37642ead5b` | önerilen: `polle_meta.yaml` |
| `2025_Rahman_A.pdf` | çift sütun | https://doi.org/10.1186/s12911-025-02978-w | CC BY 4.0 | `90ee7fdeb909c61a0ee2f4b4ef23598a8bc278eb2bf718f085e4970abf2b3aa1` | – |
| `2025_Vekkot_Continuous.pdf` | çift sütun (tablo/formül yoğun) | https://doi.org/10.1109/ACCESS.2024.3524452 | CC BY-NC-ND 4.0 | `68cd2afbe67ea1023d46dbacf76e59e90950dff72250524b9df099c640d23484` | önerilen: `vekkot_continuous.yaml` |
| `2025_Shilaskar_Intelligent.pdf` | çift sütun, **metin vektör yol olarak çizilmiş** | https://doi.org/10.1109/GCON65540.2025.11173357 | © 2025 IEEE, kurumsal erişim (paylaşılamaz) | `e9a122f99a0483bdb58772f8a2745ad66c950502f05c719100cd3ece9277d592` | – |

## Künye ve Yapı Analizi

| Dosya | Başlık | Yayın | Sayfa | Tablo başlığı | Şekil başlığı | Numaralı formül (yaklaşık) | Not |
|---|---|---|---:|---:|---:|---:|---|
| `2025_Berardi_Voice.pdf` | Voice fatigue subtyping through individual modeling of vocal demand responses | Scientific Reports 15:25718 (2025) | 11 | 6 | 4 | 0 | Tek sütun, geniş sol kenar boşluğu (metin x≈156–556). `find_tables()` 7 çizgili tablo buluyor. PDF metadata'sında başlık/yazar yok |
| `2024_Imran_Designing.pdf` | Designing a practical fatigue detection system: A review on recent developments and challenges | Journal of Safety Research 90 (2024) 100–114 | 15 | 8 | 6 | 0 | Derleme makalesi. Tablolar çizgisiz (`find_tables()` 0) |
| `2024_Lambay_Machine.pdf` | Machine learning assisted human fatigue detection, monitoring, and recovery: A Review | Digital Engineering 1 (2024) 100004 | 18 | 7 | 6 | 1 | Derleme, pdfTeX. Metadata'da başlık/yazar yok, DOI yalnızca `subject` alanında |
| `2024_Pokorny_VocDoc.pdf` | VocDoc, what happened to my voice? Towards automatically capturing vocal fatigue in the wild | Biomedical Signal Processing and Control 88 (2024) 105595 | 12 | 3 | 10 | 5 | Metadata tam. 12 yazar, çok satırlı yazar listesi |
| `2025_Goodman_Approaches.pdf` | Approaches to inducing mental fatigue: A systematic review and meta-analysis of (neuro)physiologic indices | Behavior Research Methods 57:102 (2025) | 29 | 6 | 2 | 0 | Sayfalara yayılan uzun tablolar; `5 (96)` biçimli hücreler satır sonu formül numarasına benziyor (formül tespiti için yanlış pozitif testi) |
| `2025_Polle_Meta.pdf` | Meta-Learning Approaches for Speaker-Dependent Voice Fatigue Models | Interspeech 2025, pp. 2038–2042 | 5 | 3 | 3 | 4 | LaTeX, kısa ve yoğun. Metadata'da başlık/yazar yok. Satır sonu tirelemesi yoğun |
| `2025_Rahman_A.pdf` | A hybrid approach for binary and multi-class classification of voice disorders using a pre-trained model and ensemble classifiers | BMC Medical Informatics and Decision Making 25:177 (2025) | 14 | 7 | 6 | 2 | İlk sayfada başlıktan önce uzun lisans metni; DOI/URL karakterleri arasında sıfır genişlikli boşluk (U+200B) var |
| `2025_Vekkot_Continuous.pdf` | Continuous Speech-Based Fatigue Detection and Transition State Prediction for Air Traffic Controllers | IEEE Access 13 (2025) 3298–3319 | 22 | 9 | 10 | 5 | 71 gömülü görsel (yazar fotoğrafları dahil). Yazar adları üst simge numaralarıyla ayrı satırlara bölünüyor |
| `2025_Shilaskar_Intelligent.pdf` | Intelligent Driver Monitoring System for Detecting Fatigue and Distraction through Speech Analysis | 2025 IEEE Guwahati Subsection Conference (GCON) | 6 | – | – | – | "Microsoft Print To PDF" çıktısı. Sayfa başına 600–6.000 vektör çizim; okunabilen tek metin kenardaki IEEE damgası (sayfa başına 138–253 karakter) |

Tüm PDF'ler şifresiz. Hiçbirinde raster taranmış sayfa yok.

## §38.1 ile Karşılaştırma

| Gereksinim | İstenen | Mevcut | Durum |
|---|---:|---:|---|
| Metin tabanlı tek sütun | 4 | 1 (Berardi) | **3 eksik** |
| Çift sütun | 3 | 7 metin katmanlı + 1 vektör metinli | fazlasıyla karşılanıyor |
| Tablo ve formül yoğun çift sütun | ≥1 | Vekkot, Pokorny, Polle | karşılanıyor |
| Taranmış | 2 | 0 | **2 eksik** |
| Referans verisine uygun makale (≥2 tablo, ≥3 formül, ≥5 sonuç) | 3 | Pokorny, Vekkot, Polle | karşılanıyor (formül sayıları elle doğrulanmalı) |

Eksikleri kapatma seçenekleri:

- **Tek sütun:** arXiv ön baskıları (çoğu tek sütun) veya tez/rapor biçimli makaleler eklenebilir.
- **Taranmış:** gerçek tarama yoksa, lisansı türev esere izin veren (CC BY) bir makalenin birkaç sayfası 200–300 DPI görsele çevrilip metin katmanı olmadan PDF yapılabilir (§38.1 "yüksek kaliteli sentetik" seçeneği). Uygun adaylar: `2024_Pokorny_VocDoc.pdf`, `2025_Rahman_A.pdf`. CC BY-NC-ND (Berardi, Vekkot), ISCA (Polle) ve IEEE (Shilaskar) makalelerinden türev üretilmemeli.

## Paylaşım Notları

- `2025_Shilaskar_Intelligent.pdf` kurumsal abonelikle indirilmiş ve her sayfasında indiren kurumun damgası var. Lisansı yeniden dağıtıma izin vermediği için git'e **eklenmemeli**.
- `2025_Polle_Meta.pdf` PDF'inde açık lisans ifadesi yok. ISCA arşivinde ücretsiz okunabilir ama yeniden dağıtım izni belirsiz olduğundan git'e eklenmemesi önerilir.
- CC BY-NC-ND 4.0 makaleler (Berardi, Vekkot) değiştirilmeden ve ticari olmayan amaçla dağıtılabilir; depo ticari kullanılacaksa hariç tutulmalı.
- CC BY 4.0 makaleler (Imran, Lambay, Pokorny, Goodman, Rahman) atıfla dağıtılabilir.

## İşleme Hattı Açısından Dikkat Çeken Durumlar

- **Vektör yol olarak çizilmiş metin (Shilaskar):** §11.2 sınıflandırması bu sayfaları `text` sayar (karakter sayısı ≥ 100, görsel oranı ≈ 0), bu yüzden OCR veya görsel model tetiklenmez ve makale içeriği kaybolur. Faz 03/06'da "çok az metin + çok yüksek vektör çizim yoğunluğu" durumu için sayfanın render edilip OCR'a gönderilmesi gerekir.
- **Kenar damgaları:** Shilaskar'daki IEEE indirme damgası gibi dikey/kenar metinler üst/alt bilgi tespitinin dışında kalır; okuma sırasını ve künye çıkarımını bozabilir.
- **Başlıktan önce gelen metin:** Rahman'da ilk sayfa lisans paragrafıyla, Vekkot'ta tarih satırıyla başlıyor. "İlk sayfanın en büyük fontu = başlık" kuralı bunlarda doğru çalışmalı; ilk satır kuralı çalışmaz.
- **Metadata'sı eksik PDF'ler:** Berardi, Lambay, Polle, Rahman'da metadata başlık/yazar içermiyor; künye çıkarımı (§22.3) ilk sayfa metnine ve LLM adımına düşecek.
- **Sıfır genişlikli karakterler:** Rahman'daki URL/DOI'lerde U+200B var; DOI regex'i ve metin normalizasyonu bunları temizlemeli.
- **Çizgisiz tablolar:** Elsevier ve IEEE makalelerinde `find_tables()` tablo bulamıyor; bunlar BALANCED modda görsel modele gidecek adaylardır.
