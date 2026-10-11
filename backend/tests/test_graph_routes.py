"""Every path through the LangGraph workflow, with fake models and an in-memory database."""
from app.graph import edges
from app.graph.graph import build_graph
from app.graph.nodes.router import classify
from tests.fakes import fake_deps


def run(question, conversation_id=None, deps=None):
    deps = deps or fake_deps()
    conv = {"id": conversation_id, "title": question[:60], "summary": "", "visitor_id": "v1"}
    events = list(build_graph(deps).stream({"question": question, "conversation": conv}, stream_mode="custom"))
    return deps, events


def steps(events):
    return [e["data"]["name"] for e in events if e["event"] == "step"]


def test_question_goes_through_search():
    deps, events = run("How long does a refund take?")
    assert steps(events) == ["classify", "rewrite", "retrieve"]
    assert [e["event"] for e in events][-1] == "done"
    meta = next(e["data"] for e in events if e["event"] == "meta")
    assert meta["route"] == "question" and meta["sources"][0]["title"] == "Refund Timelines"
    assert len(deps.conversations.msgs) == 2          # question + answer saved


def test_greeting_skips_search():
    deps, events = run("hi")
    assert steps(events) == ["classify"]
    assert deps.knowledge.searches == []


def test_nothing_found_widens_search_once():
    deps, events = run("Who is the CEO?")
    assert steps(events) == ["classify", "rewrite", "retrieve", "broaden", "retrieve"]
    (_, s1, c1), (q2, s2, c2) = deps.knowledge.searches
    assert q2.startswith("standalone:") and s2 < s1 and c2 > c1


def test_talk_to_a_person_asks_for_the_ticket_form():
    deps, events = run("I want to talk to a person please")
    text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert "form" in text
    assert {"event": "handoff", "data": {"form": True}} in events     # the panel shows the ticket form
    assert deps.tickets.rows == {}                                      # the form opens the ticket
    done = next(e["data"] for e in events if e["event"] == "done")
    assert done["usage"]["input"] == 0 and done["usage"]["route"] == "handoff"


def test_tool_use_is_reported():
    _, events = run("Where is SE10482931?")
    assert {"event": "tool", "data": {"name": "lookup_order"}} in events


def test_model_can_hand_over_to_a_person():
    # subtler requests go through the model, which calls open_support_ticket -> the form is shown
    _, events = run("I want to make a complaint about a late refund")
    assert {"event": "tool", "data": {"name": "open_support_ticket"}} in events
    assert {"event": "handoff", "data": {"form": True}} in events


def test_follow_up_is_rewritten_with_history():
    deps, _ = run("How long does a refund take?")
    conv_id = deps.conversations.msgs[0]["conversation_id"]
    deps, events = run("how long does it take?", conversation_id=conv_id, deps=deps)
    meta = next(e["data"] for e in events if e["event"] == "meta")
    assert meta["query"] == "standalone: how long does it take?"


def test_router_rules():
    for greeting in ("hi", "Assalam o Alaikum", "assalamu alaikum", "AOA", "thanks!", "shukriya"):
        assert classify({"question": greeting})["route"] == "greeting", greeting
    for ask in ("can I speak to a human agent?", "I want to talk", "connect me to customer service",
                "agent se baat karni hai", "kisi insaan se baat karni hai", "real person please"):
        assert classify({"question": ask})["route"] == "handoff", ask
    assert classify({"question": "how do I talk about returns in a review?"})["route"] == "question"
    assert classify({"question": "refund kab milega?"})["route"] == "question"


def test_edges():
    assert edges.after_classify({"route": "greeting"}) == "generate"
    assert edges.after_retrieve({"results": [], "attempts": 0}) == "broaden"
    assert edges.after_retrieve({"results": [], "attempts": 1}) == "generate"
