"use client";
/**
 * SupportWidget - the RAG customer-support chat as a slide-out panel.
 * Closed by default; the "Support" tab on the right edge opens it.
 *
 * FLOW for every question:
 *   1. POST { conversation_id, message } to /api/chat/stream
 *   2. the server streams events back (Server-Sent Events):
 *        meta   -> search query used + retrieved passages   (trace moves to "Writing")
 *        tool   -> Claude looked something up (e.g. an order)
 *        delta  -> the next few words of the answer         (shown as they arrive)
 *        done   -> message id, token usage, chat id
 *   3. sources (collapsed), feedback and follow-ups appear under the answer
 *
 * Every request sends X-Visitor-Id (a random id kept in this browser), so each
 * visitor only ever sees their own chats.
 *
 * TALK TO A PERSON: the customer fills in a short form (name, email, issue, files) and the
 * chat joins a support queue (POST /api/handoff, multipart). While the ticket
 * is open, a WebSocket (/ws/support) pushes its place in line and the agent's replies
 * the moment they happen (polling /api/handoff/<id> is the fallback if the socket drops).
 * Messages go to the agent instead of the assistant. Agents work in /admin.
 *
 * Other components open it with:  openSupport("optional question")
 */
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { openLive, typingNotifier } from "./live";

export function openSupport(question) {
  window.dispatchEvent(new CustomEvent("support:open", { detail: { question } }));
}

const SUGGESTIONS = [
  "Where is my order SE10482931?",
  "What payment methods do you accept?",
  "How do I return a product?",
  "Refund kitne din mein milta hai?",
];

// Related questions to offer after an answer, picked by keywords in the question
const FOLLOWUPS = [
  [/deduct|charged|no order/i, ["Talk to a person", "What payment methods do you accept?"]],
  [/refund/i, ["How do I return a product?", "Money was deducted but no order was placed"]],
  [/return|earbud|don.?t like/i, ["When will I get my refund?", "How do I claim warranty?"]],
  [/cancel/i, ["When will I get my refund?", "How can I track my order?"]],
  [/track|where.*order|status/i, ["Can I cancel my order?", "How long does delivery take?"]],
  [/pay|install|card|cash|wallet/i, ["Money was deducted but no order was placed", "How much does delivery cost?"]],
  [/deliver|ship|how long|cost|charge|cit(y|ies)/i, ["How can I track my order?", "What payment methods do you accept?"]],
  [/password|otp|account|log ?in|sign/i, ["Talk to a person", "How can I track my order?"]],
  [/warrant|pta|authentic|genuine/i, ["How do I return a product?", "Talk to a person"]],
  [/gift|voucher|reward|point/i, ["What payment methods do you accept?", "How do I return a product?"]],
];

function followupsFor(question, hasSources) {
  if (!hasSources) return ["Talk to a person"];
  const hit = FOLLOWUPS.find(([re]) => re.test(question));
  return (hit ? hit[1] : []).filter((q) => q.toLowerCase() !== question.toLowerCase());
}

// A short readable title for a PDF chunk (skips the page header/footer lines)
function chunkTitle(text) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean)
    .filter((l) => !/^ShopEase Customer Support Handbook$/i.test(l) && !/^Page \d+$/i.test(l));
  const line = lines.find((l) => l.length <= 48) || lines[0] || "Handbook passage";
  return line.replace(/^\d+\.\s*/, "");
}

const TRACE_STEPS = ["Understanding question", "Searching handbook", "Ranking passages", "Writing answer"];

// Anonymous id for this browser: the server only shows chats that belong to it
function visitorId() {
  try {
    let id = localStorage.getItem("visitor-id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("visitor-id", id);
    }
    return id;
  } catch {
    if (!window.__visitorId) window.__visitorId = crypto.randomUUID(); // storage blocked: this visit only
    return window.__visitorId;
  }
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Visitor-Id": visitorId(), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `The server answered with status ${res.status}.`);
  return data;
}

// Reads a Server-Sent Events stream and calls onEvent(name, data) for each event
async function readEvents(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message", data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent(event, JSON.parse(data));
    }
  }
}

