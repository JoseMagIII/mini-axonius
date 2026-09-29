from itertools import count

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app import sync
from app.agent import build_agent, events_from_update
from tests.conftest import FakeDocker, FakeNvd

pytestmark = pytest.mark.integration
_ids = count()


class ScriptedModel(GenericFakeChatModel):
    """Plays back a fixed list of Claude replies and records what it was sent."""

    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


def calls(*pairs):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}"} for name, args in pairs])


def run(agent, question, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    events = []
    for update in agent.stream({"messages": [HumanMessage(question)], "steps": 0}, config, stream_mode="updates"):
        for node, delta in update.items():
            events.extend(events_from_update(node, delta))
    return events


@pytest.fixture
def synced(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())


def scripted(*replies):
    return ScriptedModel(messages=iter(replies), seen=[])


def test_answers_from_real_query_results(synced):
    model = scripted(
        calls(("get_schema", {})),
        calls(("run_sql", {"sql": "SELECT hostname FROM gap_missing_edr ORDER BY hostname"})),
        AIMessage("api-02 and jump-01 have no EDR agent."),
    )
    events = run(build_agent(model), "Which servers have no EDR?")

    assert [e["type"] for e in events] == ["tool_call", "result", "tool_call", "result", "answer"]
    assert events[1]["tables"] >= 9
    result = events[3]
    assert result["rows"] == [{"hostname": "api-02"}, {"hostname": "jump-01"}]
    assert result["sql"].endswith("LIMIT 200")
    assert events[-1]["text"] == "api-02 and jump-01 have no EDR agent."


def test_guardrail_blocks_writes_and_the_agent_recovers(synced):
    model = scripted(
        calls(("run_sql", {"sql": "DELETE FROM identities WHERE username = 'dave'"})),
        calls(("run_sql", {"sql": "SELECT count(*) AS n FROM identities"})),
        AIMessage("I can't delete data, but there are 5 identities."),
    )
    events = run(build_agent(model), "Delete dave")

    assert [e["type"] for e in events] == ["tool_call", "blocked", "tool_call", "result", "answer"]
    assert "Only SELECT" in events[1]["reason"]
    assert events[3]["rows"] == [{"n": 5}]
    blocked_reply = model.seen[1][-1]
    assert blocked_reply.content.startswith("Blocked by the guardrail")


def test_one_blocked_query_stops_the_whole_step(synced):
    model = scripted(
        calls(("run_sql", {"sql": "SELECT 1"}), ("run_sql", {"sql": "DROP TABLE identities"})),
        AIMessage("Done."),
    )
    events = run(build_agent(model), "Mixed")
    assert [e["type"] for e in events] == ["tool_call", "tool_call", "blocked", "answer"]
    assert len(model.seen[1]) == 1 + 1 + 1 + 2  # system, question, tool calls, one reply per call


def test_database_errors_go_back_to_the_model(synced):
    model = scripted(
        calls(("run_sql", {"sql": "SELECT no_such_column FROM assets_unified"})),
        AIMessage("That column doesn't exist."),
    )
    events = run(build_agent(model), "Bad column")
    assert events[1]["type"] == "error"
    assert "no_such_column" in events[1]["message"]
    assert events[-1]["type"] == "answer"


def test_stops_at_the_step_limit(synced):
    model = scripted(*[calls(("get_schema", {})) for _ in range(10)])
    events = run(build_agent(model, max_steps=3), "Loop forever")
    assert sum(e["type"] == "tool_call" for e in events) == 3
    assert events[-1] == {
        "type": "answer",
        "text": "I stopped after 3 steps without a final answer. Try a narrower question.",
    }


def test_remembers_earlier_turns_in_the_same_thread(synced):
    model = scripted(AIMessage("There are 9 assets."), AIMessage("5 of them are in prod."))
    agent = build_agent(model)
    run(agent, "How many assets?", thread="memory")
    run(agent, "How many of those are prod?", thread="memory")
    second_turn = [m.content for m in model.seen[1]]
    assert "How many assets?" in second_turn and "There are 9 assets." in second_turn


def test_threads_do_not_share_memory(synced):
    model = scripted(AIMessage("First."), AIMessage("Second."))
    agent = build_agent(model)
    run(agent, "Question A", thread="a")
    run(agent, "Question B", thread="b")
    assert "Question A" not in [m.content for m in model.seen[1]]
