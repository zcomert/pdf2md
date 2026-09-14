# Katkı Rehberi

Hata düzeltmeleri, testler, dokümantasyon ve yeni özellikler memnuniyetle karşılanır.

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -m "not requires_ollama"
```

LLM testleri için Ollama ve ilgili modeller gerekir. Kabul testleri `tests/acceptance/`,
değerlendirme araçları `tools/` altındadır. Pull request'lerde değişikliğin amacını
açıklayın, davranış değişikliklerine test ekleyin, kullanıcıya görünen değişiklikleri
`CHANGELOG.md` dosyasına yazın ve gizlilik/kanıt doğrulama kurallarını koruyun.
