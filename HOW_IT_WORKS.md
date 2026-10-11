# How My RAG Chatbot Works (explained super simply)

## The one-line idea

> **RAG = before answering, look it up in the book.**

Claude is very smart, but it has **never read ShopEase's rules**.
So every time someone asks a question, we first **find the right page** in our rule book,
then hand that page to Claude and say: *"Answer using this."*

That's it. That's RAG.

- **R**etrieval = find the right page
- **A**ugmented = stick that page onto the question
- **G**eneration = Claude writes the answer

---

## The story: a new shop helper

Imagine you hire a very smart new helper for your shop. On day one:

- They talk nicely and understand everything customers say. ✅
- But they **don't know your shop's rules**: return days, delivery charges, nothing. ❌

You have two choices:

| Option | What you do | Problem |
|---|---|---|
| **Training** (what you already know) | Make them memorize every rule | Slow and costly, and if a rule changes they must memorize again |
| **RAG** (what we built) | Give them a **rule book** and say "check it before you answer" | Nothing! Change the book, and they instantly know the new rule |

Our chatbot is that helper with a rule book.

- The **helper** = Claude
- The **rule book** = `support_knowledge.txt`
- **Finding the right page fast** = the embedding model + FAISS

---

## Part 1: Getting the book ready (happens once, when the server starts)

Think of preparing a giant book so you can find anything in one second.

### Step 1: Cut the book into small cards ✂️ (chunking)

Our rule book is one long file. We cut it into **small cards**, one card per paragraph.

```
Card 1: "Return Policy: Most products can be returned within 7 days..."
Card 2: "Delivery Charges: Delivery is free on orders of 1,500 PKR..."
Card 3: "Forgot Password: Tap 'Forgot Password' on the login screen..."
... 54 cards total
```

**Why cards?** Because when someone asks about returns, we want to give Claude **just the
returns card**, not the whole book. Small cards = exact answers + fewer tokens.

📄 Code: `knowledge_base.py` → the line that splits on `"\n\n"` (blank lines)

### Step 2: Give every card a "meaning address" 📍 (embedding)

This is the magic part.

A special small model (`all-MiniLM-L6-v2`) reads each card and turns it into
**384 numbers**. Think of these numbers as an **address on a map of meanings**.

- Cards about **money back** live in the same neighborhood.
- Cards about **delivery** live in another neighborhood.
- Cards about **passwords** live far away from both.

```
            🗺️  The meaning map

   [Refund timelines] [Return policy]        ← "money back" street
        [Refund methods]

                       [Delivery times] [Delivery charges]   ← "delivery" street

  [Forgot password] [OTP not received]       ← "login" street
```

You already know this from training models: it's just a vector.
**Similar meaning = vectors close together.**

📄 Code: `knowledge_base.py` → `self._embed(...)`

### Step 3: Put all addresses in a fast phone book 📒 (vector store)

We store all 54 addresses in **FAISS**, which is like a phone book that can answer:
*"Which cards live closest to this address?"* in milliseconds.

📄 Code: `knowledge_base.py` → `faiss.IndexFlatIP(...)`

When you start the server you see these three steps happen:
```
[1 chunk]  54 chunks
[2 embed]  vectors shape = (54, 384)     ← 54 cards, 384 numbers each
[3 store]  index ready
```

---

## Part 2: Answering a question (happens every time someone types)

A customer types: **"Can I get my money back for earbuds?"**

### Step 1: RETRIEVE: find the right cards 🔍

1. We turn the **question** into an address too (same 384-number trick).
2. We ask FAISS: *"Which cards live nearest to this question?"*
3. FAISS returns the closest ones with a **closeness score** (0 = unrelated, 1 = same meaning):

```
0.62  Non-Returnable Items   ✅ very related
0.55  Return Policy          ✅ related
0.41  Refund Methods         ✅ related
0.18  App Problems           ❌ thrown away (below 0.3)
```

Notice: the customer said **"money back"**, but the card says **"refund"**.
It still found it, because embeddings match **meaning**, not exact words. 🎉

We **throw away** cards scoring below **0.3** (`MIN_SCORE`), because they're noise.
If you just say "hi", *no* card is close, so we send none (and save tokens).

📄 Code: `knowledge_base.py` → `search()`

### Step 2: AUGMENT: staple the cards to the question 📎

We build one message for Claude that looks like this:

```
<context>
Non-Returnable Items: ... earphones and earbuds once the seal is broken ...
Return Policy: Most products can be returned within 7 days ...
Refund Methods: ...
</context>

Question: Can I get my money back for earbuds?
```

