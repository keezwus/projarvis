from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import time

import anthropic
import requests

API_URL = os.environ.get("PROJARVIS_API_URL", "http://localhost:8000")

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "agent_system_prompt.md"
SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

SESSION_DB: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3600  # evict sessions idle for >1 hour
_CLIENT: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic()
    return _CLIENT


def _evict_expired_sessions() -> None:
    now = time.time()
    expired = [
        sid for sid, s in SESSION_DB.items()
        if now - s.get("_last_access", 0) > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        SESSION_DB.pop(sid, None)

TOOLS = [
    {
        "name": "get_plan",
        "description": "查看当前完整的排程状态：所有任务、已排程时间、约束和覆盖",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "add_tasks",
        "description": "暂存一个或多个新任务。title 放入 metadata。duration_minutes 以分钟为单位",
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "duration_minutes": {"type": "integer"},
                            "priority": {"type": "integer", "default": 100},
                            "metadata": {"type": "object"},
                        },
                        "required": ["title", "duration_minutes"],
                    },
                }
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "modify_task",
        "description": "修改已有任务的属性",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "title": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "priority": {"type": "integer"},
                "metadata": {"type": "object"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_tasks",
        "description": "删除一个或多个任务",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["task_ids"],
        },
    },
    {
        "name": "block_time",
        "description": "屏蔽一个或多个时间段（如休息、开会）。date 格式 YYYY-MM-DD，start/end 格式 HH:MM",
        "input_schema": {
            "type": "object",
            "properties": {
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                        },
                        "required": ["date", "start", "end"],
                    },
                }
            },
            "required": ["blocks"],
        },
    },
    {
        "name": "set_constraints",
        "description": "设置排程约束。mode=replace 替换全部，mode=append 追加（同类型覆盖）",
        "input_schema": {
            "type": "object",
            "properties": {
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "params": {"type": "object"},
                        },
                        "required": ["type"],
                    },
                },
                "mode": {"type": "string", "enum": ["replace", "append"]},
            },
            "required": ["constraints"],
        },
    },
    {
        "name": "what_if",
        "description": "在暂存的变更上运行引擎，查看调度结果和影响",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def _http_get(path: str) -> dict:
    resp = requests.get(f"{API_URL}{path}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def _http_post(path: str, body: dict | None = None) -> dict:
    resp = requests.post(f"{API_URL}{path}", json=body or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _http_delete(path: str, body: dict | None = None) -> dict:
    resp = requests.delete(f"{API_URL}{path}", json=body or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _execute_tool(name: str, tool_input: dict) -> str:
    """Execute a tool call against the app API. Returns JSON string for tool_result."""
    try:
        if name == "get_plan":
            result = _http_get("/api/v1/plan")
        elif name == "add_tasks":
            result = _http_post("/api/v1/tasks/add", tool_input)
        elif name == "modify_task":
            task_id = tool_input["task_id"]
            body = {k: v for k, v in tool_input.items() if k != "task_id"}
            result = _http_post(f"/api/v1/tasks/{task_id}/modify", body)
        elif name == "delete_tasks":
            result = _http_delete("/api/v1/tasks", tool_input)
        elif name == "block_time":
            result = _http_post("/api/v1/block-time", tool_input)
        elif name == "set_constraints":
            result = _http_post("/api/v1/constraints", tool_input)
        elif name == "what_if":
            result = _http_post("/api/v1/what-if")
        else:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)
    except requests.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        return json.dumps({"error": f"API error: {detail}"}, ensure_ascii=False)
    except requests.RequestException as e:
        return json.dumps({"error": f"Connection error: {e}"}, ensure_ascii=False)


def _claude_round(client: anthropic.Anthropic, session: dict) -> dict:
    """Call Claude and return {status, tools_to_approve, response_text, assistant_content}."""
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=session["messages"],
    )

    if resp.stop_reason == "end_turn":
        text = "".join(
            block.text for block in resp.content if block.type == "text"
        )
        session["messages"].append({"role": "assistant", "content": resp.content})
        return {"status": "completed", "tools_to_approve": None, "response_text": text}

    if resp.stop_reason == "tool_use":
        tools = [
            {"id": block.id, "name": block.name, "input": block.input}
            for block in resp.content
            if block.type == "tool_use"
        ]
        session["pending_assistant"] = resp.content
        session["pending_tools"] = tools
        session["status"] = "awaiting_tools"
        return {"status": "awaiting_tools", "tools_to_approve": tools, "response_text": None}

    # unexpected stop_reason
    return {"status": "completed", "tools_to_approve": None, "response_text": None}


def send_user_message(session_id: str | None, user_text: str) -> dict:
    _evict_expired_sessions()

    if session_id and session_id in SESSION_DB:
        session = SESSION_DB[session_id]
    else:
        sid = session_id or uuid.uuid4().hex[:12]
        session = {
            "session_id": sid,
            "messages": [],
            "pending_tools": [],
            "status": "idle",
        }
        SESSION_DB[sid] = session

    session["_last_access"] = time.time()
    session["messages"].append({"role": "user", "content": user_text})
    result = _claude_round(_get_client(), session)
    return {
        "session_id": session["session_id"],
        **result,
    }


def approve_pending_tools(session_id: str, approved: bool) -> dict:
    session = SESSION_DB.get(session_id)
    if not session:
        return {
            "session_id": session_id,
            "status": "completed",
            "tools_to_approve": None,
            "response_text": "Session not found",
        }

    if session.get("status") != "awaiting_tools":
        return {
            "session_id": session_id,
            "status": "completed",
            "tools_to_approve": None,
            "response_text": "No tools awaiting approval",
        }

    pending = session.pop("pending_tools", [])
    assistant_content = session.pop("pending_assistant", [])

    # Append assistant message (tool_use blocks)
    session["messages"].append({"role": "assistant", "content": assistant_content})

    # Execute and append tool_results
    for tool in pending:
        if approved:
            content = _execute_tool(tool["name"], dict(tool["input"]))
        else:
            content = "用户未批准此操作"
        session["messages"].append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool["id"], "content": content}
            ],
        })

    session["status"] = "idle"
    session["_last_access"] = time.time()

    result = _claude_round(_get_client(), session)
    return {
        "session_id": session_id,
        **result,
    }


def clear_session(session_id: str) -> None:
    SESSION_DB.pop(session_id, None)
