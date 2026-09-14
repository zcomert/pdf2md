"""Alan kataloğu (§17.3): planlayıcının istekle eşleyebileceği standart alanlar. Liste zorunlu çıktı değildir;
yalnızca promptta istenen alanlar çıkarılır. Katalog dışı istekler `custom.<slug>` alanı olur."""
import re
import unicodedata
from dataclasses import dataclass

FULL_CONVERSION = "full_conversion"
CUSTOM_PREFIX = "custom."
GROUPS = ("bibliographic", "research", "dataset", "methodology", "results", "equations", "evaluation")
NEED_KEYS = ("tables", "equations", "figures", "full_text")


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label_tr: str
    label_en: str
    value_type: str  # str | int | float | list[str] | table | equations | results
    hint_sections: tuple = ()
    needs: tuple = ()  # NEED_KEYS alt kümesi

    @property
    def group(self):
        return self.key.split(".", 1)[0]

    @property
    def name(self):
        return self.key.split(".", 1)[1]


_METHOD = ("Method", "Methodology", "Materials and Methods", "Approach", "Yöntem", "Materyal ve Yöntem")
_DATA = ("Dataset", "Data", "Data Collection", "Experimental Setup", "Veri", "Veri Seti")
_RESULTS = ("Results", "Experiments", "Evaluation", "Results and Discussion", "Bulgular", "Sonuçlar", "Deneyler")
_CONCLUSION = ("Conclusion", "Conclusions", "Discussion", "Sonuç", "Tartışma")
_INTRO = ("Abstract", "Introduction", "Özet", "Giriş")

CATALOG = (
    FieldSpec("bibliographic.title", "Başlık", "Title", "str", ("Title",)),
    FieldSpec("bibliographic.authors", "Yazarlar", "Authors", "list[str]", ("Title",)),
    FieldSpec("bibliographic.year", "Yıl", "Year", "int", ("Title",)),
    FieldSpec("bibliographic.venue", "Dergi/konferans", "Journal or conference", "str", ("Title",)),
    FieldSpec("bibliographic.doi", "DOI", "DOI", "str", ("Title",)),
    FieldSpec("research.objective", "Amaç", "Objective", "str", _INTRO),
    FieldSpec("research.problem", "Problem", "Research problem", "str", _INTRO),
    FieldSpec("research.contributions", "Temel katkılar", "Main contributions", "list[str]", _INTRO + _CONCLUSION),
    FieldSpec("dataset.name", "Veri seti adı", "Dataset name", "list[str]", _DATA + _METHOD),
    FieldSpec("dataset.sample_count", "Örnek sayısı", "Number of samples", "int", _DATA + _METHOD, ("tables",)),
    FieldSpec("dataset.classes", "Sınıflar", "Classes", "list[str]", _DATA + _METHOD, ("tables",)),
    FieldSpec("dataset.split", "Eğitim/doğrulama/test bölünmesi", "Train/validation/test split", "str",
              _DATA + _METHOD, ("tables",)),
    FieldSpec("methodology.preprocessing", "Ön işleme", "Preprocessing", "list[str]", _METHOD),
    FieldSpec("methodology.features", "Özellikler", "Features", "list[str]", _METHOD, ("tables",)),
    FieldSpec("methodology.feature_selection", "Özellik seçimi", "Feature selection", "str", _METHOD),
    FieldSpec("methodology.models", "Modeller", "Models", "list[str]", _METHOD + _RESULTS),
    FieldSpec("methodology.hyperparameters", "Hiperparametreler", "Hyperparameters", "table", _METHOD, ("tables",)),
    FieldSpec("methodology.evaluation_protocol", "Değerlendirme protokolü", "Evaluation protocol", "str",
              _METHOD + _RESULTS),
    FieldSpec("results.metrics", "Performans metrikleri", "Performance metrics", "list[str]", _RESULTS, ("tables",)),
    FieldSpec("results.best_model", "En iyi model", "Best model", "str", _RESULTS + _CONCLUSION, ("tables",)),
    FieldSpec("results.best", "En iyi sonuçlar", "Best results", "results", _RESULTS + _CONCLUSION, ("tables",)),
    FieldSpec("results.comparative", "Karşılaştırmalı sonuçlar", "Comparative results", "results", _RESULTS,
              ("tables",)),
    FieldSpec("results.per_class", "Sınıf bazlı sonuçlar", "Per-class results", "results", _RESULTS, ("tables",)),
    FieldSpec("equations.important", "Önemli formüller", "Important equations", "equations", _METHOD,
              ("equations",)),
    FieldSpec("evaluation.conclusion", "Yazarların temel sonucu", "Authors' main conclusion", "str", _CONCLUSION),
    FieldSpec("evaluation.limitations", "Sınırlılıklar", "Limitations", "list[str]", _CONCLUSION + _RESULTS),
    FieldSpec("evaluation.future_work", "Gelecek çalışma önerileri", "Future work", "list[str]", _CONCLUSION),
)

