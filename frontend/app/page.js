"use client";
/**
 * ShopEase Help - landing page of the portfolio demo.
 * The real project is the support assistant (SupportWidget): a RAG chatbot that
 * answers from a PDF handbook. Every question button on this page opens it.
 */
import { useState } from "react";
import SupportWidget, { openSupport } from "./components/SupportWidget";
import ThemeToggle from "./components/ThemeToggle";

const POPULAR = [
  "Where is my order?",
  "How do I return a product?",
  "Money was deducted but no order was placed",
];

const TOPICS = [
  { title: "Orders and tracking", text: "Place, change, cancel and track orders.",
    asks: ["How can I track my order?", "Can I cancel my order?"] },
  { title: "Delivery", text: "Times, charges, cities and missed deliveries.",
    asks: ["How long does delivery take?", "How much does delivery cost?"] },
  { title: "Payments", text: "Cash on delivery, cards, wallets and installments.",
    asks: ["What payment methods do you accept?", "Money was deducted but no order was placed"] },
  { title: "Returns and refunds", text: "Return a product and get your money back.",
    asks: ["How do I return a product?", "When will I get my refund?"] },
  { title: "Your account", text: "Sign up, passwords, OTPs and account details.",
    asks: ["I forgot my password", "I'm not receiving the OTP"] },
  { title: "Warranty and products", text: "Warranty claims, PTA phones and authenticity.",
    asks: ["How do I claim warranty?", "Are your phones PTA approved?"] },
];

const STEPS = [
  { tag: "01 / INGEST", title: "Handbook to topics",
    text: "pdfplumber reads the PDF (tables and scanned pages too) and splits it by heading, so each chunk is one policy." },
  { tag: "02 / EMBED", title: "Vectors and keywords",
    text: "A multilingual model turns every chunk into a vector in PostgreSQL + pgvector, next to a full-text keyword index." },
  { tag: "03 / ROUTE", title: "Decide what to do",
    text: "A LangGraph workflow reads each message: a greeting skips the search, \"talk to a person\" opens a ticket, questions go on." },
  { tag: "04 / RETRIEVE", title: "Find the right policy",
    text: "Follow-ups and Urdu are rewritten into a clear search. Vector and keyword results are merged and reranked; if nothing fits, it widens the search once." },
  { tag: "05 / GENERATE", title: "Grounded answer",
    text: "Claude answers only from those passages, looks up live order status with a tool, and streams the reply word by word." },
  { tag: "06 / REMEMBER", title: "Private memory",
    text: "Each chat is saved in Postgres for that browser only, with a running summary so long conversations stay cheap." },
];

// One real question, node by node (what the live trace in the chat shows)
const EXAMPLE = {
  question: "mera order SE10482931 kahan hai?",
  steps: [
    { node: "load_memory", out: "2 earlier messages about delivery + chat summary" },
    { node: "classify", out: "question (not a greeting, not asking for a person)" },
    { node: "rewrite", out: "“where is order SE10482931 tracking status”" },
    { node: "retrieve", out: "4 of 63 passages · order tracking, delivery times · 0.4 s" },
    { node: "generate", out: "Claude calls lookup_order(SE10482931) → Shipped, TCS-77120934" },
    { node: "save", out: "answer + sources stored, summary updated in the background" },
  ],
  answer: "Your order SE10482931 has shipped with TCS and should reach you in Lahore by 11 Oct. Track it with TCS-77120934. Please keep PKR 6,499 ready for cash on delivery.",
};

const SEARCH = [
  { k: "query", v: "one clear English question" },
  { k: "meaning + keywords", v: "pgvector similarity and Postgres full-text, 20 each" },
  { k: "merge", v: "reciprocal rank fusion" },
  { k: "filter", v: "drop anything below 0.3 similarity" },
  { k: "rerank", v: "cross-encoder reads question + passage" },
  { k: "top 4", v: "sent to Claude as the only facts it may use" },
];

const STACK = ["Next.js", "Flask", "LangGraph", "LangChain", "PostgreSQL + pgvector", "Sentence Transformers", "Claude", "Docker"];

