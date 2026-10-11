"""The decisions: which node runs next."""


def after_classify(state):
    """handoff -> handoff, greeting -> straight to generate (no search), question -> rewrite."""
    return {"handoff": "handoff", "greeting": "generate"}.get(state["route"], "rewrite")


def after_retrieve(state):
    """Found something, or already retried once -> generate. Otherwise widen the search."""
    if state["results"] or state["attempts"] >= 1:
        return "generate"
    return "broaden"