FIELDS = {spec.key: spec for spec in CATALOG}

# Çıktı başlıklarını alanlarla eşlemek için grup adları (TR/EN)
GROUP_LABELS = {
    "bibliographic": ("Künye", "Kaynak bilgisi", "Bibliographic", "Bibliography", "Metadata"),
    "research": ("Araştırma", "Research", "Study"),
    "dataset": ("Veri seti", "Veri", "Dataset", "Data"),
    "methodology": ("Yöntem", "Metodoloji", "Method", "Methodology", "Approach"),
    "results": ("Sonuçlar", "Bulgular", "Results", "Findings", "Performance"),
    "equations": ("Formüller", "Denklemler", "Equations", "Formulas"),
    "evaluation": ("Değerlendirme", "Evaluation", "Discussion"),
}
# Grup öneki olmadan verilen adlar ("title", "doi") tek bir alana karşılık geliyorsa kabul edilir.
_BY_NAME = {}
for _spec in CATALOG:
    _BY_NAME.setdefault(_spec.name, []).append(_spec.key)


def is_catalog_field(key):
    return key in FIELDS or key == FULL_CONVERSION


DERIVED_BEST_PREFIX = "results.best_"


def derived_metric(key):
    """`results.best_accuracy` → `accuracy`; katalogdaki `results.best_model` türetilmiş metrik değildir."""
    if key.startswith(DERIVED_BEST_PREFIX) and key not in FIELDS:
        metric = key[len(DERIVED_BEST_PREFIX):]
        return metric if re.fullmatch(r"[a-z0-9_]+", metric) else None
    return None


def is_summary_field(key):
    """`summary.extra_fields` için geçerli anahtar: katalog alanı veya `results.best_<metrik>` (§22.4)."""
    return key in FIELDS or derived_metric(key) is not None


def is_valid_field(key):
    return is_catalog_field(key) or (key.startswith(CUSTOM_PREFIX) and len(key) > len(CUSTOM_PREFIX))


def resolve_alias(key):
    """Kataloğa ait alan anahtarı veya None. `title` → `bibliographic.title`."""
    key = key.strip()
    if is_catalog_field(key):
        return key
    matches = _BY_NAME.get(key, [])
    return matches[0] if len(matches) == 1 else None


def slugify(text, max_length=40):
    """`custom.<slug>` için ASCII, küçük harf, alt çizgili ad."""
    text = text.replace("ı", "i").replace("İ", "I")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return slug[:max_length].rstrip("_") or "field"


def custom_key(text):
    if text.startswith(CUSTOM_PREFIX):
        text = text[len(CUSTOM_PREFIX):]
    return CUSTOM_PREFIX + slugify(text)


def label(key, language="tr"):
    spec = FIELDS.get(key)
    if spec is None:
        return "Tam dönüşüm" if key == FULL_CONVERSION else key
    return spec.label_en if language == "en" else spec.label_tr


def catalog_needs(fields):
    """Katalogdaki alanların gerektirdiği pahalı işlemler. `full_conversion` her şeyi gerektirir."""
    needs = dict.fromkeys(NEED_KEYS, False)
    for key in fields:
        if key == FULL_CONVERSION:
            return dict.fromkeys(NEED_KEYS, True)
        for need in getattr(FIELDS.get(key), "needs", ()):
            needs[need] = True
    return needs


def catalog_prompt_lines():
    """Planlayıcı sistem promptundaki katalog listesi."""
    return "\n".join(f"- {spec.key}: {spec.label_en}" for spec in CATALOG)