export default function Home() {
  const [question, setQuestion] = useState("");

  function heroSubmit(e) {
    e.preventDefault();
    openSupport(question.trim() || undefined);
    setQuestion("");
  }

  return (
    <>
      <header className="site-nav">
        <div className="wrap nav-inner">
          <a href="#" className="brand" aria-label="ShopEase Help home">
            <span className="mark" aria-hidden>S</span>
            <span className="brand-name">ShopEase</span>
            <span className="badge">Help</span>
          </a>
          <nav aria-label="Main">
            <a href="#topics" className="nav-link">Topics</a>
            <a href="#how" className="nav-link">How it works</a>
            <ThemeToggle />
            <button className="nav-cta" onClick={() => openSupport()}>Get help</button>
          </nav>
        </div>
      </header>

      <main>
        {/* ---------- hero ---------- */}
        <section className="hero wrap">
          <div>
            <p className="status-line"><span className="live-dot" aria-hidden />SUPPORT ONLINE · REPLIES IN SECONDS</p>
            <h1>Hi, how can we&nbsp;<span className="accent-text">help?</span></h1>
            <p className="hero-lead">
              Ask about an order, delivery, payment or return. The assistant looks up ShopEase's own
              handbook before every answer, so it won't make up a policy.
            </p>

            <form className="hero-ask" onSubmit={heroSubmit}>
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
                <path d="M4 5h16v11H9l-5 4V5z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              </svg>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Type your question"
                aria-label="Ask customer support"
              />
              <button type="submit" className="btn-accent">Ask</button>
            </form>

            <div className="popular">
              <span>Popular</span>
              {POPULAR.map((q) => (
                <button key={q} className="chip" onClick={() => openSupport(q)}>{q}</button>
              ))}
            </div>

            <p className="human">
              Prefer a person? WhatsApp <strong>0300-1234567</strong> or email{" "}
              <strong>support@shopease.pk</strong>, every day 9 AM to 10 PM.
            </p>
          </div>

          <div className="hero-card-wrap">
            <div className="hero-card" aria-label="Example support conversation">
              <div className="hc-head">
                <span className="mark" aria-hidden>S</span>
                <div className="hc-who">
                  <p className="hc-name">ShopEase support</p>
                  <p className="hc-sub">Answers from the store handbook</p>
                </div>
                <span className="mono-label">LIVE TRACE</span>
              </div>
              <div className="hc-msg user">Can I return earbuds if I don't like them?</div>
              <div className="hc-msg bot">
                Earbuds can't be returned once the seal is broken, unless they arrived damaged or wrong.
                In that case, report it within 48 hours with photos.
              </div>
              <p className="hc-stats">1.1s · 812 in / 38 out</p>
              <button className="btn-accent block" onClick={() => openSupport("Can I return earbuds if I don't like them?")}>
                Try it yourself
              </button>
            </div>
          </div>
        </section>

        {/* ---------- help topics ---------- */}
        <section id="topics" className="topics wrap">
          <div className="section-head">
            <div>
              <h2>Browse help topics</h2>
              <p>Pick a question and the assistant answers it straight away.</p>
            </div>
            <p className="mono-label">6 TOPICS · 11-PAGE HANDBOOK</p>
          </div>
          <ul className="topic-grid">
            {TOPICS.map((t, i) => (
              <li key={t.title} className="topic">
                <span className="topic-n">{String(i + 1).padStart(2, "0")}</span>
                <h3>{t.title}</h3>
                <p>{t.text}</p>
                {t.asks.map((q) => (
                  <button key={q} className="topic-q" onClick={() => openSupport(q)}>{q}</button>
                ))}
              </li>
            ))}
          </ul>
        </section>

        {/* ---------- how it works (dark band) ---------- */}
        <section id="how" className="band">
          <div className="wrap band-inner">
            <p className="band-kicker">RETRIEVAL-AUGMENTED GENERATION</p>
            <h2>How the assistant answers</h2>
            <p className="band-lead">
              The model never memorised the store's rules. Every message runs through a small workflow that
              decides what to do, looks the rules up in the handbook, and says so when it can't find one.
            </p>
            <ol className="band-steps">
              {STEPS.map((s) => (
                <li key={s.tag}>
                  <span className="step-tag">{s.tag}</span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                </li>
              ))}
            </ol>
            {/* ---------- the workflow graph ---------- */}
            <div className="wf" aria-label="The LangGraph workflow every message runs through">
              <div className="wf-head">
                <span className="band-kicker">THE WORKFLOW · LANGGRAPH</span>
                <p>Every message takes one of three paths. You can watch it happen in the chat panel.</p>
              </div>

              <div className="wf-trunk">
                <span className="wf-node start">message</span>
                <span className="wf-arrow" aria-hidden>→</span>
                <span className="wf-node">load memory</span>
                <span className="wf-arrow" aria-hidden>→</span>
                <span className="wf-node decide">classify</span>
              </div>

              <div className="wf-lanes">
                <div className="wf-lane main">
                  <p className="wf-when">a question</p>
                  <div className="wf-path">
                    <span className="wf-node">rewrite</span>
                    <span className="wf-arrow" aria-hidden>→</span>
                    <span className="wf-node">retrieve</span>
                    <span className="wf-arrow" aria-hidden>→</span>
                    <span className="wf-node llm">generate</span>
                  </div>
                  <p className="wf-loop"><span aria-hidden>↺</span> nothing found? <b>broaden</b> the query and search once more</p>
                </div>
                <div className="wf-lane">
                  <p className="wf-when">“hi”, “shukriya”</p>
                  <div className="wf-path">
                    <span className="wf-node llm">generate</span>
                  </div>
                  <p className="wf-loop">no search needed</p>
                </div>
                <div className="wf-lane">
                  <p className="wf-when">“talk to a person”</p>
                  <div className="wf-path">
                    <span className="wf-node">handoff</span>
                  </div>
                  <p className="wf-loop">opens a support ticket</p>
                </div>
              </div>

              <div className="wf-trunk end">
                <span className="wf-node">save</span>
                <span className="wf-arrow" aria-hidden>→</span>
                <span className="wf-node start">reply streams in</span>
              </div>
            </div>

            {/* ---------- one real question + inside the search ---------- */}
            <div className="wf-detail">
              <div className="wf-example">
                <span className="band-kicker">ONE QUESTION, TRACED</span>
                <p className="wf-q">{EXAMPLE.question}</p>
                <ol className="wf-log">
                  {EXAMPLE.steps.map((s) => (
                    <li key={s.node}>
                      <span className="wf-log-node">{s.node}</span>
                      <span className="wf-log-out">{s.out}</span>
                    </li>
                  ))}
                </ol>
                <p className="wf-a">{EXAMPLE.answer}</p>
                <button className="btn-ghost" onClick={() => openSupport(EXAMPLE.question)}>Ask it yourself</button>
              </div>

              <div className="wf-search">
                <span className="band-kicker">INSIDE “RETRIEVE”</span>
                <ol className="wf-funnel">
                  {SEARCH.map((s) => (
                    <li key={s.k}>
                      <span className="wf-funnel-k">{s.k}</span>
                      <span className="wf-funnel-v">{s.v}</span>
                    </li>
                  ))}
                </ol>
                <p className="wf-note">
                  Meaning search knows “money back” means refund. Keyword search catches exact words like
                  “COD” or “PTA”. Using both, then reranking, is what keeps answers on the right policy.
                </p>
              </div>
            </div>

            <div className="band-foot">
              <ul className="stack" aria-label="Built with">
                {STACK.map((t) => <li key={t}>{t}</li>)}
              </ul>
              <button className="btn-accent" onClick={() => openSupport()}>Open the assistant</button>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="wrap footer-inner">
          <p>
            ShopEase is a fictional store built as a portfolio demo of a RAG customer-support assistant.
            Built by <a href="https://fawadiqbal.dev">Fawad Iqbal</a>.
          </p>
        </div>
      </footer>

      <SupportWidget />
    </>
  );
}
