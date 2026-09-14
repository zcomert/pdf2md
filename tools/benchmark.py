"""Performans ölçümü (§30 son paragraf): mod başına sayfa başına süre, belge başına görsel/metin çağrısı, OCR.

Kullanım:
    .venv\\Scripts\\python.exe tools\\benchmark.py [--input tests\\fixtures\\real] [--modes fast balanced full]

Her mod için:
  soğuk: yeni çıktı klasörü, `--force`, varsayılan prompt (tam dönüşüm)
  sıcak: aynı klasörde prompt değişikliği (ayrıştırma ve görsel sonuçlar önbellekten; §38 kriter 14)
Rapor: reports/performance_<tarih>.md ve .json
"""
import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import AppConfig  # noqa: E402
from src.logger import setup_logging  # noqa: E402
from src.ollama_backend import OllamaBackend  # noqa: E402
from src.preflight import check_gpu, check_ocr  # noqa: E402
from src.runner import RunOptions, run  # noqa: E402

WARM_PROMPT = "Başlık, veri seti ve en iyi sonuçları çıkar."


def hardware():
    config = AppConfig()
    logger = setup_logging(console=False)
    info = {"gpu": check_gpu().message, "ocr": check_ocr(config)[0].message}
    try:
        models = OllamaBackend(config.ollama, logger).list_models()
        info["models"] = {name: models[name].reference for name in (config.models.text, config.models.vision)
                          if name in models}
    except Exception as exc:  # noqa: BLE001 — rapora yazılır
        info["models"] = f"alınamadı: {exc}"
    return info


def measure(options, output):
    started = time.monotonic()
    result = run(options, console=lambda text, error=False: print(f"  {text}"))
    wall = time.monotonic() - started
    state = json.loads((output / "processing_state.json").read_text(encoding="utf-8"))
    documents = [state["documents"][d.relative_path] for d in result.documents if d.relative_path in state["documents"]]
    processed = [d for d in documents if d.get("processing_time_sec") is not None and d["status"] != "failed"]
    pages = sum(d.get("pages") or 0 for d in processed)
    summary = result.summary
    return {
        "exit_code": result.exit_code, "wall_sec": round(wall, 1),
        "run_sec": summary.total_time_sec if summary else None,
        "documents": len(documents), "processed": summary.completed + summary.completed_with_warnings if summary else 0,
        "failed": summary.failed if summary else 0, "pages": pages,
        "sec_per_page": round(sum(d["processing_time_sec"] for d in processed) / pages, 2) if pages else None,
        "vision_calls": summary.vision_calls if summary else 0, "text_llm_calls": summary.text_llm_calls if summary else 0,
        "vision_calls_per_doc": round(summary.vision_calls / max(1, len(processed)), 1) if summary else None,
        "text_calls_per_doc": round(summary.text_llm_calls / max(1, len(processed)), 1) if summary else None,
        "ocr_pages": sum(d.get("ocr_pages") or 0 for d in processed),
        "parsed": summary.parsed if summary else 0, "parsed_from_cache": summary.parsed_from_cache if summary else 0,
    }


def benchmark(input_dir, modes, work):
    report = {"generated": datetime.now().isoformat(timespec="seconds"), "input": str(input_dir),
              "hardware": hardware(), "warm_prompt": WARM_PROMPT, "modes": {}}
    for mode in modes:
        output = work / f"bench_{mode}"
        shutil.rmtree(output, ignore_errors=True)
        common = dict(input_dir=str(input_dir), output_dir=str(output), mode=mode, console_logging=False)
        print(f"== {mode} soğuk")
        cold = measure(RunOptions(**common, force=True), output)
        print(f"== {mode} sıcak (prompt değişikliği)")
        warm = measure(RunOptions(**common, prompt=WARM_PROMPT, scope="document"), output)
        report["modes"][mode] = {"cold": cold, "warm": warm}
    return report


def render_markdown(report):
    modes = list(report["modes"])
    lines = [f"# Performans Raporu — {report['generated'][:10]}", "",
             f"Girdi: `{report['input']}`. Donanım: {report['hardware']['gpu']}. OCR: {report['hardware']['ocr']}.",
             f"Modeller: {report['hardware']['models']}.", "",
             "Soğuk: önbelleksiz, varsayılan prompt (tam dönüşüm). Sıcak: aynı klasörde prompt değişikliği "
             f"(\"{report['warm_prompt']}\"); ayrıştırma ve görsel sonuçlar önbellekten.", "",
             "| Ölçüt | " + " | ".join(f"{m} soğuk | {m} sıcak" for m in modes) + " |",
             "|---|" + "---:|" * (2 * len(modes))]
    rows = [("wall_sec", "Toplam süre (sn)"), ("pages", "İşlenen sayfa"), ("sec_per_page", "Sayfa başına süre (sn)"),
            ("processed", "Tamamlanan belge"), ("failed", "Başarısız belge"), ("vision_calls", "Görsel çağrı"),
            ("vision_calls_per_doc", "Belge başına görsel çağrı"), ("text_llm_calls", "Metin çağrısı"),
            ("text_calls_per_doc", "Belge başına metin çağrısı"), ("ocr_pages", "OCR sayfası"),
            ("parsed", "Ayrıştırılan"), ("parsed_from_cache", "Önbellekten ayrıştırma")]
    for key, label in rows:
        values = []
        for mode in modes:
            for phase in ("cold", "warm"):
                value = report["modes"][mode][phase].get(key)
                values.append("—" if value is None else str(value))
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default=str(ROOT / "tests" / "fixtures" / "real"))
    parser.add_argument("--modes", nargs="+", default=["fast", "balanced", "full"], choices=["fast", "balanced", "full"])
    parser.add_argument("--work", default=str(ROOT / "reports" / "bench_work"))
    parser.add_argument("--reports", default=str(ROOT / "reports"))
    args = parser.parse_args(argv)
    report = benchmark(Path(args.input), args.modes, Path(args.work))
    stamp = datetime.now().strftime("%Y%m%d")
    reports = Path(args.reports)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"performance_{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports / f"performance_{stamp}.md").write_text(render_markdown(report), encoding="utf-8")
    sys.stdout.reconfigure(errors="replace")
    print(render_markdown(report))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
