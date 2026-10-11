"use client";
/**
 * /admin - the support console for human agents.
 *
 *   sign in      agent name + ADMIN_TOKEN (checked against /api/admin/stats, kept for this tab only)
 *   queue        waiting tickets in order (No. 1 = next), active chats, recently closed
 *   ticket       the whole chat (assistant answers included), Take / reply / Close
 *
 * Live: a WebSocket (/ws/admin) says "something changed" and the console reloads what it
 * shows; while the socket is down it polls every 3 s instead. API: backend/app/api/admin.py
 */
import { useEffect, useRef, useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { openLive, typingNotifier } from "../components/live";

const QUICK_REPLIES = [
  "Hi! Thanks for waiting. Let me look into this for you.",
  "Could you share your order number (it starts with SE)?",
  "I've checked this and I'll update you in a moment.",
  "Is there anything else I can help you with?",
];

const TABS = [
  { key: "waiting", label: "Queue" },
  { key: "active", label: "Active" },
  { key: "closed", label: "Closed" },
];

function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem("agent-session") || "null");
  } catch {
    return null;
  }
}

function saveSession(value) {
  try {
    if (value) sessionStorage.setItem("agent-session", JSON.stringify(value));
    else sessionStorage.removeItem("agent-session");
  } catch {
    /* storage blocked: the session lasts until the page is closed */
  }
}

function since(iso) {
  return iso ? duration((Date.now() - new Date(iso).getTime()) / 1000) : "";
}

function duration(seconds) {
  const s = Math.max(0, seconds);
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
  return `${Math.floor(s / 86400)} d`;
}

function clock(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function AdminPage() {
  const [session, setSession] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setSession(loadSession());
    setReady(true);
  }, []);

  if (!ready) return null;
  if (!session) {
    return <SignIn onDone={(s) => { saveSession(s); setSession(s); }} />;
  }
  return <Console session={session} onSignOut={() => { saveSession(null); setSession(null); }} />;
}

