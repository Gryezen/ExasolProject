"""
main.py — entry point.

Right now this just proves the wiring works end to end: load config, connect
read-write and read-only, confirm DOC_INTEL exists. Once agents/ingestion.py
and agents/extraction.py land, this becomes the CLI/API entry point that
drives orchestration/workflow.py.

Run:
    python main.py
"""

import sys

from config import load_settings
from database.db import Database, ReadOnlyDatabase


def main() -> int:
    try:
        settings = load_settings()
    except RuntimeError as e:
        print(f"Config error: {e}")
        return 1

    db = Database(settings)
    ro_db = ReadOnlyDatabase(settings)

    try:
        rows = db.fetchall("SELECT CURRENT_TIMESTAMP")
        print(f"Connected (read-write). Server time: {rows[0][0]}")
    except Exception as e:
        print(f"Read-write connection failed: {e}")
        return 1

    try:
        ro_db.fetchall("SELECT CURRENT_TIMESTAMP")
        print("Connected (read-only, chat-agent identity).")
    except Exception as e:
        print(f"Read-only connection failed: {e}")
        print("Check EXASOL_RO_USER / EXASOL_RO_PASSWORD and docs/mcp-grants.sql.")
        return 1

    doc_count = db.fetchall("SELECT COUNT(*) FROM DOCUMENTS")[0][0]
    print(f"DOCUMENTS table reachable. Current row count: {doc_count}")
    print("\nSetup verified. Next: agents/ingestion.py + agents/extraction.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
