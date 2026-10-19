"""Standalone Windows entry point."""
import sys
sys.dont_write_bytecode = True
from runtime_safety import configure_portable_storage
try:
    configure_portable_storage()
except (OSError, ValueError) as error:
    if sys.stderr is not None:
        print(str(error), file=sys.stderr)
    if len(sys.argv) == 1:
        from tkinter import messagebox
        messagebox.showerror("Folder Change Review", str(error))
    raise SystemExit(1)
from folder_change_review import main
raise SystemExit(main())
