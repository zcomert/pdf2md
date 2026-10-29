"""Masaüstü arayüzü giriş noktası (§41): `.venv\\Scripts\\pythonw.exe process_papers_gui.py`"""
import sys

from src.dependencies import bootstrap_check

if __name__ == "__main__":
    import multiprocessing
    # Paralel ayrıştırma (spawn) worker'ları bu modülü içe aktarır; arayüz yalnızca ana süreçte açılır.
    multiprocessing.freeze_support()
    # bootstrap_check yalnızca standart kütüphane kullanır; üçüncü taraf paketler src.gui.app üzerinden
    # ancak bu kontrolden sonra içe aktarılmalı (§38 kriter 19). pythonw altında konsol yoktur; başarısız
    # olursa mesaj tkinter ile gösterilir (bkz. src.gui.app.gui_entry).
    import io
    message = io.StringIO()
    exit_code = bootstrap_check(stream=message)
    if exit_code is not None:
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
    from src.gui.app import gui_entry
    sys.exit(gui_entry())
