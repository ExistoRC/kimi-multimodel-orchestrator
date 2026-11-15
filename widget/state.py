from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

METADATA_RE = re.compile(r"<!--\s*KIMI_MULTIMODEL_TASK\s*([\s\S]*?)-->")
TASK_ID_RE = re.compile(r"(?:^|\n)\s*-?\s*Task ID:\s*([A-Za-z0-9._#-]+)", re.IGNORECASE)


def short_text(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def model_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("alias", "id", "name", "model"):
            if isinstance(value.get(key), str):
                return value[key]
    return "未标记"


def task_metadata(prompt: Any, agent_name: str) -> dict[str, str]:
    if not isinstance(prompt, str):
        return {"task_id": "", "summary": "", "profile": agent_name, "tier": "—", "model": "未标记", "modality": "text"}
    match = METADATA_RE.search(prompt)
    metadata: dict[str, Any] = {}
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                metadata = parsed
        except (json.JSONDecodeError, TypeError):
            pass
    remainder = prompt[match.end():] if match else prompt
    summary = metadata.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = next((line.strip(" #\t") for line in remainder.splitlines() if line.strip()), "子代理任务")
    return {
        "task_id": short_text(metadata.get("task_id"), 128),
        "summary": short_text(summary),
        "profile": short_text(metadata.get("profile") or agent_name, 80),
        "tier": short_text(metadata.get("tier") or "—", 16),
        "model": short_text(metadata.get("model") or "未标记", 120),
        "modality": short_text(metadata.get("modality") or "text", 16),
    }


@dataclass
class TaskState:
    task_id: str
    base_id: str
    summary: str
    profile: str
    tier: str
    model: str
    modality: str
    agent_name: str
    status: str
    started_at: float
    ended_at: float | None = None
    uncertain: bool = False

    def snapshot(self, now: float) -> dict[str, Any]:
        end = self.ended_at if self.ended_at is not None else now
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "profile": self.profile,
            "tier": self.tier,
            "model": self.model,
            "modality": self.modality,
            "status": self.status,
            "elapsed": max(0, int(end - self.started_at)),
            "uncertain": self.uncertain,
        }


@dataclass
class SessionState:
    session_id: str
    title: str = "当前工程"
    cwd: str = ""
    project: str = "未知项目"
    main_model: str = "未标记"
    phase: str = "idle"
    detail: str = "等待新的工程任务"
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turn_started_at: float | None = None
    active: bool = True
    tasks: dict[str, TaskState] = field(default_factory=dict)
    pending_dispatches: list[dict[str, Any]] = field(default_factory=list)