// "5:32 PM" today, "10 Oct, 5:32 PM" on another day
function clock(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return d.toDateString() === new Date().toDateString()
    ? time : `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${time}`;
}
const now = () => new Date().toISOString();

// One saved message from the server -> what the thread renders
function fromServer(r, lastQuestion) {
  const at = r.created_at;
  if (r.role === "user") return { id: `s${r.id}`, serverId: r.id, role: "user", content: r.content, at };
  if (r.role === "agent") return { id: `s${r.id}`, serverId: r.id, role: "agent", author: r.author, content: r.content, at };
  if (r.role === "system") return { id: `s${r.id}`, serverId: r.id, role: "system", content: r.content, at };
  return {
    id: `s${r.id}`, serverId: r.id, role: "assistant", stage: 4, content: r.content, sources: r.sources || [], at,
    usage: r.usage, expanded: false, fb: r.feedback || null,
    followups: followupsFor(lastQuestion, (r.sources || []).length > 0),
  };
}

const isOpenTicket = (t) => t && (t.status === "waiting" || t.status === "active");

const MAX_FILES = 3;
const MAX_FILE_MB = 5;
const ASKS_FOR_PERSON = /\b(person|human|agent|representative|someone|insaan|banda)\b/i;

function savedContact() {
  try {
    return JSON.parse(localStorage.getItem("support-contact") || "{}");
  } catch {
    return {};
  }
}

// ---------- "talk to a person": the ticket form ----------
function TicketForm({ issue: initialIssue, onSubmit, onCancel }) {
  const saved = savedContact();
  const [name, setName] = useState(saved.name || "");
  const [email, setEmail] = useState(saved.email || "");
  const [issue, setIssue] = useState(initialIssue || "");
  const [files, setFiles] = useState([]);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  function addFiles(list) {
    const next = [...files, ...Array.from(list)];
    if (next.length > MAX_FILES) return setError(`You can attach up to ${MAX_FILES} files.`);
    const big = next.find((f) => f.size > MAX_FILE_MB * 1024 * 1024);
    if (big) return setError(`${big.name} is larger than ${MAX_FILE_MB} MB.`);
    setError("");
    setFiles(next);
  }

  async function submit(e) {
    e.preventDefault();
    if (!name.trim()) return setError("Please enter your name.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) return setError("Please enter a valid email address.");
    if (issue.trim().length < 5) return setError("Please describe the issue in a few words.");
    setSending(true);
    setError("");
    try {
      localStorage.setItem("support-contact", JSON.stringify({ name: name.trim(), email: email.trim() }));
    } catch { /* not remembered next time; that's fine */ }
    const err = await onSubmit({ name: name.trim(), email: email.trim(), issue: issue.trim(), files });
    if (err) setError(err);
    setSending(false);
  }

  return (
    <form className="ticket-form" onSubmit={submit}>
      <p className="mono-label">TALK TO A PERSON</p>
      <h3>Open a support ticket</h3>
      <p className="tf-note">An agent will reply right here in this chat.</p>
      <div className="tf-row">
        <label htmlFor="tf-name">Name</label>
        <input id="tf-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Your full name" />
      </div>
      <div className="tf-row">
        <label htmlFor="tf-email">Email</label>
        <input id="tf-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com" />
      </div>
      <div className="tf-row">
        <label htmlFor="tf-issue">Issue</label>
        <textarea id="tf-issue" rows={3} value={issue} onChange={(e) => setIssue(e.target.value)}
          placeholder="What went wrong? Add your order number if you have one." />
      </div>
      <div className="tf-row">
        <span className="tf-label">Attachments <small>optional · up to {MAX_FILES} files, {MAX_FILE_MB} MB each</small></span>
        {files.length > 0 && (
          <ul className="tf-files">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}>
                <span>{f.name}</span>
                <small>{Math.max(1, Math.round(f.size / 1024))} KB</small>
                <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</button>
              </li>
            ))}
          </ul>
        )}
        {files.length < MAX_FILES && (
          <label className="tf-attach">
            <input id="tf-files" type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,text/plain"
              onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
            + Add screenshots, a PDF or a text file
          </label>
        )}
      </div>
      {error && <p className="tf-error" role="alert">{error}</p>}
      <div className="tf-actions">
        <button type="button" className="tf-cancel" onClick={onCancel} disabled={sending}>Cancel</button>
        <button type="submit" className="btn-accent" disabled={sending}>{sending ? "Opening…" : "Open ticket"}</button>
      </div>
    </form>
  );
}

