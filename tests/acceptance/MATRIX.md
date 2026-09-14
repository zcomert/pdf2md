# Kabul Kriteri İzleme Matrisi

§38 (1–28) ve §41.4 (G1–G5). Test eşlemesinin makine okunur kaynağı `tests/acceptance/criteria.py`'dir; `test_matrix.py` her eşlenen testin var olduğunu denetler. Tümünü çalıştırmak için: `.venv\Scripts\python.exe -m pytest -m acceptance` (gerçek model testleri Ollama erişilebilirse çalışır).

Son otomatik çalıştırma: **2026-09-14** — `pytest -m acceptance` 68 geçti; tam paket 575 + `requires_ollama` 10 geçti (bkz. `fazlar/faz-14-kabul-olcum-dokumantasyon.md`).

| # | Kriter | Tür | Testler | Sonuç | Not |
|---|---|---|---|---|---|
| 1 | Klasör ve tek PDF girişi, `--recursive` | Otomatik | `test_discovery::test_recursive_discovery`, `::test_single_file_input`, `test_cli_batch::test_full_conversion_end_to_end` | ✓ | |
| 2 | Tamamlanan her PDF için tek `.md` (assets hariç) | Otomatik | `test_cli_batch::test_full_conversion_end_to_end`, `test_extraction::test_prompt_answer_end_to_end` | ✓ | |
| 3 | Aynı adlı PDF çıktıları çakışmaz | Otomatik | `test_paths::test_same_name_in_different_folders_does_not_collide`, `::test_collision_after_normalization_gets_sha_suffix`, uçtan uca test | ✓ | |
| 4 | Prompt yokken tam dönüşüm, metin LLM'i çağrılmaz | Otomatik | `test_cli_batch::test_no_text_llm_in_full_conversion`, `test_prompt_planner::test_default_prompt_does_not_call_llm` | ✓ | Faz 11 kararı: "A.md içeriği için"; künye adımı ayrı |
| 5 | Yalnızca istenen başlıklar; `not_found` | Otomatik | `test_extraction::test_prompt_answer_end_to_end`, `::test_all_not_found_writes_headings_and_warns` | ✓ | |
| 6 | Boş prompt → varsayılan + uyarılı | Otomatik | `test_cli_batch::test_empty_prompt_completes_with_warnings` | ✓ | |
| 7 | `--plan-only` PDF işlemez | Otomatik | `test_prompt_planner::test_plan_only_prints_collection_plan_without_processing`, `test_cli::test_plan_only_does_not_create_output_dir` | ✓ | Gerçek Gemma: `test_real_planner_produces_valid_plans` |
| 8 | Tek PDF → document; klasör + karşılaştırma → tek koleksiyon dosyası | Otomatik | `test_prompt_planner::test_single_pdf_input_forces_document_scope`, `test_collection::test_collection_end_to_end` | ✓ | Gerçek 9 makalede §40 komutu (Faz 12) |
| 9 | Koleksiyon bulguları makale adı ve sayfayla | Otomatik | `test_collection::test_collection_end_to_end` | ✓ | Gerçek Gemma: `test_real_synthesis_cites_papers` |
| 10 | Taranmış PDF'ten OCR/görsel modelle metin | Otomatik | `test_cli_batch::test_scanned_pdf_is_ocr_converted`, `test_vision::test_page_text_replaces_flow_blocks_and_resolves_unreadable_page`, `test_ocr::test_synthetic_scanned_pdf_ocr_accuracy` | ✓ | Gerçek taranmış PDF yok (§38.1 açığı); vektör metinli Shilaskar OCR ile |
| 11 | Bozuk/şifreli PDF failed + aşama | Otomatik | `test_cli_batch::test_full_conversion_end_to_end` | ✓ | |
| 12 | Değişmeyenler skipped, model çağrısı yok | Otomatik | `test_robustness::test_second_run_makes_no_model_calls`, `test_cli_batch::test_second_run_skips_and_exits_ok` | ✓ | |
| 13 | İçerik değişen yeniden işlenir; mtime işlenmez | Otomatik | `test_discovery::test_mtime_only_change_does_not_reset_status`, `test_cli_batch::test_changed_pdf_is_regenerated` | ✓ | |
| 14 | Prompt değişince ayrıştırma önbellekten | Otomatik | `test_extraction::test_prompt_change_reuses_parse_and_second_run_skips` | ✓ | Performans raporundaki sıcak çalıştırma |
| 15 | Kesinti sonrası yarım dosya yok, devam | Otomatik | `test_robustness::test_killed_run_leaves_no_partial_files_and_resumes` | ✓ | Alt süreç öldürülür |
| 16 | Eşzamanlı ikinci çalıştırma → 2 | Otomatik | `test_cli_discovery::test_concurrent_run_rejected_with_exit_code_2`, `test_state_lock::test_lock_held_by_other_process` | ✓ | |
| 17 | Giriş dosyaları değişmez | Otomatik | `test_cli_batch::test_full_conversion_end_to_end`, `test_cli_discovery::test_end_to_end_discovery_registers_all_pdfs` | ✓ | |
| 18 | Eksik metin modeli → `ollama pull` + 2 | Otomatik | `test_cli_batch::test_missing_text_model_shows_pull_command` | ✓ | |
| 19 | Eksik bağımlılık işleme başlamadan | Otomatik | `test_cli_discovery::test_process_papers_entry_reports_missing_dependency`, `test_preflight::test_missing_packages_reported_with_install_command` | ✓ | |
| 20 | Sayılar verified veya işaretli | Otomatik | `test_extraction::` işaret, uydurma kanıt, güvenlik ağı, uçtan uca | ✓ | |
| 21 | Referansta olmayan sonuç verified olmaz | Otomatik + ölçüm | `test_extraction::test_table_value_must_be_in_model_row`, `::test_table_value_must_be_in_metric_column_with_multilevel_header`, `::test_numbers_in_source`, `test_acceptance_extra::test_evaluator_detects_verified_value_from_wrong_cell`; `tools/evaluate.py` | ✓ | Sütun kuralı (Faz 14); ölçüm 2026-09-14: 3 modda çelişen verified 0. Sütun başlıktan belirlenemeyen tablolarda doğrulama satır düzeyinde |
| 22 | Mod bazında doğruluk ölçülür, raporlanır | Otomatik + ölçüm | `test_acceptance_extra::test_evaluator_scores_synthetic_reference`; `tools/evaluate.py` | ✓ | Rapor üretildi; eşikler kullanıcı onayı bekliyor; referans veri taslak |
| 23 | JSON ara dosyaları şemadan geçer | Otomatik | `test_acceptance_extra::test_all_output_json_files_validate` | ✓ | document, çıkarım, plan, künye, state |
| 24 | Log'da mod tetikleyicileri ayırt edilir | Otomatik | `test_cli_batch::test_mode_controls_vision_calls_and_log_records_triggers` | ✓ | |
| 25 | CSV tüm belgeler, §22.2 sütunları, Türkçe | Otomatik + elle | `test_inventory::test_csv_columns_bom_turkish_and_rows`, `::test_csv_written_at_run_end_with_discovery_failures` | ⚠ | BOM/UTF-8 bayt düzeyinde test; **Excel'de açma elle yapılmadı** |
| 26 | Sonuç sayıları konsol ve log'da | Otomatik | `test_acceptance_extra::test_run_summary_on_console_and_in_log` | ✓ | |
| 27 | Temiz kurulum, global site-packages yok | Otomatik + elle | `test_acceptance_extra::test_virtualenv_does_not_use_global_site_packages` | ✓ | 2026-09-14: temiz `git clone` + §34.3 komutları (Windows); 561/562 test geçti, başarısız fixture `.gitattributes` ile düzeltildi. Linux denenmedi |
| 28 | `.venv`/önbellek çıktıya ve git'e girmez | Otomatik | `test_acceptance_extra::test_venv_and_caches_not_in_output_or_git` | ✓ | |
| G1 | Terminal olmadan başlatma | Otomatik + elle | `test_gui::test_start_progress_errors_and_results`, `::test_validation_errors_block_start` | ⚠ | Gerçek pencereyle otomatik; dosya seçme diyaloğu elle denenmedi |
| G2 | İlerleme ve hata anlaşılır | Otomatik | `test_gui::test_start_progress_errors_and_results`, `::test_progress_tracker_counts_and_eta` | ✓ | Gerçek modellerle ekran görüntüleri (Faz 13) |
| G3 | A.md / koleksiyon GUI'den açılır | Otomatik | `test_gui::test_start_progress_errors_and_results`, `::test_collection_output_shown_separately` | ✓ | `os.startfile` çağrısı elle denenmedi |
| G4 | Kapatma sonrası resume | Otomatik | `test_gui::test_close_during_run_then_resume` | ✓ | |
| G5 | Ollama/model yok → çözüm ve komut | Otomatik | `test_gui::test_ollama_down_shows_solution_command`, `::test_missing_model_shows_pull_command` | ✓ | |

**Açıklama:** ✓ otomatik testlerle karşılanıyor · ⚠ otomatik kısım karşılanıyor, belirtilen elle doğrulama veya bilinen sınırlama var.
