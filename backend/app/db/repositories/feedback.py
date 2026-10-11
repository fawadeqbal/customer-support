"""All SQL for feedback (thumbs up / down) and usage stats. Support tickets: tickets.py."""
from app.db.connection import connect


class FeedbackRepository:
    def set_feedback(self, message_id, visitor_id, value):
        """Save feedback on an assistant message the visitor owns. False if not theirs."""
        with connect() as conn:
            row = conn.execute(
                "UPDATE messages m SET feedback = %s FROM conversations c "
                "WHERE m.id = %s AND m.role = 'assistant' AND m.conversation_id = c.id "
                "AND c.visitor_id = %s RETURNING m.id",
                (value, message_id, visitor_id),
            ).fetchone()
        return row is not None

    def stats(self):
        with connect() as conn:
            return conn.execute("""
                SELECT
                  (SELECT count(*) FROM messages WHERE role='assistant' AND created_at >= date_trunc('day', now())) AS questions_today,
                  (SELECT coalesce(sum((usage->>'input')::int), 0) FROM messages WHERE created_at >= date_trunc('day', now())) AS input_tokens_today,
                  (SELECT coalesce(sum((usage->>'output')::int), 0) FROM messages WHERE created_at >= date_trunc('day', now())) AS output_tokens_today,
                  (SELECT count(*) FROM messages WHERE role='assistant') AS answers_total,
                  (SELECT count(*) FROM messages WHERE feedback='up') AS helpful,
                  (SELECT count(*) FROM messages WHERE feedback='down') AS not_helpful,
                  (SELECT count(*) FROM handoffs WHERE status='waiting') AS tickets_waiting,
                  (SELECT count(*) FROM handoffs WHERE status='active') AS tickets_active,
                  (SELECT count(DISTINCT visitor_id) FROM conversations WHERE updated_at >= date_trunc('day', now())) AS visitors_today
            """).fetchone()
