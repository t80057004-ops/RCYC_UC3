"""SQLite persistence for authenticated guest conversations, messages, and reply feedback."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


MAX_TITLE_LENGTH = 80


def utc_now_iso(offset_microseconds: int = 0) -> str:
    """Return fixed-width UTC ISO-8601 timestamp string suitable for lexicographical ordering."""
    dt = datetime.now(timezone.utc) + timedelta(microseconds=offset_microseconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize_title(raw_title: str) -> str:
    """Trim whitespace and collapse internal spacing for conversation titles."""
    return re.sub(r"\s+", " ", str(raw_title or "").strip())


def auto_title_from_message(message: str) -> str:
    """Build an initial title from the first 6 words of the guest's first message."""
    collapsed = normalize_title(message)
    if not collapsed:
        return "New chat"
    words = collapsed.split(" ")[:6]
    candidate = " ".join(words).strip()
    if len(candidate) > MAX_TITLE_LENGTH:
        candidate = candidate[:MAX_TITLE_LENGTH].rstrip()
    return candidate or "New chat"


def escape_like_query(query: str) -> str:
    """Escape SQL LIKE wildcard characters so user search input is matched literally."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ChatStore:
    """Thread-safe SQLite store scoped strictly by session Customer ID."""

    def __init__(self, db_path: Path, retention_days: int = 30) -> None:
        self.db_path = Path(db_path)
        self.retention_days = max(int(retention_days or 30), 1)
        self._lock = threading.RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        customer_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversations_customer_updated
                    ON conversations (customer_id, updated_at DESC)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                        text TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_voyages TEXT NOT NULL DEFAULT '[]'
                    )
                    """
                )
                existing_msg_cols = {
                    str(row["name"])
                    for row in conn.execute("PRAGMA table_info(messages)").fetchall()
                }
                if "last_voyages" not in existing_msg_cols:
                    conn.execute("ALTER TABLE messages ADD COLUMN last_voyages TEXT NOT NULL DEFAULT '[]'")
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_messages_conv_created
                    ON messages (conversation_id, created_at ASC)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS message_feedback (
                        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                        customer_id TEXT NOT NULL,
                        vote TEXT NOT NULL CHECK(vote IN ('up', 'down')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (message_id, customer_id)
                    )
                    """
                )
                conn.commit()

    def cleanup_expired(
        self,
        retention_days: int | None = None,
        now: datetime | None = None,
    ) -> int:
        """Delete conversations older than retention_days (cascades messages and feedback)."""
        days = max(int(retention_days if retention_days is not None else self.retention_days), 1)
        ref_now = now if now is not None else datetime.now(timezone.utc)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=timezone.utc)
        cutoff = (ref_now - timedelta(days=days)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM conversations WHERE updated_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return int(cur.rowcount or 0)

    def list_conversations(self, customer_id: str, query: str | None = None) -> list[dict[str, Any]]:
        """List conversations for customer_id newest first, optionally filtered by title or message text."""
        q_clean = normalize_title(query or "")
        with self._lock:
            with self._connect() as conn:
                if q_clean:
                    pattern = f"%{escape_like_query(q_clean)}%"
                    rows = conn.execute(
                        """
                        SELECT c.id, c.title, c.created_at, c.updated_at
                        FROM conversations c
                        WHERE c.customer_id = ?
                          AND (
                            LOWER(c.title) LIKE LOWER(?) ESCAPE '\\'
                            OR EXISTS (
                              SELECT 1 FROM messages m
                              WHERE m.conversation_id = c.id
                                AND LOWER(m.text) LIKE LOWER(?) ESCAPE '\\'
                            )
                          )
                        ORDER BY c.updated_at DESC, c.rowid DESC
                        """,
                        (customer_id, pattern, pattern),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, title, created_at, updated_at
                        FROM conversations
                        WHERE customer_id = ?
                        ORDER BY updated_at DESC, rowid DESC
                        """,
                        (customer_id,),
                    ).fetchall()
                return [
                    {
                        "id": str(r["id"]),
                        "title": str(r["title"]),
                        "created_at": str(r["created_at"]),
                        "updated_at": str(r["updated_at"]),
                    }
                    for r in rows
                ]

    def create_conversation(self, customer_id: str, title: str = "New chat") -> dict[str, Any]:
        """Create an empty conversation owned by customer_id."""
        conv_id = f"conv_{uuid.uuid4().hex[:16]}"
        clean_title = normalize_title(title)[:MAX_TITLE_LENGTH] or "New chat"
        now_iso = utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO conversations (id, customer_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (conv_id, customer_id, clean_title, now_iso, now_iso),
                )
                conn.commit()
        return {
            "id": conv_id,
            "title": clean_title,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    def get_conversation(self, customer_id: str, conversation_id: str) -> dict[str, Any] | None:
        """Return conversation details and chronological messages if owned by customer_id."""
        with self._lock:
            with self._connect() as conn:
                conv_row = conn.execute(
                    """
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    WHERE id = ? AND customer_id = ?
                    """,
                    (conversation_id, customer_id),
                ).fetchone()
                if conv_row is None:
                    return None

                msg_rows = conn.execute(
                    """
                    SELECT m.id, m.role, m.text, m.created_at, f.vote
                    FROM messages m
                    LEFT JOIN message_feedback f
                      ON f.message_id = m.id AND f.customer_id = ?
                    WHERE m.conversation_id = ?
                    ORDER BY m.created_at ASC, m.rowid ASC
                    """,
                    (customer_id, conversation_id),
                ).fetchall()

                return {
                    "id": str(conv_row["id"]),
                    "title": str(conv_row["title"]),
                    "created_at": str(conv_row["created_at"]),
                    "updated_at": str(conv_row["updated_at"]),
                    "messages": [
                        {
                            "id": str(m["id"]),
                            "role": str(m["role"]),
                            "text": str(m["text"]),
                            "created_at": str(m["created_at"]),
                            "vote": str(m["vote"]) if m["vote"] in {"up", "down"} else None,
                        }
                        for m in msg_rows
                    ],
                }

    def get_recent_context(
        self,
        customer_id: str,
        conversation_id: str,
        limit: int = 8,
    ) -> tuple[list[dict[str, Any]], list[str]] | None:
        """Load up to the last `limit` messages and latest MARIS last_voyages for an owned conversation."""
        safe_limit = max(int(limit or 8), 1)
        with self._lock:
            with self._connect() as conn:
                conv_row = conn.execute(
                    """
                    SELECT id
                    FROM conversations
                    WHERE id = ? AND customer_id = ?
                    """,
                    (conversation_id, customer_id),
                ).fetchone()
                if conv_row is None:
                    return None

                msg_rows = conn.execute(
                    """
                    SELECT id, role, text, created_at, last_voyages
                    FROM (
                        SELECT id, role, text, created_at, last_voyages, rowid AS _rid
                        FROM messages
                        WHERE conversation_id = ?
                        ORDER BY created_at DESC, rowid DESC
                        LIMIT ?
                    )
                    ORDER BY created_at ASC, _rid ASC
                    """,
                    (conversation_id, safe_limit),
                ).fetchall()

                def _parse_voyages(raw: Any) -> list[str]:
                    try:
                        parsed = json.loads(str(raw or "[]"))
                        if isinstance(parsed, list):
                            return list(dict.fromkeys(str(x).strip() for x in parsed if str(x or "").strip()))
                    except Exception:
                        pass
                    return []

                messages: list[dict[str, Any]] = []
                last_voyages: list[str] = []
                for m in msg_rows:
                    vids = _parse_voyages(m["last_voyages"])
                    role = str(m["role"])
                    if role == "assistant":
                        last_voyages = vids
                    messages.append(
                        {
                            "id": str(m["id"]),
                            "role": role,
                            "text": str(m["text"]),
                            "created_at": str(m["created_at"]),
                            "last_voyages": vids,
                        }
                    )
                return messages, last_voyages

    def rename_conversation(self, customer_id: str, conversation_id: str, title: str) -> dict[str, Any] | None:
        """Rename a conversation owned by customer_id."""
        clean_title = normalize_title(title)
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE conversations
                    SET title = ?
                    WHERE id = ? AND customer_id = ?
                    """,
                    (clean_title, conversation_id, customer_id),
                )
                if not cur.rowcount:
                    return None
                row = conn.execute(
                    """
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    WHERE id = ? AND customer_id = ?
                    """,
                    (conversation_id, customer_id),
                ).fetchone()
                conn.commit()
                if row is None:
                    return None
                return {
                    "id": str(row["id"]),
                    "title": str(row["title"]),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                }

    def delete_conversation(self, customer_id: str, conversation_id: str) -> bool:
        """Delete a conversation owned by customer_id."""
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM conversations WHERE id = ? AND customer_id = ?",
                    (conversation_id, customer_id),
                )
                conn.commit()
                return bool(cur.rowcount)

    def append_exchange(
        self,
        customer_id: str,
        conversation_id: str | None,
        user_text: str,
        assistant_text: str,
        assistant_voyage_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Attach a guest/MARIS message pair to an owned conversation (creating one if None)."""
        t_user = utc_now_iso(0)
        t_assistant = utc_now_iso(1)
        user_msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        assistant_msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        clean_vids = list(
            dict.fromkeys(
                str(vid).strip()
                for vid in (assistant_voyage_ids or [])
                if str(vid or "").strip()
            )
        )
        vids_json = json.dumps(clean_vids)

        with self._lock:
            with self._connect() as conn:
                if conversation_id is None:
                    conv_id = f"conv_{uuid.uuid4().hex[:16]}"
                    conv_title = auto_title_from_message(user_text)
                    conn.execute(
                        """
                        INSERT INTO conversations (id, customer_id, title, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (conv_id, customer_id, conv_title, t_user, t_assistant),
                    )
                else:
                    conv_row = conn.execute(
                        """
                        SELECT id, title
                        FROM conversations
                        WHERE id = ? AND customer_id = ?
                        """,
                        (conversation_id, customer_id),
                    ).fetchone()
                    if conv_row is None:
                        return None
                    conv_id = str(conv_row["id"])
                    conv_title = str(conv_row["title"])
                    existing_count = conn.execute(
                        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                        (conv_id,),
                    ).fetchone()[0]
                    if existing_count == 0 and conv_title == "New chat":
                        conv_title = auto_title_from_message(user_text)
                        conn.execute(
                            "UPDATE conversations SET title = ? WHERE id = ? AND customer_id = ?",
                            (conv_title, conv_id, customer_id),
                        )

                conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, text, created_at, last_voyages)
                    VALUES (?, ?, 'user', ?, ?, '[]')
                    """,
                    (user_msg_id, conv_id, user_text, t_user),
                )
                conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, text, created_at, last_voyages)
                    VALUES (?, ?, 'assistant', ?, ?, ?)
                    """,
                    (assistant_msg_id, conv_id, assistant_text, t_assistant, vids_json),
                )
                conn.execute(
                    """
                    UPDATE conversations
                    SET updated_at = ?
                    WHERE id = ? AND customer_id = ?
                    """,
                    (t_assistant, conv_id, customer_id),
                )
                conn.commit()

        return {
            "conversation_id": conv_id,
            "conversation_title": conv_title,
            "user_message_id": user_msg_id,
            "assistant_message_id": assistant_msg_id,
            "user_created_at": t_user,
            "assistant_created_at": t_assistant,
        }

    def upsert_feedback(
        self,
        customer_id: str,
        conversation_id: str,
        message_id: str,
        vote: str,
    ) -> dict[str, str] | None:
        """Upsert helpful/not-helpful feedback for an assistant message owned by customer_id."""
        now_iso = utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT m.role
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE m.id = ? AND m.conversation_id = ? AND c.customer_id = ?
                    """,
                    (message_id, conversation_id, customer_id),
                ).fetchone()
                if row is None:
                    return None
                if str(row["role"]) != "assistant":
                    raise ValueError("Feedback is only supported on MARIS replies.")

                conn.execute(
                    """
                    INSERT INTO message_feedback (conversation_id, message_id, customer_id, vote, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id, customer_id) DO UPDATE SET
                        vote = excluded.vote,
                        updated_at = excluded.updated_at
                    """,
                    (conversation_id, message_id, customer_id, vote, now_iso, now_iso),
                )
                conn.commit()

        return {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "vote": vote,
        }
