"""
Prompts live in plain text files next to this one, so they can be edited without touching code.

    from app.prompts import load_prompt
    load_prompt("system")                          # app/prompts/system.md
    load_prompt("handoff_reply", ticket="SE-1")    # with {placeholders} filled in
"""
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _read(name):
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def load_prompt(name, **values):
    text = _read(name)
    return text.format(**values) if values else text
