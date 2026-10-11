"""
Who is asking, and are they asking too often?

  - visitor id: a random UUID the browser keeps and sends as X-Visitor-Id.
    Every chat belongs to one visitor, so people only see their own chats.
  - rate limits: per visitor and per IP address, kept in memory
    (fine because the API runs as one process).
"""
import threading
import time
import uuid
from collections import defaultdict, deque


def is_valid_id(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


class RateLimiter:
    """At most `limit` hits per key in the last 60 seconds."""

    def __init__(self, limit):
        self.limit, self.hits, self.lock = limit, defaultdict(deque), threading.Lock()

    def retry_after(self, key):
        """0 if allowed (and counts the hit), otherwise seconds to wait."""
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.limit:
                return int(60 - (now - q[0])) + 1
            q.append(now)
            return 0
