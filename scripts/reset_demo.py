"""Delete ONLY the designated demo database (data/tether.db*) and audit anchor. Keys and the model are kept.

Stop the backend first. Usage: backend\\.venv\\Scripts\\python.exe scripts\\reset_demo.py --yes
"""
import pathlib
import sys

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
TARGETS = [DATA / "tether.db", DATA / "tether.db-wal", DATA / "tether.db-shm", DATA / "audit_anchor.json"]

if "--yes" not in sys.argv:
    print("Would delete:", *[str(t) for t in TARGETS if t.exists()], sep="\n  ")
    print("Re-run with --yes to confirm.")
    sys.exit(0)
for t in TARGETS:
    if t.exists():
        t.unlink()
        print("deleted", t)
