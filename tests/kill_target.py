"""Kesinti testi için alt süreç: CLI'yi sahte model arka ucuyla çalıştırır ve N. Markdown yazımında geçici dosya
oluşturulduktan sonra (yerine konmadan önce) işaret dosyası yazıp bekler; test süreci bu anda öldürür.

Kullanım: python tests/kill_target.py <işaret_dosyası> <yazım_sırası> <cli argümanları...>
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.atomic_io as atomic_io  # noqa: E402
import src.cli as cli  # noqa: E402
from tests.fakes import FakeBackend  # noqa: E402


def main():
    marker, stall_at, args = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
    cli.create_model_backend = lambda config, logger: FakeBackend()
    real_replace = atomic_io._replace_with_retry
    markdown_writes = 0

    def stalling_replace(source, target, retries):
        nonlocal markdown_writes
        if str(target).endswith(".md"):
            markdown_writes += 1
            if markdown_writes == stall_at:
                marker.write_text(str(source), encoding="utf-8")
                time.sleep(120)  # test süreci burada öldürür
        return real_replace(source, target, retries)

    atomic_io._replace_with_retry = stalling_replace
    return cli.main(args)


if __name__ == "__main__":
    sys.exit(main())