function timeAgo(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

// ---------- live retrieval trace while the answer is being prepared ----------
function Trace({ m, chunkCount }) {
  const n = m.sources?.length ?? 0;
  const pages = [...new Set((m.sources || []).map((s) => `p.${s.page}`))].join(", ");
  const rewritten = m.query && m.query !== m.question;
  const skipped = m.route === "greeting" || m.route === "handoff";
  const details = [
    m.route === "greeting" ? "Greeting, no search needed"
      : m.route === "handoff" ? "Request for a person"
      : m.stage > 0 ? (rewritten ? `Searching for “${m.query}”` : "Used as written") : "",
    skipped ? "Skipped" : m.broadened ? "Nothing close, widening the search" : `${chunkCount ?? "All"} chunks · vector + keyword`,
    skipped ? "Skipped" : m.stage > 2 ? (n ? `${n} passages · ${pages}` : "Nothing relevant in the handbook") : "Cross-encoder rerank",
    m.route === "handoff" ? "Ticket created" : m.tool ? "Looked up the order" : "Claude, streaming",
  ];
  return (
    <div className="trace" role="status" aria-label="Preparing the answer">
      {TRACE_STEPS.map((label, i) => {
        const done = i < m.stage;
        const active = i === m.stage;
        return (
          <div key={label} className={`trace-step${done ? " done" : ""}${active ? " active" : ""}`}>
            <span className="trace-dot" aria-hidden>{done ? "✓" : ""}</span>
            <span className="trace-text">
              <span>{label}</span>
              {details[i] && <span className="trace-detail">{details[i]}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------- quiet "Sources" toggle under the answer ----------
function Sources({ m, onToggle }) {
  const n = m.sources?.length ?? 0;
  if (!n) return null;
  return (
    <button className="meta-btn" onClick={onToggle} aria-expanded={m.expanded}>
      {Icon.doc}
      <span>{n} source{n === 1 ? "" : "s"}</span>
      <span className={`chev${m.expanded ? " up" : ""}`} aria-hidden>{Icon.chev}</span>
    </button>
  );
}

function SourceList({ m }) {
  return (
    <ul className="passages">
      {m.sources.map((s, i) => (
        <li key={i} title={s.text}>
          <span className="p-page">p.{s.page}</span>
          <span className="p-title">{s.title || chunkTitle(s.text)}</span>
          <span className="p-score">{Math.round(Math.min(1, s.score) * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}

// ---------- place in the support queue / who is chatting ----------
function QueueBar({ ticket, onLeave }) {
  if (ticket.status === "active") {
    return (
      <div className="queue-bar active" role="status">
        <span className="queue-avatar" aria-hidden>{(ticket.agent || "S").slice(0, 1).toUpperCase()}</span>
        <div className="queue-text">
          <strong>{ticket.agent} is helping you</strong>
          <span>Support agent · ticket {ticket.ticket}</span>
        </div>
        <button className="queue-leave" onClick={onLeave}>End chat</button>
      </div>
    );
  }
  const next = ticket.position <= 1;
  return (
    <div className="queue-bar" role="status">
      <span className="queue-pos" aria-hidden>
        <small>No.</small>{ticket.position || 1}
      </span>
      <div className="queue-text">
        <strong>
          {ticket.agents_busy
            ? (next ? "All agents are busy. You're next in line" : `All agents are busy. You're number ${ticket.position} in line`)
            : "Connecting you to an agent"}
        </strong>
        <span>
          About {ticket.wait_minutes} min{ticket.wait_minutes === 1 ? "" : "s"}
          {ticket.ahead > 0 ? ` · ${ticket.ahead} ${ticket.ahead === 1 ? "person" : "people"} ahead of you` : ""}
          {` · ticket ${ticket.ticket}`}
        </span>
      </div>
      <button className="queue-leave" onClick={onLeave}>Leave queue</button>
    </div>
  );
}

const Icon = {
  up: <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden><path d="M7 10v10H4V10h3zm0 0l4-7c1.5 0 2.5 1 2.2 2.6L12.6 9H19a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 20H7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /></svg>,
  down: <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden><path d="M17 14V4h3v10h-3zm0 0l-4 7c-1.5 0-2.5-1-2.2-2.6l.6-3.4H5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.2 4H17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /></svg>,
  doc: <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden><path d="M7 3h7l5 5v13H7zM14 3v5h5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /></svg>,
  chev: <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  chat: <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden><path d="M4 5h16v11H9l-5 4V5z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /></svg>,
  history: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  plus: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>,
  close: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>,
  back: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  send: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M4 12l16-8-6 16-2.5-6.5L4 12z" fill="currentColor" /></svg>,
};

export default function SupportWidget() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("chat");        // "chat" | "history"
  const [chats, setChats] = useState([]);
  const [chatsLoaded, setChatsLoaded] = useState(false);
  const [chunkCount, setChunkCount] = useState(null);
  const [activeId, setActiveId] = useState(null);  // null = new chat, not saved yet
  const [messages, setMessages] = useState([]);
  const [opening, setOpening] = useState(false);
  const [notice, setNotice] = useState("");
  const [input, setInput] = useState("");
  const [ticket, setTicket] = useState(null);      // open support ticket of this chat (queue / agent)
  const [showForm, setShowForm] = useState(false); // the "talk to a person" form is on screen
  const [agentTyping, setAgentTyping] = useState(null);   // name of the agent who is typing right now
  const liveRef = useRef(null);                    // the open /ws/support socket (to send "typing")
  const typingRef = useRef(null);
  const agentTypingTimer = useRef(null);
  const lastSeen = useRef(0);                      // newest server message id on screen
  const activeRef = useRef(null);
  const sendRef = useRef(null);
  const seq = useRef(0);
  const threadRef = useRef(null);
  const inputRef = useRef(null);
  const tabRef = useRef(null);

  const busy = messages.some((m) => m.role === "assistant" && m.stage < 4);
  const withAgent = isOpenTicket(ticket);
  const nextId = () => ++seq.current;

  useEffect(() => { activeRef.current = activeId; }, [activeId]);

  // Adds server messages (agent replies, "Ali joined the chat") that aren't on screen yet
  function addFromServer(rows) {
    if (!rows?.length) return;
    lastSeen.current = Math.max(lastSeen.current, ...rows.map((r) => r.id));
    setMessages((prev) => {
      const have = new Set(prev.map((m) => m.serverId).filter(Boolean));
      const fresh = rows.filter((r) => !have.has(r.id)).map((r) => fromServer(r, ""));
      return fresh.length ? [...prev, ...fresh] : prev;
    });
  }

  // While a ticket is open: live updates over a WebSocket, polling every 3 s only while it is down
  useEffect(() => {
    if (!isOpenTicket(ticket)) return;
    const id = ticket.id;
    let stop = false;
    let timer = null;

    function apply(data) {
      if (stop) return;
      if (data.messages?.some((m) => m.role === "agent")) setAgentTyping(null);   // the reply arrived
      addFromServer(data.messages);
      const { messages: _, ...info } = data;
      setTicket(isOpenTicket(info) ? info : null);
    }
    async function poll() {
      try {
        apply(await api(`/api/handoff/${id}?after=${lastSeen.current}`));
      } catch {
        /* try again on the next tick */
      }
    }
    function setPolling(on) {
      clearInterval(timer);
      timer = on ? setInterval(poll, 3000) : null;
    }

    poll();
    setPolling(true);
    const close = openLive(
      "/ws/support",
      () => ({ visitor_id: visitorId(), ticket_id: id, after: lastSeen.current }),
      {
        onMessage: (msg) => {
          if (msg.type === "update") apply({ ...msg.ticket, messages: msg.messages });
          if (msg.type === "typing") {
            clearTimeout(agentTypingTimer.current);
            setAgentTyping(msg.on ? msg.name : null);
            // safety net: hide it if the "stopped typing" message never comes
            if (msg.on) agentTypingTimer.current = setTimeout(() => setAgentTyping(null), 6000);
          }
        },
        onStatus: (connected) => setPolling(!connected),
      },
    );
    liveRef.current = close;
    typingRef.current = typingNotifier((on) => close.send({ type: "typing", on }));
    return () => {
      stop = true;
      setPolling(false);
      typingRef.current?.stop();
      close();
      liveRef.current = null;
      typingRef.current = null;
      setAgentTyping(null);
    };
  }, [ticket?.id, ticket?.status === "closed"]);

  async function refreshChats() {
    try {
      setChats(await api("/api/conversations"));
      setNotice("");
    } catch {
      setNotice("Can't load your chats right now.");
    } finally {
      setChatsLoaded(true);
    }
  }

  // First open: load the chat list and how many chunks the handbook has
  useEffect(() => {
    if (!open || chatsLoaded) return;
    refreshChats();
    api("/api/health").then((h) => setChunkCount(h.chunks)).catch(() => {});
  }, [open, chatsLoaded]);

  // Other parts of the page open the panel (and optionally ask something)
  useEffect(() => {
    function onOpen(e) {
      setOpen(true);
      setView("chat");
      const q = e.detail?.question;
      if (q) setTimeout(() => sendRef.current?.(q), 0);
    }
    window.addEventListener("support:open", onOpen);
    return () => window.removeEventListener("support:open", onOpen);
  }, []);

  // Large screens dock the open panel beside the page (see .support-docked in globals.css)
  useEffect(() => {
    document.documentElement.classList.toggle("support-docked", open);
    return () => document.documentElement.classList.remove("support-docked");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open && view === "chat") setTimeout(() => inputRef.current?.focus(), 300);
  }, [open, view]);

  useEffect(() => { scrollToEnd(); }, [messages, showForm, agentTyping]);

  function scrollToEnd() {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }

  function close() {
    setOpen(false);
    tabRef.current?.focus();
  }

  function patch(id, change) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...(typeof change === "function" ? change(m) : change) } : m)));
  }

  function newChat() {
    setView("chat");
    setActiveId(null);
    activeRef.current = null;
    setMessages([]);
    setTicket(null);
    setShowForm(false);
    lastSeen.current = 0;
    setInput("");
  }

  async function openChat(id) {
    setView("chat");
    if (id === activeId) return;
    setActiveId(id);
    activeRef.current = id;
    setMessages([]);
    setTicket(null);
    setShowForm(false);
    setOpening(true);
    try {
      const [rows, current] = await Promise.all([
        api(`/api/conversations/${id}/messages`),
        api(`/api/handoff/current?conversation_id=${id}`).catch(() => ({})),
      ]);
      if (activeRef.current !== id) return;
      let lastQuestion = "";
      lastSeen.current = rows.reduce((max, r) => Math.max(max, r.id), 0);
      setMessages(rows.map((r) => {
        if (r.role === "user") lastQuestion = r.content;
        return fromServer(r, lastQuestion);
      }));
      setTicket(isOpenTicket(current) ? current : null);
    } catch (err) {
      setMessages([{ id: nextId(), role: "assistant", stage: 4, error: true, content: err.message }]);
    } finally {
      setOpening(false);
    }
  }

  async function deleteChat(id) {
    try {
      await api(`/api/conversations/${id}`, { method: "DELETE" });
      if (id === activeId) newChat();
      refreshChats();
    } catch (err) {
      setNotice(err.message);
    }
  }

  function escalate() {
    setOpen(true);
    setView("chat");
    if (isOpenTicket(ticket) || busy) return;
    setShowForm(true);
  }

  // Sends the ticket form. Returns an error message for the form, or nothing when it worked.
  async function openTicket({ name, email, issue, files }) {
    const form = new FormData();
    form.append("name", name);
    form.append("email", email);
    form.append("issue", issue);
    if (activeRef.current) form.append("conversation_id", activeRef.current);
    files.forEach((f) => form.append("files", f));
    try {
      const res = await fetch("/api/handoff", { method: "POST", headers: { "X-Visitor-Id": visitorId() }, body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return data.error || (res.status === 413 ? "The files are too large." : `The server answered with status ${res.status}.`);
      setShowForm(false);
      setActiveId(data.conversation_id);
      activeRef.current = data.conversation_id;
      setTicket(data);               // polling starts and shows "Ticket SE-… opened" from the server
      refreshChats();
    } catch {
      return "The support team can't be reached right now. Please try again.";
    }
  }

  async function leaveQueue() {
    if (!ticket) return;
    const id = ticket.id;
    setTicket(null);
    try {
      await api(`/api/handoff/${id}/cancel`, { method: "POST" });
      const data = await api(`/api/handoff/${id}?after=${lastSeen.current}`);
      addFromServer(data.messages);
    } catch {
      /* the ticket stays closed on screen; the server closes it on its next check */
    }
  }

  // While a person handles the chat, messages go to them (not to the assistant)
  async function sendToAgent(text) {
    const localId = nextId();
    typingRef.current?.stop();
    setInput("");
    setMessages((prev) => [...prev, { id: localId, role: "user", content: text, at: now() }]);
    try {
      const data = await api(`/api/handoff/${ticket.id}/messages`, { method: "POST", body: JSON.stringify({ message: text }) });
      patch(localId, { serverId: data.message_id });
      lastSeen.current = Math.max(lastSeen.current, data.message_id);
    } catch (err) {
      setMessages((prev) => [...prev, { id: nextId(), role: "system", content: err.message, at: now() }]);
      if (/closed/i.test(err.message)) setTicket(null);
    }
  }

  async function giveFeedback(m, value) {
    const next = m.fb === value ? null : value;
    patch(m.id, { fb: next });
    if (!m.serverId) return;
    try {
      await api(`/api/messages/${m.serverId}/feedback`, { method: "POST", body: JSON.stringify({ value: next }) });
    } catch {
      /* keep the click on screen even if saving failed */
    }
  }

  async function send(text) {
    const question = (text ?? input).trim();
    if (!question) return;
    if (/^talk to a person$/i.test(question)) return escalate();
    if (isOpenTicket(ticket)) return sendToAgent(question);
    if (messages.some((m) => m.role === "assistant" && m.stage < 4)) return;

    const chatAtSend = activeRef.current;
    const botId = nextId();
    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", content: question, at: now() },
      { id: botId, role: "assistant", stage: 0, question, content: "", sources: [], expanded: false, fb: null },
    ]);

    const stillHere = () => activeRef.current === chatAtSend;

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Visitor-Id": visitorId() },
        body: JSON.stringify({ conversation_id: chatAtSend, message: question }),
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `The server answered with status ${res.status}.`);
      }

      let failed = null;
      await readEvents(res, (event, data) => {
        if (!stillHere()) return; // user switched chats; the answer is still saved
        if (event === "step") {
          // the server's workflow reports each step as it starts
          if (data.name === "classify") patch(botId, { route: data.route });
          else if (data.name === "retrieve") patch(botId, (m) => ({ stage: Math.max(m.stage, 1) }));
          else if (data.name === "broaden") patch(botId, { broadened: true });
        } else if (event === "meta") {
          if (data.chunks_searched) setChunkCount(data.chunks_searched);
          patch(botId, { stage: 3, route: data.route, query: data.query, sources: data.sources || [] });
        } else if (event === "handoff") {
          setShowForm(true);           // "talk to a person" typed in the chat: show the ticket form
        } else if (event === "tool") {
          patch(botId, { tool: data.name });
        } else if (event === "delta") {
          patch(botId, (m) => ({ content: m.content + data.text }));
        } else if (event === "done") {
          setActiveId(data.conversation_id);
          activeRef.current = data.conversation_id;
          patch(botId, (m) => ({
            stage: 4,
            at: now(),
            serverId: data.message_id,
            usage: data.usage,
            content: m.content.trim() || "Sorry, I couldn't finish that answer. Please try asking again.",
            followups: followupsFor(question, (m.sources || []).length > 0),
          }));
        } else if (event === "error") {
          failed = data.error;
        }
      });
      if (failed) throw new Error(failed);
      refreshChats();
    } catch (err) {
      const offline = err instanceof TypeError || /status 50[0-4]/.test(err.message);
      patch(botId, {
        stage: 4,
        error: true,
        content: offline ? "The assistant is offline right now. Please try again in a moment." : err.message,
      });
    } finally {
      inputRef.current?.focus();
    }
  }
  sendRef.current = send;

  function renderAssistant(m, isLast) {
    if (m.error) {
      return <div className="bubble bot error">{m.content}</div>;
    }
    const done = m.stage >= 4;
    const u = m.usage || {};
    const stats = u.total_ms != null
      ? `${(u.total_ms / 1000).toFixed(1)}s · ${u.input ?? 0} tokens in / ${u.output ?? 0} out`
      : "";
    return (
      <div className="bot-col">
        {/* live trace only until the first words arrive */}
        {!done && !m.content && <Trace m={m} chunkCount={chunkCount} />}

        {m.stage === 3 && !m.content && (
          <div className="bubble bot thinking" aria-label="Support is typing">
            <span className="dots" aria-hidden><i /><i /><i /></span>
          </div>
        )}
        {m.content && (
          <div className={`bubble bot${m.stage === 3 ? " is-typing" : ""}`}>
            <ReactMarkdown>{m.content}</ReactMarkdown>
          </div>
        )}
        {done && !isLast && m.at && <span className="msg-time">{clock(m.at)}</span>}

        {/* sources, feedback, time and suggestions only on the newest answer; older ones stay clean */}
        {done && isLast && (
          <>
            <div className="msg-meta">
              <Sources m={m} onToggle={() => patch(m.id, { expanded: !m.expanded })} />
              <span className="meta-actions">
                <button
                  className={`fb-btn${m.fb === "up" ? " on" : ""}`}
                  onClick={() => giveFeedback(m, "up")}
                  aria-pressed={m.fb === "up"}
                  aria-label="Helpful"
                  title="Helpful"
                >
                  {Icon.up}
                </button>
                <button
                  className={`fb-btn${m.fb === "down" ? " on" : ""}`}
                  onClick={() => giveFeedback(m, "down")}
                  aria-pressed={m.fb === "down"}
                  aria-label="Not helpful"
                  title="Not helpful"
                >
                  {Icon.down}
                </button>
                {(m.at || u.total_ms != null) && (
                  <span className="stats" title={stats ? `Answered in ${stats}` : undefined}>
                    {m.at ? clock(m.at) : `${(u.total_ms / 1000).toFixed(1)}s`}
                  </span>
                )}
              </span>
            </div>
            {m.expanded && m.sources?.length > 0 && <SourceList m={m} />}
            {m.fb === "down" && (
              <p className="fb-note">
                Thanks, we'll review this answer. <button className="link" onClick={escalate}>Talk to a person</button>
              </p>
            )}
            {!withAgent && m.followups?.length > 0 && (
              <div className="followups">
                {m.followups.map((q) => (
                  <button key={q} className="chip accent" onClick={() => send(q)}>{q}</button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <>
      <button
        ref={tabRef}
        className={`support-tab${open ? " is-hidden" : ""}`}
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-controls="support-panel"
      >
        {Icon.chat}
        <span>Support</span>
      </button>

      <aside
        id="support-panel"
        className={`support-panel${open ? " open" : ""}`}
        aria-label="Customer support chat"
        aria-hidden={!open}
      >
        <header className="sp-head">
          {view === "history" ? (
            <button className="sp-icon" onClick={() => setView("chat")} aria-label="Back to chat">{Icon.back}</button>
          ) : (
            <span className="mark" aria-hidden>S</span>
          )}
          <div className="sp-title">
            <h2>{view === "history" ? "Your chats" : "ShopEase support"}</h2>
            {view === "chat" && (
              <p>
                <span className="live-dot small" aria-hidden />
                {ticket?.status === "active" ? `Chatting with ${ticket.agent}`
                  : ticket?.status === "waiting" ? "Waiting for a support agent"
                  : "Online · from the handbook"}
              </p>
            )}
          </div>
          {view === "chat" && (
            <button className="sp-icon" onClick={() => { setView("history"); refreshChats(); }} aria-label="Your chats" title="Your chats">
              {Icon.history}
            </button>
          )}
          <button className="sp-icon" onClick={newChat} disabled={busy} aria-label="New chat" title="New chat">{Icon.plus}</button>
          <button className="sp-icon" onClick={close} aria-label="Close support" title="Close">{Icon.close}</button>
        </header>

        {view === "history" ? (
          <div className="sp-history">
            {notice && <p className="sp-muted">{notice}</p>}
            {!notice && chatsLoaded && chats.length === 0 && (
              <p className="sp-muted">No chats yet. Your conversations will appear here.</p>
            )}
            <ul>
              {chats.map((c) => (
                <li key={c.id} className={`history-item${c.id === activeId ? " active" : ""}`}>
                  <button className="history-open" onClick={() => openChat(c.id)}>
                    <span className="history-title">{c.title}</span>
                    <span className="history-time">{timeAgo(c.updated_at)}</span>
                  </button>
                  <button
                    className="history-delete"
                    onClick={() => deleteChat(c.id)}
                    aria-label={`Delete chat: ${c.title}`}
                    title="Delete chat"
                    disabled={busy && c.id === activeId}
                  >
                    {Icon.close}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <>
            <div className="sp-thread" ref={threadRef} aria-live="polite">
              {opening ? (
                <p className="sp-muted">Loading chat…</p>
              ) : messages.length === 0 ? (
                <div className="sp-welcome">
                  <p className="mono-label">NEW CONVERSATION</p>
                  <h3>Hi! How can we help?</h3>
                  <p>Ask about orders, delivery, payments, returns or your account, in English or Urdu. Demo order numbers: SE10482931 to SE10482936.</p>
                  <div className="sp-suggestions">
                    {SUGGESTIONS.map((q) => (
                      <button key={q} onClick={() => send(q)}>{q}</button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div key={m.id} className="msg">
                    {m.role === "user" && (
                      <>
                        <div className="bubble user">{m.content}</div>
                        {m.at && <span className="msg-time right">{clock(m.at)}</span>}
                      </>
                    )}
                    {m.role === "assistant" && renderAssistant(m, i === messages.length - 1)}
                    {m.role === "agent" && (
                      <div className="agent-col">
                        <span className="agent-name">{m.author || "Support"} · ShopEase support</span>
                        <div className="bubble agent">{m.content}</div>
                        {m.at && <span className="msg-time">{clock(m.at)}</span>}
                      </div>
                    )}
                    {m.role === "system" && <p className="sys-line">{m.content}{m.at ? ` · ${clock(m.at)}` : ""}</p>}
                  </div>
                ))
              )}
              {withAgent && agentTyping && (
                <div className="msg">
                  <div className="agent-col" aria-live="polite">
                    <span className="agent-name">{agentTyping} is typing…</span>
                    <div className="bubble agent thinking" aria-label={`${agentTyping} is typing`}>
                      <span className="dots" aria-hidden><i /><i /><i /></span>
                    </div>
                  </div>
                </div>
              )}
              {showForm && !opening && (
                <TicketForm
                  issue={[...messages].reverse().find((m) => m.role === "user" && !ASKS_FOR_PERSON.test(m.content))?.content}
                  onSubmit={openTicket}
                  onCancel={() => setShowForm(false)}
                />
              )}
            </div>

            {withAgent && <QueueBar ticket={ticket} onLeave={leaveQueue} />}
            {!showForm && <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
              <input
                ref={inputRef}
                value={input}
                placeholder={
                  busy ? "Waiting for the answer…"
                    : ticket?.status === "active" ? `Message ${ticket.agent}`
                    : ticket?.status === "waiting" ? "Write to the agent while you wait"
                    : "Type your question"
                }
                aria-label="Your question"
                onChange={(e) => {
                  setInput(e.target.value);
                  if (withAgent && e.target.value) typingRef.current?.();
                }}
              />
              <button type="submit" className="send" disabled={busy || !input.trim()} aria-label="Send">{Icon.send}</button>
            </form>}
            <div className="sp-foot">
              <span>Demo assistant for a fictional store.</span>
              {!withAgent && !showForm && <button className="link" onClick={escalate}>Talk to a person</button>}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
