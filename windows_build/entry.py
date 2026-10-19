"""Standalone Windows entry point."""
import sys
sys.dont_write_bytecode = True
from runtime_safety import configure_portable_storage
configure_portable_storage()
from folder_change_review import main
raise SystemExit(main())
