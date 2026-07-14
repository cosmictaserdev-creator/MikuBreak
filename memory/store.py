import sqlite3
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    recurring_rule TEXT,
    done INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    target_interval_minutes INTEGER NOT NULL,
    last_triggered_at TEXT,
    is_paused INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
"""

# Full-text index over memories — much better recall than LIKE (word matching,
# prefix search). Kept in sync by triggers; content= makes it an external-content
# table so nothing is stored twice.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, category, content='memories', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES ('delete', old.id, old.content, old.category);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES ('delete', old.id, old.content, old.category);
    INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
END;
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self, db_path="miku_memory.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._fts_enabled = True
        try:
            self._conn.executescript(FTS_SCHEMA)
            # reindex rows that predate the FTS table (or were changed while triggers were absent)
            self._conn.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError:
            self._fts_enabled = False  # sqlite built without fts5 — LIKE fallback still works
        self._conn.commit()

    # -- memories --------------------------------------------------------

    def add_memory(self, category: str, content: str, importance: int = 1, source: str = "user") -> int:
        cur = self._conn.execute(
            "INSERT INTO memories (category, content, importance, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (category, content, importance, source, _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_memories(self, limit: int = 50):
        rows = self._conn.execute(
            "SELECT * FROM memories ORDER BY importance DESC, created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_memories(self, query: str, limit: int = 10):
        if self._fts_enabled:
            # OR the words together with prefix match — "coffe pref" still finds
            # "prefers coffee". Quoted to keep FTS syntax chars in the query inert.
            words = [w.replace('"', "") for w in query.split() if w.strip('"')]
            if words:
                match = " OR ".join(f'"{w}"*' for w in words)
                try:
                    rows = self._conn.execute(
                        "SELECT m.* FROM memories m JOIN memories_fts f ON m.id = f.rowid "
                        "WHERE memories_fts MATCH ? ORDER BY rank, m.importance DESC LIMIT ?",
                        (match, limit),
                    ).fetchall()
                    if rows:
                        return [dict(r) for r in rows]
                except sqlite3.OperationalError:
                    pass  # malformed match string — fall through to LIKE
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? OR category LIKE ? "
            "ORDER BY importance DESC, created_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, memory_id: int):
        self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()

    def clear_memories(self):
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    # -- reminders ---------------------------------------------------------

    def add_reminder(self, text: str, due_at: str, recurring_rule: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders (text, due_at, recurring_rule, done) VALUES (?, ?, ?, 0)",
            (text, due_at, recurring_rule),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_active_reminders(self):
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE done = 0 ORDER BY due_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_due_reminders(self, now: str | None = None):
        now = now or _now()
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE done = 0 AND due_at <= ? ORDER BY due_at ASC", (now,)
        ).fetchall()
        return [dict(r) for r in rows]

    def complete_or_reschedule_reminder(self, reminder_id: int, recurring_rule: str | None):
        if recurring_rule == "daily":
            row = self._conn.execute("SELECT due_at FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
            next_due = (datetime.fromisoformat(row["due_at"]) + timedelta(days=1)).isoformat(timespec="seconds")
            self._conn.execute("UPDATE reminders SET due_at = ? WHERE id = ?", (next_due, reminder_id))
        else:
            self._conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))
        self._conn.commit()

    def delete_reminder(self, reminder_id: int):
        self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self._conn.commit()

    # -- habits --------------------------------------------------------

    def upsert_habit(self, name: str, target_interval_minutes: int):
        self._conn.execute(
            "INSERT INTO habits (name, target_interval_minutes, last_triggered_at, is_paused) "
            "VALUES (?, ?, ?, 0) "
            "ON CONFLICT(name) DO UPDATE SET target_interval_minutes = excluded.target_interval_minutes",
            (name, target_interval_minutes, _now()),
        )
        self._conn.commit()

    def update_habit_triggered(self, name: str, when: str | None = None):
        self._conn.execute(
            "UPDATE habits SET last_triggered_at = ? WHERE name = ?", (when or _now(), name)
        )
        self._conn.commit()

    def get_habits(self):
        rows = self._conn.execute("SELECT * FROM habits ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]

    def get_due_habits(self):
        due = []
        for h in self.get_habits():
            if h["is_paused"] or not h["last_triggered_at"]:
                continue
            elapsed = datetime.now() - datetime.fromisoformat(h["last_triggered_at"])
            if elapsed >= timedelta(minutes=h["target_interval_minutes"]):
                due.append(h)
        return due

    def set_habit_paused(self, name: str, is_paused: bool):
        self._conn.execute("UPDATE habits SET is_paused = ? WHERE name = ?", (int(is_paused), name))
        self._conn.commit()

    def delete_habit(self, name: str):
        self._conn.execute("DELETE FROM habits WHERE name = ?", (name,))
        self._conn.commit()

    # -- conversation log --------------------------------------------------------

    def log_conversation(self, role: str, content: str):
        self._conn.execute(
            "INSERT INTO conversation_log (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, _now()),
        )
        self._conn.commit()

    def get_recent_conversation(self, limit: int = 20):
        rows = self._conn.execute(
            "SELECT * FROM conversation_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def count_conversation(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]

    def get_oldest_conversation(self, limit: int):
        rows = self._conn.execute(
            "SELECT * FROM conversation_log ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation_up_to(self, last_id: int):
        self._conn.execute("DELETE FROM conversation_log WHERE id <= ?", (last_id,))
        self._conn.commit()

    def clear_conversation(self):
        self._conn.execute("DELETE FROM conversation_log")
        self._conn.commit()

    def search_conversations(self, query: str, limit: int = 10):
        """Search past conversation turns by content. Returns matching rows newest-first."""
        rows = self._conn.execute(
            "SELECT role, content, timestamp FROM conversation_log "
            "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def clear_all(self):
        self._conn.executescript(
            "DELETE FROM memories; DELETE FROM reminders; DELETE FROM habits; DELETE FROM conversation_log;"
        )
        self._conn.commit()

    # -- context injection --------------------------------------------------------

    def get_context_snippet(self, max_memories: int = 8) -> str:
        """Short summary of what's relevant right now, for the LLM system prompt. Not a full DB dump."""
        parts = []

        reminders = self.get_active_reminders()[:5]
        if reminders:
            lines = [f"- \"{r['text']}\" due {r['due_at']}" for r in reminders]
            parts.append("Active reminders:\n" + "\n".join(lines))

        habits = [h for h in self.get_habits() if not h["is_paused"]]
        if habits:
            lines = [f"- {h['name']} (every {h['target_interval_minutes']}min)" for h in habits]
            parts.append("Tracked habits:\n" + "\n".join(lines))

        # Conversation summaries (auto-generated, high value for context)
        summaries = self._conn.execute(
            "SELECT content FROM memories WHERE category = 'conversation_summary' "
            "ORDER BY created_at DESC LIMIT 3"
        ).fetchall()
        if summaries:
            lines = [f"- {r['content']}" for r in summaries]
            parts.append("Recent conversation summaries:\n" + "\n".join(lines))

        # Other memories (exclude summaries to avoid duplication)
        memories = self._conn.execute(
            "SELECT category, content FROM memories WHERE category != 'conversation_summary' "
            "ORDER BY importance DESC, created_at DESC LIMIT ?", (max_memories,)
        ).fetchall()
        if memories:
            lines = [f"- [{m['category']}] {m['content']}" for m in memories]
            parts.append("Things you remember about the user:\n" + "\n".join(lines))

        return "\n\n".join(parts)
