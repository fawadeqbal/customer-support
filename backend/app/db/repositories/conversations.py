"""All SQL for chats and their messages (including the running summary)."""
from psycopg.types.json import Jsonb

from app.core.security import is_valid_id
from app.db.connection import connect


def _conv(row):
    return {"id": str(row["id"]), "title": row["title"],
            "updated_at": row["updated_at"].isoformat(), "summary": row.get("summary", "")}


class ConversationRepository:
    # ---------- chats ----------
    def create(self, title, visitor_id):
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO conversations (title, visitor_id) VALUES (%s, %s) "
                "RETURNING id, title, updated_at, summary",
                (title, visitor_id),
            ).fetchone()
        return _conv(row)

    def get(self, conversation_id, visitor_id):
        """One chat - only if it belongs to this visitor."""
        if not is_valid_id(conversation_id):
            return None
        with connect() as conn:
            row = conn.execute(
                "SELECT id, title, updated_at, summary FROM conversations "
                "WHERE id = %s AND visitor_id IS NOT DISTINCT FROM %s",
                (conversation_id, visitor_id),
            ).fetchone()
        return _conv(row) if row else None

    def list(self, visitor_id, limit=50):
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, title, updated_at, summary FROM conversations "
                "WHERE visitor_id = %s ORDER BY updated_at DESC LIMIT %s",
                (visitor_id, limit),
            ).fetchall()
        return [_conv(r) for r in rows]

    def delete(self, conversation_id, visitor_id):
        with connect() as conn:   # messages are deleted too (ON DELETE CASCADE)
            conn.execute("DELETE FROM conversations WHERE id = %s AND visitor_id = %s",
                         (conversation_id, visitor_id))

    # ---------- messages ----------
    def add_message(self, conversation_id, role, content, sources=None, usage=None, author=None):
        """role: user | assistant | agent (a person, named in author) | system (a status line)."""
        with connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, sources, usage, author) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (conversation_id, role, content,
                     Jsonb(sources) if sources is not None else None,
                     Jsonb(usage) if usage is not None else None, author),
                ).fetchone()
                conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (conversation_id,))
        return row["id"]

    def messages(self, conversation_id, after=0):
        """Messages of a chat with id > after, oldest first (for showing in the UI)."""
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, sources, usage, feedback, author, created_at FROM messages "
                "WHERE conversation_id = %s AND id > %s ORDER BY id", (conversation_id, after),
            ).fetchall()
        return [{**r, "created_at": r["created_at"].isoformat()} for r in rows]

    def history(self, conversation_id, turns):
        """The last `turns` question/answer pairs, oldest first (sent to the model)."""
        with connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = %s "
                "AND role IN ('user', 'assistant') ORDER BY id DESC LIMIT %s",
                (conversation_id, turns * 2),
            ).fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        while history and history[0]["role"] != "user":   # models expect the user to speak first
            history.pop(0)
        return history

    # ---------- running summary of older messages ----------
    def messages_to_summarize(self, conversation_id, keep_turns):
        """Messages that left the word-for-word window and aren't in the summary yet."""
        with connect() as conn:
            conv = conn.execute("SELECT summary, summarized_upto FROM conversations WHERE id = %s",
                                (conversation_id,)).fetchone()
            rows = conn.execute("SELECT id, role, content FROM messages WHERE conversation_id = %s "
                                "AND role IN ('user', 'assistant') ORDER BY id", (conversation_id,)).fetchall()
        old = rows[:-keep_turns * 2] if len(rows) > keep_turns * 2 else []
        return conv["summary"], [r for r in old if r["id"] > conv["summarized_upto"]]

    def save_summary(self, conversation_id, summary, upto_id):
        with connect() as conn:
            conn.execute("UPDATE conversations SET summary = %s, summarized_upto = %s WHERE id = %s",
                         (summary, upto_id, conversation_id))

    def questions_today(self):
        with connect() as conn:
            return conn.execute(
                "SELECT count(*) AS n FROM messages WHERE role = 'assistant' "
                "AND created_at >= date_trunc('day', now())"
            ).fetchone()["n"]
