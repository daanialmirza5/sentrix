"""Verify the demo audit hash chain directly from SQLite (no server needed). Exit code 1 if broken."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from app.audit import chain  # noqa: E402
from app.database import SessionLocal, create_all  # noqa: E402

create_all()
with SessionLocal() as db:
    result = chain.verify_chain(db)
print(json.dumps(result, indent=2))
sys.exit(0 if result["valid"] else 1)