class StateStore:
    def __init__(self, default_main_model: str = "") -> None:
        self.default_main_model = default_main_model or "未标记"
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.RLock()

    def _session(self, payload: dict[str, Any], now: float) -> SessionState:
        session_id = str(payload.get("session_id") or "unknown")
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionState(
                session_id=session_id,
                main_model=self.default_main_model,
                started_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = session
        cwd = str(payload.get("cwd") or "")
        if cwd:
            session.cwd = cwd
            session.project = Path(cwd).name
        title = payload.get("session_title")
        if isinstance(title, str) and title.strip():
            session.title = short_text(title, 100)
        session.updated_at = now
        return session

    def apply(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        event = payload.get("hook_event_name")
        if not isinstance(event, str):
            return
        now = time.time()
        with self._lock:
            session = self._session(payload, now)
            handler = getattr(self, f"_on_{self._snake(event)}", None)
            if handler:
                handler(session, payload, now)

    @staticmethod
    def _snake(value: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()

    def _on_session_start(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        session.active = True
        session.phase = "idle"
        session.detail = "会话已就绪"
        model = model_name(payload.get("model"))
        if model != "未标记":
            session.main_model = model

    def _on_session_end(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        session.active = False
        session.phase = "idle"
        session.detail = "会话已关闭"
        for task in session.tasks.values():
            if task.status == "working":
                task.status = "stopped"
                task.ended_at = now

    def _on_turn_started(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        origin = str(payload.get("origin_kind") or "")
        if origin == "system_trigger":
            return
        if origin == "user":
            session.tasks.clear()
            session.turn_started_at = now
            session.phase = "planning"
            session.detail = "主代理正在理解目标并规划"
        else:
            if session.turn_started_at is None:
                session.turn_started_at = now
            session.phase = "working"
            session.detail = "主代理正在处理任务结果"
        session.active = True

    def _on_pre_tool_use(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        tool_name = payload.get("tool_name")
        if tool_name not in {"Agent", "AgentSwarm"}:
            return
        arguments = payload.get("tool_input")
        if not isinstance(arguments, dict) or arguments.get("resume"):
            return
        items = arguments.get("items") if tool_name == "AgentSwarm" else None
        remaining = len(items) if isinstance(items, list) else 1
        if remaining < 1:
            return
        session.pending_dispatches.append({
            "profile": str(arguments.get("subagent_type") or "coder"),
            "model": str(arguments.get("model") or "未显式指定"),
            "prompt": arguments.get("prompt") if tool_name == "Agent" else arguments.get("prompt_template"),
            "kind": "swarm" if tool_name == "AgentSwarm" else "agent",
            "remaining": remaining,
            "created_at": now,
        })
        session.pending_dispatches = [item for item in session.pending_dispatches if now - item["created_at"] <= 900]

    def _take_dispatch(self, session: SessionState, agent_name: str, prompt: Any, now: float) -> str:
        session.pending_dispatches = [item for item in session.pending_dispatches if now - item["created_at"] <= 900]
        matching = [item for item in session.pending_dispatches if item["profile"] == agent_name]
        if not matching:
            return ""
        exact = [item for item in matching if item["kind"] == "agent" and item["prompt"] == prompt]
        swarm = [item for item in matching if item["kind"] == "swarm"]
        candidates = exact or swarm
        if not candidates and len(matching) == 1:
            candidates = matching
        if not candidates and len({item["model"] for item in matching}) == 1:
            candidates = matching
        if not candidates:
            return ""
        selected = candidates[0]
        selected["remaining"] -= 1
        if selected["remaining"] <= 0:
            session.pending_dispatches.remove(selected)
        return selected["model"]

    def _on_subagent_start(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        agent_name = str(payload.get("agent_name") or "coder")
        prompt = payload.get("prompt")
        metadata = task_metadata(prompt, agent_name)
        dispatched_model = self._take_dispatch(session, agent_name, prompt, now)
        if metadata["model"] == "未标记" and dispatched_model:
            metadata["model"] = dispatched_model
        base_id = metadata["task_id"] or f"{agent_name}-{int(now * 1000)}"
        task_id = base_id
        suffix = 2
        while task_id in session.tasks:
            task_id = f"{base_id}#{suffix}"
            suffix += 1
        session.tasks[task_id] = TaskState(
            task_id=task_id,
            base_id=base_id,
            summary=metadata["summary"],
            profile=metadata["profile"],
            tier=metadata["tier"],
            model=metadata["model"],
            modality=metadata["modality"],
            agent_name=agent_name,
            status="working",
            started_at=now,
        )
        session.phase = "working"
        session.detail = f"{agent_name} 正在执行子任务"
        session.active = True

    def _on_subagent_stop(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        response = payload.get("response")
        match = TASK_ID_RE.search(response) if isinstance(response, str) else None
        response_id = match.group(1) if match else ""
        agent_name = str(payload.get("agent_name") or "")
        candidates = [task for task in session.tasks.values() if task.status == "working"]
        task = next((item for item in candidates if item.task_id == response_id), None)
        if task is None and response_id:
            task = next((item for item in candidates if item.base_id == response_id), None)
        if task is None:
            matching = [item for item in candidates if not agent_name or item.agent_name == agent_name]
            if len(matching) == 1:
                task = matching[0]
            elif matching:
                task = min(matching, key=lambda item: item.started_at)
                task.uncertain = True
        if task:
            task.status = "delivered"
            task.ended_at = now
        active = any(item.status == "working" for item in session.tasks.values())
        session.phase = "working" if active else "review"
        session.detail = "仍有子代理工作" if active else "子代理已交付，等待主代理验收"

    def _on_permission_request(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        session.phase = "waiting"
        session.detail = f"等待授权：{short_text(payload.get('tool_name') or '工具调用', 80)}"

    def _on_permission_result(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        if self.active_count(session):
            session.phase = "working"
        elif self.pending_count(session):
            session.phase = "review"
        else:
            session.phase = "working"
        session.detail = "授权已处理，继续执行"

    def _on_task_started(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        session.phase = "working"
        session.detail = short_text(payload.get("description") or "后台任务正在运行")

    def _on_stop(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        if self.active_count(session):
            session.phase = "working"
            return
        for task in session.tasks.values():
            if task.status == "delivered":
                task.status = "closed"
        session.phase = "finished"
        session.detail = "本轮已结束；最终验收以主代理答复为准"

    def _on_stop_failure(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        session.phase = "error"
        session.detail = short_text(payload.get("error_message") or payload.get("error_type") or "本轮执行失败")

    def _on_interrupt(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        session.phase = "interrupted"
        session.detail = "用户中断了当前轮次"

    def _on_notification(self, session: SessionState, payload: dict[str, Any], now: float) -> None:
        if not self.active_count(session) and not self.pending_count(session):
            session.detail = "后台任务状态已更新"

    @staticmethod
    def active_count(session: SessionState) -> int:
        return sum(task.status == "working" for task in session.tasks.values())

    @staticmethod
    def pending_count(session: SessionState) -> int:
        return sum(task.status == "delivered" for task in session.tasks.values())

    def snapshot(self, session_id: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            if not self._sessions:
                return self._empty_snapshot(now)
            if session_id is None:
                session = max(self._sessions.values(), key=lambda item: item.updated_at)
            else:
                session = self._sessions.get(session_id) or max(self._sessions.values(), key=lambda item: item.updated_at)
            tasks = sorted(session.tasks.values(), key=lambda item: item.started_at)
            return {
                "session_id": session.session_id,
                "title": session.title,
                "project": session.project,
                "main_model": session.main_model,
                "phase": session.phase,
                "detail": session.detail,
                "active": session.active,
                "active_count": self.active_count(session),
                "pending_count": self.pending_count(session),
                "turn_elapsed": max(0, int(now - session.turn_started_at)) if session.turn_started_at else 0,
                "updated_at": session.updated_at,
                "tasks": [task.snapshot(now) for task in tasks],
                "session_count": len(self._sessions),
            }

    @staticmethod
    def _empty_snapshot(now: float) -> dict[str, Any]:
        return {
            "session_id": "", "title": "当前工程", "project": "尚未连接会话",
            "main_model": "等待 SessionStart", "phase": "idle", "detail": "等待 Kimi Code 工程事件",
            "active": False, "active_count": 0, "pending_count": 0, "turn_elapsed": 0,
            "updated_at": now, "tasks": [], "session_count": 0,
        }
