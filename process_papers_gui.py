"""Masaüstü arayüzü giriş noktası (§41): `.venv\\Scripts\\pythonw.exe process_papers_gui.py`"""
import multiprocessing
import sys

from src.dependencies import bootstrap_check


def _enable_high_dpi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


if __name__ == "__main__":
    # Paralel ayrıştırma (spawn) worker'ları bu modülü içe aktarır; arayüz yalnızca ana süreçte açılır.
    multiprocessing.freeze_support()
    import io
    message = io.StringIO()
    exit_code = bootstrap_check(stream=message)
    if exit_code is not None:
        # pythonw altında konsol yoktur: eksik paket mesajı ve kurulum komutu pencerede gösterilir.
        if sys.stderr is not None:
            sys.stderr.write(message.getvalue())
        try:
            import tkinter
            from tkinter import messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("pdf2md", message.getvalue())
            root.destroy()
        except Exception:  # noqa: BLE001 — tkinter de yoksa yalnızca konsol mesajı kalır
            pass
        sys.exit(exit_code)
    _enable_high_dpi()
    from src.gui.app import run_app
    run_app()
