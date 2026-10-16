"""Standalone Windows entry point."""
import sys
sys.dont_write_bytecode = True
from folder_change_review import main
raise SystemExit(main())
