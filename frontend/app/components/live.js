/**
 * openLive(path, hello, { onMessage, onStatus }) - a WebSocket that reconnects by itself.
 *
 *   path      "/ws/support" or "/ws/admin"
 *   hello     first message (ids / token), sent on every (re)connect - can be a function
 *   onStatus  true when connected, false when not (callers poll as a fallback while false)
 * Returns close(); close.send(obj) sends a message while connected (typing indicators).
 *
 * Where the socket goes:
 *   NEXT_PUBLIC_WS_URL if set, else
 *   local dev (site on :3000) -> ws://<host>:5000   (Next's dev proxy doesn't pass WebSockets)
 *   production               -> same host; nginx sends /ws/ to the API
 */
export function wsUrl(path) {
  const base = process.env.NEXT_PUBLIC_WS_URL;
  if (base) return base.replace(/\/$/, "") + path;
  const { protocol, hostname, host, port } = window.location;
  if (port === "3000") return `ws://${hostname}:5000${path}`;
  return `${protocol === "https:" ? "wss" : "ws"}://${host}${path}`;
}

export function openLive(path, hello, { onMessage, onStatus } = {}) {
  let ws = null;
  let stopped = false;
  let retry = null;
  let delay = 1000;

  function connect() {
    if (stopped) return;
    try {
      ws = new WebSocket(wsUrl(path));
    } catch {
      return schedule();
    }
    ws.onopen = () => {
      delay = 1000;
      ws.send(JSON.stringify(typeof hello === "function" ? hello() : hello));
      onStatus?.(true);
    };
    ws.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      if (data.type !== "ping") onMessage?.(data);
    };
    ws.onclose = (e) => {
      onStatus?.(false);
      if (e.code === 1008) stopped = true;   // refused (wrong ticket / token): don't hammer the server
      schedule();
    };
    ws.onerror = () => ws?.close();
  }

  function schedule() {
    if (stopped) return;
    clearTimeout(retry);
    retry = setTimeout(connect, delay);
    delay = Math.min(delay * 2, 15000);
  }

  connect();
  const close = () => {
    stopped = true;
    clearTimeout(retry);
    if (ws) {
      ws.onclose = null;
      ws.close();
    }
  };
  close.send = (obj) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  };
  return close;
}

/**
 * typingNotifier(send) - call it on every keystroke; it sends {on: true} at most every 2 s
 * and {on: false} after 3 s without typing. stop() sends {on: false} right away (message sent).
 */
export function typingNotifier(send) {
  let lastOn = 0;
  let idle = null;
  function stop() {
    clearTimeout(idle);
    idle = null;
    if (lastOn) send(false);
    lastOn = 0;
  }
  function typed() {
    const now = Date.now();
    if (now - lastOn > 2000) {
      send(true);
      lastOn = now;
    }
    clearTimeout(idle);
    idle = setTimeout(stop, 3000);
  }
  typed.stop = stop;
  return typed;
}
