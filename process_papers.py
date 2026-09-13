import signal
import sys

from src.dependencies import bootstrap_check


def _interrupt(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    exit_code = bootstrap_check()
    if exit_code is not None:
        sys.exit(exit_code)
    if hasattr(signal, "SIGBREAK"):
        # Windows Ctrl+Break varsayılan olarak süreci anında sonlandırır; finally blokları (kilit, state) çalışsın.
        signal.signal(signal.SIGBREAK, _interrupt)
    from src.cli import main
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("İptal edildi.", file=sys.stderr)
        sys.exit(130)
