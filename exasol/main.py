"""
main.py — connection/setup verification only.

Confirms config loads, both the read-write and read-only (chat-agent)
Exasol identities connect, and DOC_INTEL is reachable. This is NOT the
app entry point — it doesn't start the Flask server or serve the
dashboard.

Run:
    python main.py

To actually run the dashboard, use `python -m api.routes` from the
project root instead (see README step 6), then open
http://localhost:5005.
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
    print("\nSetup verified. Run the dashboard with:  python -m api.routes")
    print("Then open http://localhost:5005 in a browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
