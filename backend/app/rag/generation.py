"""
app/rag/generation.py - THE "G": EVERYTHING THE PIPELINE ASKS A LANGUAGE MODEL TO DO
(the prompts are in app/prompts/*.md)

This file doesn't know which model it talks to. It uses two ChatModels from
providers/factory.py (picked in config.py):
    self.chat   the main model, writes answers
    self.fast   the fast model, for small jobs (query rewriting, summaries)

  rewrite_query()  "how long does it take?" (after asking about returns)
                   -> "how long does a refund take"   standalone, English, good for search
  stream()         AUGMENT: put the retrieved chunks in the prompt
                   GENERATE: stream the answer; if the model calls a tool (lookup_order),
                   run it and let the model continue with the result
  answer()         same as stream(), but returns the whole text at once
  summarize()      fold old messages into a short running summary (long chats stay cheap)

MEMORY: models are stateless, so the caller passes recent messages (history)
and the running summary every time. Both come from Postgres (app/db/repositories/conversations.py).
"""
import logging

from app.core import config
from app.prompts import load_prompt
from app.providers import factory

log = logging.getLogger(__name__)

FALLBACK = ("Sorry, I couldn't finish that answer. Please try asking again, "
            "or contact ShopEase support on WhatsApp at 0300-1234567.")


class Assistant:
    def __init__(self, chat=None, fast=None, tools=None, run_tool=None, prefetch=None):
        self.chat = chat or factory.build_llm("main")
        self.fast = fast or factory.build_llm("fast")
        self.tools = tools or []
        self.run_tool = run_tool
        self.prefetch = prefetch     # used instead of tools when the model can't call tools

    # ---------- helpers ----------
    @staticmethod
    def _trim_history(history):
        out = []
        for m in history[-config.MEMORY_TURNS * 2:]:
            text = m["content"]
            if m["role"] == "assistant" and len(text) > config.HISTORY_CHAR_LIMIT:
                text = text[: config.HISTORY_CHAR_LIMIT] + "..."
            out.append({"role": m["role"], "content": text})
        return out

    # ---------- 1. query rewriting ----------
    def rewrite_query(self, question, history, force=False):
        """Returns (search_query, usage). Only calls the model when it helps:
        a follow-up in an ongoing chat, a question that isn't plain English,
        or force=True (the workflow's retry after an empty search)."""
        needs_it = force or (config.REWRITE_QUERIES and (history or any(ord(ch) > 127 for ch in question)))
        if not needs_it:
            return question, {"input": 0, "output": 0}
        convo = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])
        turn = self.fast.complete(
            system=load_prompt("rewrite_query"),
            messages=[{"role": "user", "content": f"Conversation:\n{convo or '(none)'}\n\nLatest message: {question}"}],
            max_tokens=60,
        )
        query = turn.text.strip().strip('"').splitlines()[0].strip() if turn.text.strip() else question
        return query or question, {"input": turn.input_tokens, "output": turn.output_tokens}

    # ---------- 2 + 3. augment + generate (streaming, with tools) ----------
    def stream(self, question, chunks, history, summary=""):
        """Yields ("delta", text), ("tool", name) and finally ("usage", {...})."""
        context = "\n\n".join(chunks) if chunks else "(no relevant information found)"
        use_tools = bool(self.tools) and self.chat.supports_tools
        if self.tools and not use_tools and self.prefetch:
            extra = self.prefetch(question)   # model can't call tools: look the order up ourselves
            if extra:
                context += "\n\n" + extra
                yield "tool", "lookup_order"
        prompt = f"<context>\n{context}\n</context>\n\nQuestion: {question}"
        system = load_prompt("system")
        if summary:
            system += f"\n\nEarlier in this conversation (summary): {summary}"

        messages = self._trim_history(history) + [{"role": "user", "content": prompt}]
        used_in = used_out = 0
        wrote_text = False
        for _ in range(3):   # at most 3 rounds of tool use
            turn = None
            for kind, value in self.chat.stream(system, messages, config.MAX_ANSWER_TOKENS,
                                                self.tools if use_tools else None):
                if kind == "text":
                    if value.strip():
                        wrote_text = True
                    yield "delta", value
                else:
                    turn = value
            used_in += turn.input_tokens
            used_out += turn.output_tokens
            if not turn.tool_calls:
                if turn.stop_reason in ("max_tokens", "length"):
                    log.warning("answer hit MAX_ANSWER_TOKENS (%s)", config.MAX_ANSWER_TOKENS)
                break
            # The model asked for tools: run them, give back the results, let it continue
            results = []
            for call in turn.tool_calls:
                yield "tool", call.name
                results.append((call, self.run_tool(call.name, call.arguments)))
            messages = self.chat.add_tool_results(messages, turn, results)
            if turn.text.strip():
                yield "delta", "\n\n"
        if not wrote_text:   # e.g. the token budget ran out while the model was still thinking
            yield "delta", FALLBACK
        yield "usage", {"input": used_in, "output": used_out}

    def answer(self, question, chunks, history, summary=""):
        """Non-streaming version: returns (text, usage)."""
        parts, usage, tools_used = [], {}, []
        for kind, value in self.stream(question, chunks, history, summary):
            if kind == "delta":
                parts.append(value)
            elif kind == "tool":
                tools_used.append(value)
            elif kind == "usage":
                usage = value
        return "".join(parts).strip(), {**usage, "tools": tools_used}

    # ---------- 4. running summary ----------
    def summarize(self, previous_summary, messages):
        convo = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in messages)
        turn = self.fast.complete(
            system=load_prompt("summarize"),
            messages=[{"role": "user", "content": f"Current summary: {previous_summary or '(none)'}\n\nNew messages:\n{convo}"}],
            max_tokens=150,
        )
        return turn.text.strip()
