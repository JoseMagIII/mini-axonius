import json
from typing import Annotated, Any

from fastapi.encoders import jsonable_encoder
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from psycopg import Error as DatabaseError
from typing_extensions import TypedDict

from app.config import anthropic_headers, get_settings
from app.db import reader_connection
from app.guardrail import check_sql

SYSTEM_PROMPT = """You are the asset inventory analyst for Acme. Answer questions about Acme's servers, \
software, vulnerabilities, and people by querying the inventory database.

- Call get_schema before writing SQL if you haven't seen the schema in this conversation.
- Use run_sql with PostgreSQL. Prefer the views: assets_unified has one row per asset, and the gap_* views \
list known security gaps. Raw tables keep the full sync history.
- Hostnames are lowercase short names, like web-01. Use normalize_hostname() on raw tables.
- The database is read-only. Never try to change data.
- Answer in a few short sentences or a short list, and name the hostnames involved. If the data can't \
answer the question, say so."""


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int


TOOL_LABELS = {"get_schema": "Reading the database schema", "run_sql": "Running SQL"}


def _check(sql: str):
    return check_sql(sql, get_settings().query_row_limit)


@tool(response_format="content_and_artifact")
def get_schema() -> tuple[str, dict]:
    """List every table and view in the inventory database with its columns and types."""
    with reader_connection() as conn:
        rows = conn.execute(
            """SELECT c.table_name, t.table_type, string_agg(c.column_name || ' ' || c.data_type, ', '
                      ORDER BY c.ordinal_position) AS columns
               FROM information_schema.columns c
               JOIN information_schema.tables t USING (table_schema, table_name)
               WHERE c.table_schema = 'public'
               GROUP BY c.table_name, t.table_type
               ORDER BY t.table_type DESC, c.table_name"""
        ).fetchall()
    text = "\n".join(
        f"{'view' if r['table_type'] == 'VIEW' else 'table'} {r['table_name']}: {r['columns']}" for r in rows
    )
    return text, {"summary": f"Found {len(rows)} tables and views"}


@tool(response_format="content_and_artifact")
def run_sql(sql: str) -> tuple[str, dict]:
    """Run one read-only PostgreSQL SELECT query against the inventory database and return the rows."""
    # The guardrail node already vetted this; checking again here adds the row limit and keeps the tool safe alone.
    checked = _check(sql)
    if not checked.allowed:
        return f"Blocked: {checked.reason}", {"sql": sql, "blocked": True, "reason": checked.reason}
    try:
        with reader_connection() as conn:
            cursor = conn.execute(checked.sql)
            rows = jsonable_encoder(cursor.fetchall())
            columns = [c.name for c in cursor.description or []]
    except DatabaseError as error:
        message = str(error).strip()
        return f"The query failed: {message}", {"sql": checked.sql, "error": message}
    summary = f"Returned {len(rows)} {'row' if len(rows) == 1 else 'rows'}"
    return json.dumps(rows), {"summary": summary, "sql": checked.sql, "columns": columns, "rows": rows}


TOOLS = [get_schema, run_sql]


def default_model() -> BaseChatModel:
    settings = get_settings()
    return init_chat_model(
        settings.claude_model,
        model_provider="anthropic",
        api_key=settings.anthropic_api_key,
        default_headers=anthropic_headers(settings),
        temperature=0,
        max_tokens=4096,
    )


def build_agent(model: BaseChatModel | None = None, max_steps: int | None = None):
    """Agent node calls Claude, guardrail node vets its SQL, tools node runs it. Loops until Claude answers."""
    llm = (model or default_model()).bind_tools(TOOLS)
    step_limit = max_steps or get_settings().agent_max_steps

    def agent(state: AgentState) -> dict:
        if state["steps"] >= step_limit:
            return {
                "messages": [
                    AIMessage(f"I stopped after {step_limit} steps without a final answer. Try a narrower question.")
                ]
            }
        response = llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response], "steps": state["steps"] + 1}

    def guardrail(state: AgentState) -> dict:
        calls = state["messages"][-1].tool_calls
        verdicts = {c["id"]: _check(c["args"].get("sql", "")) for c in calls if c["name"] == "run_sql"}
        blocked = {call_id: v for call_id, v in verdicts.items() if not v.allowed}
        if not blocked:
            return {}
        # Answer every call in this turn so the conversation stays valid, then send Claude back to try again.
        messages = []
        for call in calls:
            verdict = blocked.get(call["id"])
            if verdict:
                content = f"Blocked by the guardrail: {verdict.reason}"
                artifact = {"sql": verdict.sql, "blocked": True, "reason": verdict.reason}
            else:
                content, artifact = "Not run, because another query in the same step was blocked.", {"skipped": True}
            messages.append(
                ToolMessage(content, tool_call_id=call["id"], name=call["name"], status="error", artifact=artifact)
            )
        return {"messages": messages}

    def after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        return "guardrail" if isinstance(last, AIMessage) and last.tool_calls else END

    def after_guardrail(state: AgentState) -> str:
        return "agent" if isinstance(state["messages"][-1], ToolMessage) else "tools"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("guardrail", guardrail)
    graph.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", after_agent, ["guardrail", END])
    graph.add_conditional_edges("guardrail", after_guardrail, ["agent", "tools"])
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=InMemorySaver())


def events_from_update(update: dict[str, Any] | None) -> list[dict]:
    """Turns one graph step into the events the UI renders."""
    events = []
    for message in (update or {}).get("messages", []):
        if isinstance(message, AIMessage):
            if message.tool_calls and message.text.strip():
                events.append({"type": "thought", "text": message.text})
            events.extend(
                {"type": "tool_call", "label": TOOL_LABELS.get(c["name"], c["name"]), "sql": c["args"].get("sql")}
                for c in message.tool_calls
            )
            if not message.tool_calls:
                events.append({"type": "answer", "text": message.text})
        elif isinstance(message, ToolMessage):
            artifact = message.artifact or {}
            if artifact.get("blocked"):
                events.append({"type": "blocked", "sql": artifact["sql"], "reason": artifact["reason"]})
            elif artifact.get("skipped"):
                continue
            elif artifact.get("error") or message.status == "error":
                events.append(
                    {
                        "type": "error",
                        "sql": artifact.get("sql"),
                        "message": artifact.get("error", message.text),
                    }
                )
            else:
                events.append({"type": "result", **artifact})
    return events
