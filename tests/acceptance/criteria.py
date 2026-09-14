"""§38 (1–28) ve §41.4 (G1–G5) kabul kriterleri → otomatik testler. `tests/acceptance/MATRIX.md` bu tablonun
okunur halidir. `pytest -m acceptance` bu testleri seçer; `test_matrix.py` her kimliğin gerçekten var olduğunu
denetler (matris çürümesin)."""

CRITERIA = {
    "1": ("Klasör ve tek PDF girişi; --recursive", [
        "tests/test_discovery.py::test_recursive_discovery",
        "tests/test_discovery.py::test_single_file_input",
        "tests/test_cli_batch.py::test_full_conversion_end_to_end",
    ]),
    "2": ("Her tamamlanan PDF için tek .md; başka içerik dosyası yok (assets hariç)", [
        "tests/test_cli_batch.py::test_full_conversion_end_to_end",
        "tests/test_extraction.py::test_prompt_answer_end_to_end",
    ]),
    "3": ("Aynı adlı iki PDF'nin çıktıları çakışmaz", [
        "tests/test_paths.py::test_same_name_in_different_folders_does_not_collide",
        "tests/test_paths.py::test_collision_after_normalization_gets_sha_suffix",
        "tests/test_cli_batch.py::test_full_conversion_end_to_end",
    ]),
    "4": ("Prompt yokken tam dönüşüm, A.md üretiminde metin LLM'i çağrılmaz", [
        "tests/test_cli_batch.py::test_no_text_llm_in_full_conversion",
        "tests/test_prompt_planner.py::test_default_prompt_does_not_call_llm",
    ]),
    "5": ("Promptta yalnızca istenen başlıklar; bulunamayan not_found", [
        "tests/test_extraction.py::test_prompt_answer_end_to_end",
        "tests/test_extraction.py::test_all_not_found_writes_headings_and_warns",
    ]),
    "6": ("Boş prompt → varsayılan dönüşüm + completed_with_warnings", [
        "tests/test_cli_batch.py::test_empty_prompt_completes_with_warnings",
    ]),
    "7": ("--plan-only PDF işlemeden planı gösterir", [
        "tests/test_prompt_planner.py::test_plan_only_prints_collection_plan_without_processing",
        "tests/test_cli.py::test_plan_only_does_not_create_output_dir",
    ]),
    "8": ("Tek PDF → document; klasör + karşılaştırma → tek koleksiyon dosyası, belge başına A.md yok", [
        "tests/test_prompt_planner.py::test_single_pdf_input_forces_document_scope",
        "tests/test_prompt_planner.py::test_plan_only_single_pdf_is_document_scope",
        "tests/test_collection.py::test_collection_end_to_end",
    ]),
    "9": ("Koleksiyon bulguları makale adıyla, sayısal bulgular sayfayla izlenebilir", [
        "tests/test_collection.py::test_collection_end_to_end",
    ]),
    "10": ("Taranmış PDF'ten OCR veya görsel model ile metin", [
        "tests/test_cli_batch.py::test_scanned_pdf_is_ocr_converted",
        "tests/test_vision.py::test_page_text_replaces_flow_blocks_and_resolves_unreadable_page",
        "tests/test_ocr.py::test_synthetic_scanned_pdf_ocr_accuracy",
    ]),
    "11": ("Bozuk ve şifreli PDF failed + aşama; batch tamamlanır", [
        "tests/test_cli_batch.py::test_full_conversion_end_to_end",
    ]),
    "12": ("İkinci çalıştırmada değişmeyenler skipped, model çağrısı yok", [
        "tests/test_robustness.py::test_second_run_makes_no_model_calls",
        "tests/test_cli_batch.py::test_second_run_skips_and_exits_ok",
    ]),
    "13": ("İçerik değişen PDF yeniden işlenir; yalnızca mtime değişen işlenmez", [
        "tests/test_discovery.py::test_mtime_only_change_does_not_reset_status",
        "tests/test_cli_batch.py::test_changed_pdf_is_regenerated",
    ]),
    "14": ("Prompt değişince ayrıştırma önbellekten, A.md yeniden", [
        "tests/test_extraction.py::test_prompt_change_reuses_parse_and_second_run_skips",
    ]),
    "15": ("Süreç öldürülüp yeniden başlatılınca yarım dosya yok, kaldığı yerden devam", [
        "tests/test_robustness.py::test_killed_run_leaves_no_partial_files_and_resumes",
    ]),
    "16": ("Aynı çıktı klasörü için eşzamanlı ikinci çalıştırma → çıkış 2", [
        "tests/test_cli_discovery.py::test_concurrent_run_rejected_with_exit_code_2",
        "tests/test_state_lock.py::test_lock_held_by_other_process",
    ]),
    "17": ("Giriş klasöründeki dosyaların SHA-256'ları ve listesi değişmez", [
        "tests/test_cli_batch.py::test_full_conversion_end_to_end",
        "tests/test_cli_discovery.py::test_end_to_end_discovery_registers_all_pdfs",
    ]),
    "18": ("Eksik metin modeli → ollama pull komutu + çıkış 2", [
        "tests/test_cli_batch.py::test_missing_text_model_shows_pull_command",
    ]),
    "19": ("Eksik Python bağımlılığı işleme başlamadan paket adı ve kurulum komutuyla", [
        "tests/test_cli_discovery.py::test_process_papers_entry_reports_missing_dependency",
        "tests/test_preflight.py::test_missing_packages_reported_with_install_command",
    ]),
    "20": ("A.md'deki sayılar verified veya işaretli; işaretsiz doğrulanmamış değer yok", [
        "tests/test_extraction.py::test_value_missing_from_source_is_unverified_and_marked",
        "tests/test_extraction.py::test_invented_block_id_is_source_not_found",
        "tests/test_extraction.py::test_safety_net_marks_unverified_numbers",
        "tests/test_extraction.py::test_prompt_answer_end_to_end",
    ]),
    "21": ("Referans veride bulunmayan sonuç verified raporlanmaz", [
        "tests/test_extraction.py::test_table_value_must_be_in_model_row",
        "tests/test_extraction.py::test_table_value_must_be_in_metric_column_with_multilevel_header",
        "tests/test_extraction.py::test_numbers_in_source",
        "tests/acceptance/test_acceptance_extra.py::test_evaluator_detects_verified_value_from_wrong_cell",
    ]),
    "22": ("Referans veride mod bazında doğruluk ölçülüp raporlanır", [
        "tests/acceptance/test_acceptance_extra.py::test_evaluator_scores_synthetic_reference",
    ]),
    "23": ("document.json, çıkarım ve state dosyaları şema doğrulamasından geçer", [
        "tests/acceptance/test_acceptance_extra.py::test_all_output_json_files_validate",
    ]),
    "24": ("Log'da FAST/BALANCED/FULL görsel çağrıları tetikleyicileriyle ayırt edilebilir", [
        "tests/test_cli_batch.py::test_mode_controls_vision_calls_and_log_records_triggers",
    ]),
    "25": ("papers_summary.csv tüm belgeleri §22.2 sütunlarıyla içerir, Türkçe karakterler bozulmaz", [
        "tests/test_inventory.py::test_csv_columns_bom_turkish_and_rows",
        "tests/test_inventory.py::test_csv_written_at_run_end_with_discovery_failures",
    ]),
    "26": ("Sonuç sayıları konsolda ve log'da", [
        "tests/acceptance/test_acceptance_extra.py::test_run_summary_on_console_and_in_log",
    ]),
    "27": ("Temiz makinede §34.3 ile kurulum; global site-packages olmadan çalışır", [
        "tests/test_preflight.py::test_virtualenv_warning_has_command",
        "tests/acceptance/test_acceptance_extra.py::test_virtualenv_does_not_use_global_site_packages",
    ]),
    "28": (".venv ve Python önbellek dosyaları çıktı klasörüne ve sürüm kontrolüne girmez", [
        "tests/acceptance/test_acceptance_extra.py::test_venv_and_caches_not_in_output_or_git",
    ]),
    "G1": ("Terminal kullanmadan klasör, prompt ve mod seçip başlatma", [
        "tests/test_gui.py::test_start_progress_errors_and_results",
        "tests/test_gui.py::test_validation_errors_block_start",
    ]),
    "G2": ("İşlem sırasında ilerleme ve hata durumu anlaşılır", [
        "tests/test_gui.py::test_start_progress_errors_and_results",
        "tests/test_gui.py::test_progress_tracker_counts_and_eta",
    ]),
    "G3": ("A.md veya koleksiyon Markdown'ı GUI'den açılabilir", [
        "tests/test_gui.py::test_start_progress_errors_and_results",
        "tests/test_gui.py::test_collection_output_shown_separately",
    ]),
    "G4": ("GUI kapatılsa bile resume çalışır", [
        "tests/test_gui.py::test_close_during_run_then_resume",
    ]),
    "G5": ("Ollama çalışmıyor veya model eksikse çözüm önerisi ve komut", [
        "tests/test_gui.py::test_ollama_down_shows_solution_command",
        "tests/test_gui.py::test_missing_model_shows_pull_command",
    ]),
}

# Otomatik testin yanında elle doğrulama gerektiren kısımlar (MATRIX.md'de not ve tarihle)
MANUAL = {
    "22": "tools/evaluate.py ile gerçek modellerle ölçüm; rapor reports/accuracy_<tarih>.md",
    "25": "CSV'nin Excel'de açılıp Türkçe karakterlerin gözle kontrolü",
    "27": "Temiz klasöre git clone + §34.3 kurulum komutları",
    "G1": "Dosya seçme diyalogları ve 'aç' düğmelerinin varsayılan uygulamayı başlatması",
}


def acceptance_node_ids():
    return {node for _, nodes in CRITERIA.values() for node in nodes}
