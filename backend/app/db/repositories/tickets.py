"""All SQL for support tickets (a "talk to a person" request waiting for, or handled by, an agent).

Status:  waiting  -> in the queue, no agent yet
         active   -> an agent claimed it and is chatting
         closed   -> finished (by the agent) or left (by the customer)
The queue maths (position, estimated wait) lives in app/support/desk.py.
"""
from app.db.connection import connect

TICKET_COLUMNS = ("h.id, h.conversation_id, h.visitor_id, h.status, h.reason, h.agent, "
                  "h.created_at, h.claimed_at, h.closed_at, h.closed_by, c.title, "
                  "h.customer_name, h.customer_email, h.issue, "
                  "(SELECT count(*) FROM ticket_files f WHERE f.handoff_id = h.id) AS file_count")


def ticket_no(ticket_id):
    return f"SE-{48000 + ticket_id}"


def _ticket(row):
    if row is None:
        return None
    t = dict(row)
    t["ticket"] = ticket_no(t["id"])
    for k in ("conversation_id", "visitor_id"):
        t[k] = str(t[k]) if t.get(k) else None
    for k in ("created_at", "claimed_at", "closed_at"):
        t[k] = t[k].isoformat() if t.get(k) else None
    return t


class TicketRepository:
    def create(self, conversation_id, visitor_id, reason, contact=None):
        """contact: {"name", "email", "issue"} from the ticket form (optional)."""
        contact = contact or {}
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO handoffs (conversation_id, visitor_id, reason, customer_name, customer_email, issue) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (conversation_id, visitor_id, reason, contact.get("name"), contact.get("email"), contact.get("issue")),
            ).fetchone()
        return self.get(row["id"])

    # ---------- attachments ----------
    def add_file(self, ticket_id, filename, content_type, data):
        with connect() as conn:
            conn.execute(
                "INSERT INTO ticket_files (handoff_id, filename, content_type, size_bytes, data) "
                "VALUES (%s, %s, %s, %s, %s)",
                (ticket_id, filename, content_type, len(data), data),
            )

    def files(self, ticket_id):
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, filename, content_type, size_bytes FROM ticket_files WHERE handoff_id = %s ORDER BY id",
                (ticket_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_file(self, file_id):
        with connect() as conn:
            row = conn.execute(
                "SELECT id, handoff_id, filename, content_type, data FROM ticket_files WHERE id = %s", (file_id,),
            ).fetchone()
        return dict(row) if row else None

    def get(self, ticket_id):
        with connect() as conn:
            row = conn.execute(
                f"SELECT {TICKET_COLUMNS} FROM handoffs h LEFT JOIN conversations c ON c.id = h.conversation_id "
                "WHERE h.id = %s", (ticket_id,),
            ).fetchone()
        return _ticket(row)

    def open_for(self, conversation_id):
        """The waiting/active ticket of a chat, if there is one."""
        if not conversation_id:
            return None
        with connect() as conn:
            row = conn.execute(
                f"SELECT {TICKET_COLUMNS} FROM handoffs h LEFT JOIN conversations c ON c.id = h.conversation_id "
                "WHERE h.conversation_id = %s AND h.status IN ('waiting', 'active') ORDER BY h.id DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return _ticket(row)

    def list(self, closed_hours=24):
        """Open tickets plus the ones closed recently, oldest first, with a preview for the admin list."""
        with connect() as conn:
            rows = conn.execute(
                f"SELECT {TICKET_COLUMNS}, "
                "  (SELECT m.content FROM messages m WHERE m.conversation_id = h.conversation_id "
                "     AND m.role = 'user' ORDER BY m.id DESC LIMIT 1) AS last_customer_message, "
                "  (SELECT m.role FROM messages m WHERE m.conversation_id = h.conversation_id "
                "     AND m.role IN ('user', 'agent') AND m.created_at >= h.created_at "
                "     ORDER BY m.id DESC LIMIT 1) AS last_role "
                "FROM handoffs h LEFT JOIN conversations c ON c.id = h.conversation_id "
                "WHERE h.status IN ('waiting', 'active') OR h.closed_at > now() - make_interval(hours => %s) "
                "ORDER BY h.id",
                (closed_hours,),
            ).fetchall()
        return [_ticket(r) for r in rows]

    def waiting_ids(self):
        with connect() as conn:
            rows = conn.execute("SELECT id FROM handoffs WHERE status = 'waiting' ORDER BY id").fetchall()
        return [r["id"] for r in rows]

    def active_count(self):
        with connect() as conn:
            return conn.execute("SELECT count(*) AS n FROM handoffs WHERE status = 'active'").fetchone()["n"]

    def avg_handle_minutes(self, last=20):
        """Average minutes from claim to close over the last tickets an agent finished (None if none yet)."""
        with connect() as conn:
            row = conn.execute(
                "SELECT avg(extract(epoch FROM closed_at - claimed_at)) / 60 AS m FROM ("
                "  SELECT claimed_at, closed_at FROM handoffs WHERE claimed_at IS NOT NULL "
                "  AND closed_at IS NOT NULL ORDER BY id DESC LIMIT %s) t", (last,),
            ).fetchone()
        return float(row["m"]) if row and row["m"] is not None else None

    def claim(self, ticket_id, agent):
        """waiting -> active. None if someone else got it first or it is closed."""
        with connect() as conn:
            row = conn.execute(
                "UPDATE handoffs SET status = 'active', agent = %s, claimed_at = now() "
                "WHERE id = %s AND status = 'waiting' RETURNING id", (agent, ticket_id),
            ).fetchone()
        return self.get(ticket_id) if row else None

    def close(self, ticket_id, closed_by):
        with connect() as conn:
            row = conn.execute(
                "UPDATE handoffs SET status = 'closed', closed_at = now(), closed_by = %s "
                "WHERE id = %s AND status <> 'closed' RETURNING id", (closed_by, ticket_id),
            ).fetchone()
        return self.get(ticket_id) if row else None

    def counts(self):
        with connect() as conn:
            return conn.execute(
                "SELECT count(*) FILTER (WHERE status = 'waiting') AS waiting, "
                "       count(*) FILTER (WHERE status = 'active') AS active, "
                "       count(*) FILTER (WHERE status = 'closed' AND closed_at >= date_trunc('day', now())) AS closed_today, "
                "       round(avg(extract(epoch FROM claimed_at - created_at)) FILTER "
                "             (WHERE claimed_at >= now() - interval '1 day'))::int AS avg_wait_seconds "
                "FROM handoffs"
            ).fetchone()