Plus a **system prompt** (the helper's job description):
*"You are ShopEase support. Answer ONLY from the context. Keep it short. Don't invent things."*

📄 Code: `assistant.py` → `answer()` builds `prompt`

### Step 3: GENERATE: Claude writes the answer ✍️

Claude reads the cards and replies:

> "Earbuds can't be returned once the seal is broken, unless they arrived damaged or wrong.
> If that's the case, report it within 48 hours with photos."

Claude didn't *know* this rule. It **read it from the card we gave it**.

📄 Code: `assistant.py` → `client.messages.create(...)`

---

## Part 3: Memory: how it remembers the chat 🧠

Here's a surprising fact: **Claude has no memory between messages.**
Every request is like meeting a person with total amnesia. 🐟

So how does the chat "remember"? **We cheat:** every time, we send the earlier
conversation along with the new question.

```
Message 1 sent:  [Q1]
Message 2 sent:  [Q1] [A1] [Q2]
Message 3 sent:  [Q1] [A1] [Q2] [A2] [Q3]
```

It's like handing the amnesia helper a **notebook of everything said so far**
before each new question.

- The **browser** keeps the notebook (each chat in the sidebar is its own notebook).
- We only send the **last 4 back-and-forths**, and shorten long old answers,
  because a bigger notebook costs more tokens. 💸

📄 Code: `page.js` sends `history` → `app.py` → `assistant.py` → `_trim_history()`

---

## The whole picture 🖼️

```
 YOU type in the browser
        │
        ▼
 ┌────────────────────┐   frontend/app/page.js
 │  Next.js chat page │   (shows chat, keeps the notebook/history)
 └─────────┬──────────┘
           │  POST /api/chat  { message, history }
           ▼
 ┌────────────────────┐   first from scratch/app.py
 │    Flask server    │   (the waiter: takes the order, brings the food)
 └─────────┬──────────┘
           │
   1. RETRIEVE ─────────▶ knowledge_base.py   find nearest cards (FAISS)
           │
   2. AUGMENT  ─────────▶ assistant.py        staple cards to question
           │
   3. GENERATE ─────────▶ Claude API          write the answer
           │
           ▼
   { answer, sources, usage }  back to the browser
           │
           ▼
 Chat shows the answer + "Answer based on" cards + token count
```

---

## What each file is (the cast of characters 🎭)

| File | Who it is in the story | Job |
|---|---|---|
| `support_knowledge.txt` | 📕 The rule book | All of ShopEase's policies |
| `config.py` | 🎛️ The control panel | All settings in one place |
| `knowledge_base.py` | 📚 The librarian | Cuts cards, gives addresses, finds nearest cards |
| `assistant.py` | ✍️ The writer | Builds the prompt, asks Claude, counts tokens |
| `app.py` | 🍽️ The waiter | Flask API: browser ↔ librarian + writer |
| `main.py` | 💻 Terminal version | Same flow, but in the terminal, no website |
| `frontend/app/page.js` | 🪟 The shop window | The chat screen the customer sees |
| `frontend/next.config.mjs` | 🚪 The hallway | Sends `/api/...` from the website to Flask |
| `.env` | 🔑 The key | Your Claude API key (never share it!) |

---

## The knobs you can turn 🎛️ (all in `config.py`)

| Setting | Now | Turn it up | Turn it down |
|---|---|---|---|
| `TOP_K` | 4 | More cards → more context, more tokens | Fewer cards → might miss info |
| `MIN_SCORE` | 0.3 | Stricter → only very related cards | Looser → more cards, more noise |
| `MEMORY_TURNS` | 4 | Remembers longer chats, costs more | Cheaper, forgets sooner |
| `MAX_ANSWER_TOKENS` | 300 | Longer answers allowed | Shorter, cheaper answers |
| `LLM_MODEL` | Haiku | Sonnet = smarter, pricier | Haiku = fast, cheap |

---

## RAG vs training: the cheat sheet

| | Training / fine-tuning | RAG |
|---|---|---|
| Where knowledge lives | Inside the model's weights 🧠 | In a book next to the model 📕 |
| New rule? | Retrain 😩 | Edit the text file 😎 |
| Can show where the answer came from? | No | Yes ("Answer based on...") |
| Stops making things up? | Not really | Much better: "answer ONLY from the cards" |
| Best for | Teaching **how** to talk | Teaching **what** to know |

---

## Try these to *see* RAG working 🧪

1. **Change the book:** add a paragraph to `support_knowledge.txt`, e.g.
   `Dress Code: Our riders wear blue uniforms.` Restart Flask.
   Ask "what do riders wear?". It knows instantly. No training!
2. **Ask with different words:** "my thing broke, can I swap it?" and watch it still find the right cards.
3. **Ask something not in the book:** "who is the CEO?" No good cards, so it politely says it doesn't know.
4. **Watch the tokens:** say "hi" (tiny count) vs. a long chat (bigger count, because of the notebook).
5. **Set `TOP_K = 1`** and ask a question that needs two cards. Watch the answer get worse.

---

## Remember these 5 sentences and you understand RAG 🏁

1. Claude is smart but **doesn't know your data**.
2. We **cut** our data into cards and give each card a **meaning address** (embedding).
3. For each question, we **find the closest cards** (retrieve).
4. We **staple those cards to the question** (augment) and Claude **answers from them** (generate).
5. Claude has **no memory**, so we **resend the recent chat** every time.
