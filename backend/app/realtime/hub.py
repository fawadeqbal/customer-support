"""
A tiny in-process message bus. Something changed -> every open WebSocket hears about it.

    hub.publish({"type": "ticket", "ticket_id": 7})     # queue / status changed
    hub.publish({"type": "message", "ticket_id": 7})    # new chat message on a ticket
    hub.publish({"type": "typing", "ticket_id": 7, "who": "agent", "name": "Ali", "on": True})

Each socket handler (app/api/live.py) has its own queue and decides what to send to
its browser. The API runs as ONE process (see Dockerfile), so in-memory is enough.
With several processes you would swap this for Postgres LISTEN/NOTIFY or Redis pub/sub.
"""
import queue
import threading


class Hub:
    def __init__(self):
        self._lock = threading.Lock()
        self._queues = set()

    def subscribe(self):
        q = queue.Queue(maxsize=200)
        with self._lock:
            self._queues.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._queues.discard(q)

    def publish(self, event):
        with self._lock:
            targets = list(self._queues)
        for q in targets:
            try:
                q.put_nowait(event)
            except queue.Full:          # a stuck client must not slow everyone else down
                pass

    @property
    def listeners(self):
        return len(self._queues)


hub = Hub()
