"""SQLite persistence layer for LeadRelay (standard library only).

The database path defaults to ``leads.db`` next to this file and can be
overridden with the ``LEADRELAY_DB`` environment variable.
"""

import os
import sqlite3

DB_PATH = os.environ.get(
    "LEADRELAY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    company             TEXT NOT NULL,
    phone               TEXT NOT NULL,
    source              TEXT NOT NULL,
    last_contact_date   TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('HOT', 'WARM', 'COLD')),
    status_reason       TEXT NOT NULL,
    next_follow_up_date TEXT NOT NULL,
    draft_message       TEXT NOT NULL,
    is_sent             BOOLEAN DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id   INTEGER NOT NULL,
    sender    TEXT NOT NULL CHECK (sender IN ('REP', 'BUYER')),
    message   TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leads_follow_up
    ON leads (next_follow_up_date, is_sent);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
CREATE INDEX IF NOT EXISTS idx_chat_lead ON chat_messages (lead_id);
"""


def get_db_connection() -> sqlite3.Connection:
    """Return a connection with Row factory and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create tables and indices if they do not already exist."""
    conn = get_db_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