// ---------- calls to /api/admin/* with the token ----------
function useAdminApi(session, onUnauthorized) {
  return async function call(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.token}`, ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 403) onUnauthorized?.();
    if (!res.ok) throw new Error(data.error || `The server answered with status ${res.status}.`);
    return data;
  };
}

// ---------- sign in ----------
function SignIn({ onDone }) {
  const [agent, setAgent] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!agent.trim() || !token.trim()) return setError("Enter your name and the admin token.");
    setChecking(true);
    setError("");
    try {
      const res = await fetch("/api/admin/stats", { headers: { Authorization: `Bearer ${token.trim()}` } });
      if (res.status === 403) throw new Error("That token isn't right. It's ADMIN_TOKEN in the backend .env file.");
      if (!res.ok) throw new Error("The API isn't answering. Is the backend running?");
      onDone({ agent: agent.trim().slice(0, 40), token: token.trim() });
    } catch (err) {
      setError(err instanceof TypeError ? "The API isn't answering. Is the backend running?" : err.message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="adm-signin">
      <form className="adm-signin-card" onSubmit={submit}>
        <div className="adm-brand">
          <span className="mark" aria-hidden>S</span>
          <span className="brand-name">ShopEase</span>
          <span className="badge">Support console</span>
        </div>
        <h1>Sign in to answer customers</h1>
        <p className="adm-muted">Customers who ask for a person wait in the queue here. Take a ticket and reply in their chat.</p>
        <label htmlFor="agent-name">Your name</label>
        <input id="agent-name" value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="e.g. Ali" autoComplete="name" />
        <label htmlFor="admin-token">Admin token</label>
        <input id="admin-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ADMIN_TOKEN" autoComplete="current-password" />
        {error && <p className="adm-error" role="alert">{error}</p>}
        <button className="btn-accent block" disabled={checking}>{checking ? "Checking…" : "Sign in"}</button>
        <a href="/" className="adm-back">← Back to the store</a>
      </form>
    </main>
  );
}

// ---------- the console ----------
function Console({ session, onSignOut }) {
  const call = useAdminApi(session, onSignOut);
  const [tickets, setTickets] = useState([]);
  const [stats, setStats] = useState(null);
  const [tab, setTab] = useState("waiting");
  const [selected, setSelected] = useState(null);       // ticket id
  const [offline, setOffline] = useState(false);
  const [live, setLive] = useState(false);              // WebSocket connected
  const [version, setVersion] = useState(0);            // bumps on every pushed change -> open ticket reloads
  const [typing, setTyping] = useState({});             // ticket id -> customer is typing
  const liveRef = useRef(null);
  const typingTimers = useRef({});
  const [, tick] = useState(0);                          // re-render so "waiting 3 min" stays current

  async function refresh() {
    try {
      const [list, s] = await Promise.all([call("/api/admin/tickets"), call("/api/admin/stats")]);
      setTickets(list);
      setStats(s);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }

  useEffect(() => {
    refresh();
    const clock = setInterval(() => tick((n) => n + 1), 15000);
    const close = openLive("/ws/admin", { token: session.token }, {
      onMessage: (msg) => {
        if (msg.type === "changed") {
          refresh();
          setVersion((v) => v + 1);
          if (msg.kind === "message") setTyping((t) => ({ ...t, [msg.ticket_id]: false }));
        }
        if (msg.type === "typing") {
          const id = msg.ticket_id;
          clearTimeout(typingTimers.current[id]);
          setTyping((t) => ({ ...t, [id]: msg.on }));
          if (msg.on) typingTimers.current[id] = setTimeout(() => setTyping((t) => ({ ...t, [id]: false })), 6000);
        }
      },
      onStatus: (connected) => {
        setLive(connected);
        if (connected) refresh();             // catch up on anything missed while disconnected
      },
    });
    liveRef.current = close;
    return () => { clearInterval(clock); close(); liveRef.current = null; };
  }, []);

  // Fallback: poll while the socket is down
  useEffect(() => {
    if (live) return;
    const timer = setInterval(() => { refresh(); setVersion((v) => v + 1); }, 3000);
    return () => clearInterval(timer);
  }, [live]);

  const byTab = {
    waiting: tickets.filter((t) => t.status === "waiting"),
    active: tickets.filter((t) => t.status === "active"),
    closed: tickets.filter((t) => t.status === "closed").reverse(),
  };
  const current = tickets.find((t) => t.id === selected) || null;
  const helpfulRate = stats && stats.helpful + stats.not_helpful > 0
    ? `${Math.round((stats.helpful / (stats.helpful + stats.not_helpful)) * 100)}%` : "–";

  return (
    <div className={`adm${selected ? " has-selection" : ""}`}>
      <header className="adm-head">
        <a href="/" className="adm-brand" aria-label="Back to the store">
          <span className="mark" aria-hidden>S</span>
          <span className="brand-name">ShopEase</span>
          <span className="badge">Support console</span>
        </a>
        <div className="adm-head-right">
          {offline && <span className="adm-offline">API not reachable</span>}
          <span className={`adm-live${live ? " on" : ""}`} title={live ? "Updates arrive instantly (WebSocket)" : "Reconnecting… checking every 3 seconds"}>
            {live ? "Live" : "Reconnecting"}
          </span>
          <span className="adm-me"><span className="live-dot small" aria-hidden />{session.agent}</span>
          <ThemeToggle />
          <button className="adm-ghost" onClick={onSignOut}>Sign out</button>
        </div>
      </header>

      <section className="adm-stats" aria-label="Today at a glance">
        <Stat label="Waiting" value={stats?.waiting ?? "–"} tone={stats?.waiting ? "warn" : ""} />
        <Stat label="In a chat" value={stats ? `${stats.active} / ${stats.agents_on_shift}` : "–"} hint="agents busy / on shift" />
        <Stat label="Avg wait today" value={stats?.avg_wait_seconds != null ? duration(stats.avg_wait_seconds) : "–"} />
        <Stat label="Closed today" value={stats?.closed_today ?? "–"} />
        <Stat label="Bot answers today" value={stats ? `${stats.questions_today} / ${stats.daily_cap}` : "–"} hint="of the daily cap" />
        <Stat label="Rated helpful" value={helpfulRate} />
      </section>

      <div className="adm-body">
        <aside className="adm-list" aria-label="Tickets">
          <div className="adm-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                className={tab === t.key ? "on" : ""}
                onClick={() => setTab(t.key)}
              >
                {t.label}<span className="adm-count">{byTab[t.key].length}</span>
              </button>
            ))}
          </div>
          <ul>
            {byTab[tab].length === 0 && (
              <li className="adm-empty">
                {tab === "waiting" ? "No one is waiting. New requests appear here the moment a customer asks for a person."
                  : tab === "active" ? "No chats in progress. Take a ticket from the queue."
                  : "Nothing closed in the last 24 hours."}
              </li>
            )}
            {byTab[tab].map((t) => (
              <li key={t.id}>
                <button className={`adm-item${t.id === selected ? " on" : ""}`} onClick={() => setSelected(t.id)}>
                  <span className="adm-item-top">
                    {t.status === "waiting" && <span className="adm-pos">No. {t.position}</span>}
                    {typing[t.id] ? <span className="adm-typing">typing…</span>
                      : t.status === "active" && t.last_role === "user" && <span className="adm-unread">New message</span>}
                    <span className="adm-ticket">{t.ticket}</span>
                    <span className="adm-time">
                      {t.status === "waiting" ? `waiting ${since(t.created_at)}`
                        : t.status === "active" ? t.agent
                        : `closed ${since(t.closed_at)} ago`}
                    </span>
                  </span>
                  <span className="adm-item-title">
                    {t.customer_name || t.title || "Chat without messages"}
                    {t.file_count > 0 && <span className="adm-clip" title={`${t.file_count} attachment(s)`}>📎 {t.file_count}</span>}
                  </span>
                  <span className="adm-item-preview">{t.status === "active" && t.last_role === "user" ? t.last_customer_message : t.issue || t.last_customer_message || t.reason}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="adm-detail" aria-label="Ticket">
          {current ? (
            <TicketView key={current.id} ticket={current} session={session} call={call} version={version}
              customerTyping={!!typing[current.id]}
              sendTyping={(on) => liveRef.current?.send({ type: "typing", ticket_id: current.id, agent: session.agent, on })}
              onChanged={refresh} onBack={() => setSelected(null)} />
          ) : (
            <div className="adm-placeholder">
              <p className="mono-label">NO TICKET OPEN</p>
              <h2>{byTab.waiting.length ? `${byTab.waiting.length} customer${byTab.waiting.length === 1 ? " is" : "s are"} waiting` : "All caught up"}</h2>
              <p className="adm-muted">
                {byTab.waiting.length ? "Open the first ticket in the queue and take it. The customer sees you join right away."
                  : "When a customer clicks “Talk to a person”, their ticket shows up in the queue."}
              </p>
              {byTab.waiting[0] && (
                <button className="btn-accent" onClick={() => { setTab("waiting"); setSelected(byTab.waiting[0].id); }}>
                  Open {byTab.waiting[0].ticket}
                </button>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value, hint, tone }) {
  return (
    <div className={`adm-stat${tone ? ` ${tone}` : ""}`} title={hint}>
      <span className="adm-stat-label">{label}</span>
      <span className="adm-stat-value">{value}</span>
    </div>
  );
}

// ---------- one ticket: transcript + actions ----------
function TicketView({ ticket, session, call, version, customerTyping, sendTyping, onChanged, onBack }) {
  const [messages, setMessages] = useState([]);
  const [files, setFiles] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const lastId = useRef(0);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const typed = useRef(null);
  if (!typed.current) typed.current = typingNotifier((on) => sendTyping(on));
  useEffect(() => () => typed.current.stop(), []);

  async function load() {
    try {
      const data = await call(`/api/admin/tickets/${ticket.id}?after=${lastId.current}`);
      setFiles(data.files || []);
      if (data.messages.length) {
        lastId.current = data.messages[data.messages.length - 1].id;
        setMessages((prev) => {
          const have = new Set(prev.map((m) => m.id));
          return [...prev, ...data.messages.filter((m) => !have.has(m.id))];
        });
      }
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => { load(); }, [ticket.id, version]);   // version changes when the server pushes a change

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages.length, customerTyping]);

  async function act(path, body) {
    setWorking(true);
    setError("");
    try {
      await call(`/api/admin/tickets/${ticket.id}/${path}`, { method: "POST", body: JSON.stringify(body) });
      await Promise.all([load(), onChanged()]);
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setWorking(false);
    }
  }

  // Attachments need the admin token, so fetch them and open the result in a new tab
  async function openFile(f) {
    try {
      const res = await fetch(`/api/admin/files/${f.id}`, { headers: { Authorization: `Bearer ${session.token}` } });
      if (!res.ok) throw new Error("Couldn't open that file.");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      if (!f.content_type.startsWith("image/") && f.content_type !== "application/pdf") a.download = f.filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      setError(err.message);
    }
  }

  async function reply(e) {
    e?.preventDefault();
    const message = text.trim();
    if (!message) return;
    typed.current.stop();
    if (await act("messages", { agent: session.agent, message })) {
      setText("");
      inputRef.current?.focus();
    }
  }

  const mine = ticket.status === "active";
  const askedAt = new Date(ticket.created_at).getTime();   // messages before this were with the assistant

  return (
    <div className="adm-ticket-view">
      <div className="adm-ticket-head">
        <button className="adm-ghost adm-back-btn" onClick={onBack} aria-label="Back to the list">←</button>
        <div className="adm-ticket-title">
          <p className="mono-label">
            {ticket.ticket} · <span className={`adm-status ${ticket.status}`}>{ticket.status === "waiting" ? `waiting · No. ${ticket.position}` : ticket.status === "active" ? `with ${ticket.agent}` : "closed"}</span>
          </p>
          <h2>{ticket.customer_name || ticket.title || "Chat"}</h2>
          {ticket.customer_email && <p className="adm-contact">{ticket.customer_email}</p>}
          <p className="adm-muted small">
            Asked {since(ticket.created_at)} ago
            {ticket.claimed_at ? ` · waited ${duration((new Date(ticket.claimed_at) - new Date(ticket.created_at)) / 1000)}` : ""}
            {!ticket.issue && ticket.reason ? ` · “${ticket.reason.slice(0, 90)}”` : ""}
          </p>
        </div>
        <div className="adm-actions">
          {ticket.status === "waiting" && (
            <button className="btn-accent" disabled={working} onClick={() => act("claim", { agent: session.agent })}>Take ticket</button>
          )}
          {ticket.status === "active" && (
            <button className="adm-ghost" disabled={working} onClick={() => act("close", { agent: session.agent })}>Close ticket</button>
          )}
        </div>
      </div>

      {(ticket.issue || files.length > 0) && (
        <div className="adm-issue">
          <span className="adm-who">Issue from the ticket form</span>
          {ticket.issue && <p>{ticket.issue}</p>}
          {files.length > 0 && (
            <ul className="adm-files">
              {files.map((f) => (
                <li key={f.id}>
                  <button type="button" onClick={() => openFile(f)}>
                    <span className="adm-file-kind">{f.content_type === "application/pdf" ? "PDF" : f.content_type.startsWith("image/") ? "IMG" : "TXT"}</span>
                    <span className="adm-file-name">{f.filename}</span>
                    <small>{Math.max(1, Math.round(f.size_bytes / 1024))} KB</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="adm-transcript">
        {messages.length === 0 && <p className="adm-muted">This ticket has no chat messages.</p>}
        {messages.map((m) => (
          <Line key={m.id} m={m} earlier={new Date(m.created_at).getTime() < askedAt - 1000} />
        ))}
        {customerTyping && ticket.status !== "closed" && (
          <div className="adm-line user" aria-live="polite">
            <span className="adm-who">{ticket.customer_name || "Customer"} is typing…</span>
            <div className="adm-bubble adm-dots" aria-hidden><i /><i /><i /></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="adm-error" role="alert">{error}</p>}

      {ticket.status === "closed" ? (
        <p className="adm-closed-note">Closed by {ticket.closed_by === "customer" ? "the customer" : ticket.closed_by}. The assistant answers this chat again.</p>
      ) : (
        <form className="adm-reply" onSubmit={reply}>
          {mine && (
            <div className="adm-quick">
              {QUICK_REPLIES.map((q) => (
                <button type="button" key={q} className="chip" onClick={() => { setText(q); inputRef.current?.focus(); }}>{q}</button>
              ))}
            </div>
          )}
          <div className="adm-reply-row">
            <textarea
              ref={inputRef}
              id="agent-reply"
              rows={2}
              value={text}
              disabled={!mine}
              placeholder={mine ? `Reply as ${ticket.agent}  (Enter to send, Shift+Enter for a new line)` : "Take the ticket to reply"}
              onChange={(e) => {
                setText(e.target.value);
                if (mine && e.target.value) typed.current();
              }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); reply(); } }}
            />
            <button className="btn-accent" disabled={!mine || working || !text.trim()}>Send</button>
          </div>
        </form>
      )}
    </div>
  );
}

function Line({ m, earlier }) {
  if (m.role === "system") return <p className="adm-sys">{m.content} · {clock(m.created_at)}</p>;
  const who = m.role === "user" ? "Customer" : m.role === "agent" ? m.author || "Agent" : "Assistant";
  return (
    <div className={`adm-line ${m.role}${earlier ? " before" : ""}`}>
      <span className="adm-who">{who} · {clock(m.created_at)}</span>
      <div className="adm-bubble">{m.content}</div>
      {m.role === "assistant" && m.sources?.length > 0 && (
        <span className="adm-sources">{m.sources.length} handbook passages · p.{[...new Set(m.sources.map((s) => s.page))].join(", ")}</span>
      )}
    </div>
  );
}
