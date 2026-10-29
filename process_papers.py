import sys

from src.dependencies import bootstrap_check

if __name__ == "__main__":
    # bootstrap_check yalnızca standart kütüphane kullanır; üçüncü taraf paketler (tqdm, pydantic, ...)
    # src.cli üzerinden ancak bu kontrolden sonra içe aktarılmalı (§38 kriter 19).
    exit_code = bootstrap_check()
    if exit_code is not None:
        sys.exit(exit_code)
    from src.cli import cli_entry
    sys.exit(cli_entry())
