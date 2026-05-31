"""Trace-only monkeypatch instrumentation for local tau2 runs.

This module intentionally lives outside ``vendor/tau2-bench``. It observes tau2
runtime activity by wrapping public functions/methods and writing JSONL events;
it never changes tau2 inputs, task state, or control flow.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import functools
import hashlib
import importlib
import inspect
import json
import os
import pathlib
import sys
import traceback
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
VENDOR_SRC = VENDOR_DIR / "src"
VENDOR_VENV = VENDOR_DIR / ".venv"

HOOK_MAP: dict[str, dict[str, str]] = {
    "batch_run_tasks": {
        "path": "vendor/tau2-bench/src/tau2/runner/batch.py",
        "module": "tau2.runner.batch",
        "qualname": "run_tasks",
        "events": "run/batch start/end and result persistence intent",
    },
    "batch_run_single_task": {
        "path": "vendor/tau2-bench/src/tau2/runner/batch.py",
        "module": "tau2.runner.batch",
        "qualname": "run_single_task",
        "events": "simulation task start/end wrapper context",
    },
    "layer1_run_simulation": {
        "path": "vendor/tau2-bench/src/tau2/runner/simulation.py",
        "module": "tau2.runner.simulation",
        "qualname": "run_simulation",
        "events": "simulation execution/evaluation envelope",
    },
    "batch_run_simulation_alias": {
        "path": "vendor/tau2-bench/src/tau2/runner/batch.py",
        "module": "tau2.runner.batch",
        "qualname": "run_simulation",
        "events": "batch module alias for Layer 1 simulation execution/evaluation envelope",
    },
    "simulation_evaluate_alias": {
        "path": "vendor/tau2-bench/src/tau2/runner/simulation.py",
        "module": "tau2.runner.simulation",
        "qualname": "evaluate_simulation",
        "events": "simulation module alias for evaluation start/end",
    },
    "orchestrator_run": {
        "path": "vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py",
        "module": "tau2.orchestrator.orchestrator",
        "qualname": "Orchestrator.run",
        "events": "orchestrator run start/end",
    },
    "orchestrator_step": {
        "path": "vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py",
        "module": "tau2.orchestrator.orchestrator",
        "qualname": "Orchestrator.step",
        "events": "turn start/end, message observed, agent/user responses, tool-call requests",
    },
    "environment_get_response": {
        "path": "vendor/tau2-bench/src/tau2/environment/environment.py",
        "module": "tau2.environment.environment",
        "qualname": "Environment.get_response",
        "events": "tool dispatch start/end and state hash before/after tool",
    },
    "toolkit_use_tool": {
        "path": "vendor/tau2-bench/src/tau2/environment/toolkit.py",
        "module": "tau2.environment.toolkit",
        "qualname": "ToolKitBase.use_tool",
        "events": "low-level toolkit dispatch start/end",
    },
    "evaluator_evaluate_simulation": {
        "path": "vendor/tau2-bench/src/tau2/evaluator/evaluator.py",
        "module": "tau2.evaluator.evaluator",
        "qualname": "evaluate_simulation",
        "events": "evaluation start/end and reward/check summary",
    },
    "simulation_model_dump": {
        "path": "vendor/tau2-bench/src/tau2/data_model/simulation.py",
        "module": "tau2.data_model.simulation",
        "qualname": "Results.save",
        "events": "result persistence start/end",
    },
    "agent_base_generate_contract": {
        "path": "vendor/tau2-bench/src/tau2/agent/base_agent.py",
        "module": "tau2.agent.base_agent",
        "qualname": "HalfDuplexAgent.generate_next_message",
        "events": "base contract only; concrete agent responses observed via orchestrator_step",
    },
    "user_simulator_generate_contract": {
        "path": "vendor/tau2-bench/src/tau2/user/user_simulator.py",
        "module": "tau2.user.user_simulator",
        "qualname": "UserSimulator.generate_next_message",
        "events": "user response start/end when concrete class method is present",
    },
}


def ensure_vendor_import_path() -> None:
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    src = str(VENDOR_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    if VENDOR_VENV.exists():
        candidates = sorted((VENDOR_VENV / "lib").glob("python*/site-packages"))
        for site_packages in candidates:
            site = str(site_packages)
            if site not in sys.path:
                sys.path.insert(1, site)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def stable_hash(value: Any) -> str:
    try:
        blob = json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":"))
    except Exception:
        blob = repr(value)
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()


def to_jsonable(value: Any, *, max_repr: int = 2000) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, pathlib.Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v, max_repr=max_repr) for v in list(value)[:50]]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v, max_repr=max_repr) for k, v in list(value.items())[:100]}
    for attr in ("model_dump", "dict"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return to_jsonable(method(), max_repr=max_repr)
            except Exception:
                pass
    text = repr(value)
    if len(text) > max_repr:
        text = text[:max_repr] + "…"
    return {"repr": text, "class": value.__class__.__name__}


def message_summary(message: Any) -> dict[str, Any]:
    if message is None:
        return {}
    payload = to_jsonable(message)
    role = getattr(message, "role", None)
    if role is not None and not isinstance(role, str):
        role = getattr(role, "value", repr(role))
    return {
        "role": role,
        "class": message.__class__.__name__,
        "is_tool_call": bool(getattr(message, "is_tool_call", lambda: False)()),
        "tool_calls": to_jsonable(getattr(message, "tool_calls", None)),
        "content_preview": str(getattr(message, "content", ""))[:500],
        "raw": payload,
    }


def object_state_hash(obj: Any) -> str | None:
    for method_name in ("get_db_hash",):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                return str(method())
            except Exception:
                pass
    db = getattr(obj, "db", None)
    if db is not None:
        return stable_hash(db)
    tools = getattr(obj, "tools", None)
    user_tools = getattr(obj, "user_tools", None)
    pieces: dict[str, Any] = {}
    for name, toolkit in (("tools", tools), ("user_tools", user_tools)):
        if toolkit is None:
            continue
        pieces[name] = object_state_hash(toolkit)
    if pieces:
        return stable_hash(pieces)
    return None


@dataclass
class PatchRecord:
    module_name: str
    owner: Any
    attr: str
    original: Any


class RuntimeTraceWriter:
    def __init__(self, run_dir: pathlib.Path, run_id: str | None = None, phase: str = "runtime_trace"):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "runtime_events.jsonl"
        self.run_id = run_id or self.run_dir.name
        self.phase = phase
        self._counter = 0
        self._handle = self.path.open("a", encoding="utf-8")
        self.event_counts: dict[str, int] = {}
        self.last_event_id: str | None = None
        self.errors: list[dict[str, Any]] = []

    def close(self) -> None:
        self._handle.close()

    def record(
        self,
        *,
        component: str,
        event_type: str,
        task_id: str | None = None,
        turn_index: int | None = None,
        tool_name: str | None = None,
        message_role: str | None = None,
        state_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
    ) -> str:
        self._counter += 1
        event_id = f"rt-{self._counter:06d}-{uuid.uuid4().hex[:8]}"
        event = {
            "event_id": event_id,
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "phase": self.phase,
            "component": component,
            "event_type": event_type,
            "task_id": task_id,
            "turn_index": turn_index,
            "tool_name": tool_name,
            "message_role": message_role,
            "state_hash": state_hash,
            "payload": {"runtime_trace": to_jsonable(payload or {})},
            "parent_event_id": parent_event_id,
        }
        self._handle.write(json.dumps(event, sort_keys=True) + "\n")
        self._handle.flush()
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1
        self.last_event_id = event_id
        return event_id


class Tau2RuntimeTracer:
    def __init__(self, writer: RuntimeTraceWriter):
        self.writer = writer
        self.patches: list[PatchRecord] = []
        self.installed_hooks: list[str] = []
        self.deferred_hooks: list[str] = []

    def __enter__(self) -> "Tau2RuntimeTracer":
        ensure_vendor_import_path()
        self.install()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.uninstall()
        return False

    def _patch(self, hook_name: str, module_name: str, qualname: str, wrapper_factory: Callable[[Any], Any]) -> bool:
        try:
            module = importlib.import_module(module_name)
            parts = qualname.split(".")
            owner: Any = module
            for part in parts[:-1]:
                owner = getattr(owner, part)
            attr = parts[-1]
            original = getattr(owner, attr)
            setattr(owner, attr, wrapper_factory(original))
            self.patches.append(PatchRecord(module_name, owner, attr, original))
            self.installed_hooks.append(hook_name)
            return True
        except Exception as exc:
            self.deferred_hooks.append(hook_name)
            self.writer.errors.append({"hook": hook_name, "error": repr(exc)})
            return False

    def install(self) -> None:
        self._patch("batch_run_tasks", "tau2.runner.batch", "run_tasks", self._wrap_run_tasks)
        self._patch("batch_run_single_task", "tau2.runner.batch", "run_single_task", self._wrap_run_single_task)
        self._patch("layer1_run_simulation", "tau2.runner.simulation", "run_simulation", self._wrap_run_simulation)
        self._patch("batch_run_simulation_alias", "tau2.runner.batch", "run_simulation", self._wrap_run_simulation)
        self._patch("simulation_evaluate_alias", "tau2.runner.simulation", "evaluate_simulation", self._wrap_evaluate_simulation)
        self._patch("orchestrator_run", "tau2.orchestrator.orchestrator", "Orchestrator.run", self._wrap_orchestrator_run)
        self._patch("orchestrator_step", "tau2.orchestrator.orchestrator", "Orchestrator.step", self._wrap_orchestrator_step)
        self._patch("environment_get_response", "tau2.environment.environment", "Environment.get_response", self._wrap_environment_get_response)
        self._patch("toolkit_use_tool", "tau2.environment.toolkit", "ToolKitBase.use_tool", self._wrap_toolkit_use_tool)
        self._patch("evaluator_evaluate_simulation", "tau2.evaluator.evaluator", "evaluate_simulation", self._wrap_evaluate_simulation)
        self._patch("simulation_model_dump", "tau2.data_model.simulation", "Results.save", self._wrap_results_save)
        # These two may be abstract/implementation-dependent. Import validation is still useful.
        self._patch("user_simulator_generate_contract", "tau2.user.user_simulator", "UserSimulator.generate_next_message", self._wrap_user_generate)
        self._validate_contract_only("agent_base_generate_contract")

    def _validate_contract_only(self, hook_name: str) -> None:
        meta = HOOK_MAP[hook_name]
        try:
            module = importlib.import_module(meta["module"])
            owner: Any = module
            for part in meta["qualname"].split("."):
                owner = getattr(owner, part)
            inspect.signature(owner)
            self.installed_hooks.append(hook_name)
        except Exception as exc:
            self.deferred_hooks.append(hook_name)
            self.writer.errors.append({"hook": hook_name, "error": repr(exc)})

    def uninstall(self) -> None:
        while self.patches:
            patch = self.patches.pop()
            setattr(patch.owner, patch.attr, patch.original)

    def _task_id_from(self, obj: Any = None, args: tuple[Any, ...] = ()) -> str | None:
        for candidate in (obj, *(args or ())):
            task = getattr(candidate, "task", None)
            if task is not None:
                return getattr(task, "id", None)
            if getattr(candidate, "id", None) is not None and candidate.__class__.__name__.lower().endswith("task"):
                return getattr(candidate, "id", None)
        return None

    def _wrap_run_tasks(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(config, tasks, *args, **kwargs):
            payload = {"domain": getattr(config, "domain", None), "task_ids": [getattr(t, "id", None) for t in tasks], "save_path": kwargs.get("save_path")}
            eid = self.writer.record(component="tau2.runner.batch", event_type="batch_start", payload=payload)
            try:
                result = original(config, tasks, *args, **kwargs)
                self.writer.record(component="tau2.runner.batch", event_type="batch_end", payload={"status": "ok", "result_type": result.__class__.__name__}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.runner.batch", event_type="batch_end", payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_run_single_task(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(config, task, *args, **kwargs):
            task_id = getattr(task, "id", None)
            eid = self.writer.record(component="tau2.runner.batch", event_type="simulation_start", task_id=task_id, payload={"domain": getattr(config, "domain", None)})
            try:
                result = original(config, task, *args, **kwargs)
                self.writer.record(component="tau2.runner.batch", event_type="simulation_end", task_id=task_id, payload={"status": "ok", "termination_reason": getattr(result, "termination_reason", None)}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.runner.batch", event_type="simulation_end", task_id=task_id, payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_run_simulation(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(orchestrator, *args, **kwargs):
            task_id = self._task_id_from(orchestrator)
            eid = self.writer.record(component="tau2.runner.simulation", event_type="simulation_execution_start", task_id=task_id, state_hash=object_state_hash(getattr(orchestrator, "environment", None)), payload={"evaluation_type": str(kwargs.get("evaluation_type", "all"))})
            try:
                result = original(orchestrator, *args, **kwargs)
                self.writer.record(component="tau2.runner.simulation", event_type="simulation_execution_end", task_id=task_id, state_hash=object_state_hash(getattr(orchestrator, "environment", None)), payload={"status": "ok", "reward_info": to_jsonable(getattr(result, "reward_info", None))}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.runner.simulation", event_type="simulation_execution_end", task_id=task_id, payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_orchestrator_run(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(orchestrator, *args, **kwargs):
            task_id = self._task_id_from(orchestrator)
            eid = self.writer.record(component="tau2.orchestrator", event_type="orchestrator_run_start", task_id=task_id, payload={"simulation_id": getattr(orchestrator, "simulation_id", None)})
            try:
                result = original(orchestrator, *args, **kwargs)
                self.writer.record(component="tau2.orchestrator", event_type="orchestrator_run_end", task_id=task_id, payload={"status": "ok", "steps": getattr(orchestrator, "step_count", None)}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.orchestrator", event_type="orchestrator_run_end", task_id=task_id, payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_orchestrator_step(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(orchestrator, *args, **kwargs):
            task_id = self._task_id_from(orchestrator)
            turn = getattr(orchestrator, "step_count", None)
            before_message = getattr(orchestrator, "message", None)
            eid = self.writer.record(component="tau2.orchestrator", event_type="turn_start", task_id=task_id, turn_index=turn, message_role=getattr(before_message, "role", None), state_hash=object_state_hash(getattr(orchestrator, "environment", None)), payload={"from_role": str(getattr(orchestrator, "from_role", None)), "to_role": str(getattr(orchestrator, "to_role", None)), "message": message_summary(before_message)})
            if getattr(before_message, "is_tool_call", lambda: False)():
                for call in getattr(before_message, "tool_calls", []) or []:
                    self.writer.record(component="tau2.orchestrator", event_type="tool_call_requested", task_id=task_id, turn_index=turn, tool_name=getattr(call, "name", None), payload={"tool_call": to_jsonable(call)}, parent_event_id=eid)
            try:
                result = original(orchestrator, *args, **kwargs)
                after_message = getattr(orchestrator, "message", None)
                role = getattr(after_message, "role", None)
                event_type = "message_observed"
                if str(getattr(orchestrator, "from_role", "")).endswith("AGENT"):
                    event_type = "agent_response"
                elif str(getattr(orchestrator, "from_role", "")).endswith("USER"):
                    event_type = "user_response"
                self.writer.record(component="tau2.orchestrator", event_type=event_type, task_id=task_id, turn_index=turn, message_role=role, state_hash=object_state_hash(getattr(orchestrator, "environment", None)), payload={"from_role": str(getattr(orchestrator, "from_role", None)), "to_role": str(getattr(orchestrator, "to_role", None)), "message": message_summary(after_message)}, parent_event_id=eid)
                self.writer.record(component="tau2.orchestrator", event_type="turn_end", task_id=task_id, turn_index=turn, state_hash=object_state_hash(getattr(orchestrator, "environment", None)), payload={"done": getattr(orchestrator, "done", None), "termination_reason": str(getattr(orchestrator, "termination_reason", None))}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.orchestrator", event_type="turn_end", task_id=task_id, turn_index=turn, payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_environment_get_response(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(environment, message, *args, **kwargs):
            before = object_state_hash(environment)
            tool_name = getattr(message, "name", None)
            eid = self.writer.record(component="tau2.environment", event_type="tool_dispatch_start", tool_name=tool_name, state_hash=before, payload={"requestor": getattr(message, "requestor", None), "arguments": to_jsonable(getattr(message, "arguments", None))})
            try:
                result = original(environment, message, *args, **kwargs)
                after = object_state_hash(environment)
                self.writer.record(component="tau2.environment", event_type="tool_dispatch_end", tool_name=tool_name, state_hash=after, payload={"status": "ok", "state_hash_before": before, "state_hash_after": after, "response": message_summary(result)}, parent_event_id=eid)
                return result
            except Exception as exc:
                after = object_state_hash(environment)
                self.writer.record(component="tau2.environment", event_type="tool_dispatch_end", tool_name=tool_name, state_hash=after, payload={"status": "error", "error": repr(exc), "state_hash_before": before, "state_hash_after": after}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_toolkit_use_tool(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(toolkit, tool_name, *args, **kwargs):
            before = object_state_hash(toolkit)
            eid = self.writer.record(component="tau2.environment.toolkit", event_type="toolkit_dispatch_start", tool_name=tool_name, state_hash=before, payload={"kwargs": kwargs})
            try:
                result = original(toolkit, tool_name, *args, **kwargs)
                after = object_state_hash(toolkit)
                self.writer.record(component="tau2.environment.toolkit", event_type="toolkit_dispatch_end", tool_name=tool_name, state_hash=after, payload={"status": "ok", "state_hash_before": before, "state_hash_after": after, "result": to_jsonable(result)}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.environment.toolkit", event_type="toolkit_dispatch_end", tool_name=tool_name, state_hash=object_state_hash(toolkit), payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_evaluate_simulation(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            task = kwargs.get("task") if "task" in kwargs else (args[1] if len(args) > 1 else None)
            task_id = getattr(task, "id", None)
            eid = self.writer.record(component="tau2.evaluator", event_type="evaluation_start", task_id=task_id, payload={"evaluation_type": str(kwargs.get("evaluation_type", args[2] if len(args) > 2 else None)), "domain": kwargs.get("domain")})
            try:
                result = original(*args, **kwargs)
                self.writer.record(component="tau2.evaluator", event_type="evaluation_end", task_id=task_id, payload={"status": "ok", "reward": getattr(result, "reward", None), "db_check": to_jsonable(getattr(result, "db_check", None)), "action_checks": to_jsonable(getattr(result, "action_checks", None)), "nl_assertions": to_jsonable(getattr(result, "nl_assertions", None))}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.evaluator", event_type="evaluation_end", task_id=task_id, payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_results_save(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(results, path, *args, **kwargs):
            eid = self.writer.record(component="tau2.data_model.simulation", event_type="result_persistence_start", payload={"path": str(path), "format": kwargs.get("format")})
            try:
                out = original(results, path, *args, **kwargs)
                self.writer.record(component="tau2.data_model.simulation", event_type="result_persistence_end", payload={"status": "ok", "path": str(path)}, parent_event_id=eid)
                return out
            except Exception as exc:
                self.writer.record(component="tau2.data_model.simulation", event_type="result_persistence_end", payload={"status": "error", "error": repr(exc), "path": str(path)}, parent_event_id=eid)
                raise
        return wrapped

    def _wrap_user_generate(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(user, message=None, state=None, *args, **kwargs):
            eid = self.writer.record(component="tau2.user", event_type="user_generate_start", message_role=getattr(message, "role", None), payload={"input_message": message_summary(message)})
            try:
                result = original(user, message, state, *args, **kwargs)
                self.writer.record(component="tau2.user", event_type="user_generate_end", payload={"status": "ok", "result": to_jsonable(result)}, parent_event_id=eid)
                return result
            except Exception as exc:
                self.writer.record(component="tau2.user", event_type="user_generate_end", payload={"status": "error", "error": repr(exc)}, parent_event_id=eid)
                raise
        return wrapped

def inspect_hook_targets() -> dict[str, Any]:
    ensure_vendor_import_path()
    inspected: dict[str, Any] = {}
    for name, meta in HOOK_MAP.items():
        item = {**meta, "exists": False, "imported": False, "signature": None, "error": None}
        path = REPO_ROOT / meta["path"]
        item["exists"] = path.is_file()
        try:
            module = importlib.import_module(meta["module"])
            item["imported"] = True
            target: Any = module
            for part in meta["qualname"].split("."):
                target = getattr(target, part)
            try:
                item["signature"] = str(inspect.signature(target))
            except Exception as sig_exc:
                item["signature"] = f"signature unavailable: {sig_exc!r}"
        except Exception as exc:
            item["error"] = repr(exc)
        inspected[name] = item
    return inspected


def write_hook_map(run_dir: pathlib.Path, inspected: dict[str, Any], validated: list[str], deferred: list[str]) -> pathlib.Path:
    path = run_dir / "runtime_hook_map.json"
    payload = {
        "schema": "tau2_runtime_hook_map.v1",
        "generated_at": utc_now(),
        "repo_root": str(REPO_ROOT),
        "validated_hooks": sorted(set(validated)),
        "deferred_hooks": sorted(set(deferred)),
        "hooks": inspected,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_final_state(run_dir: pathlib.Path, status: str, writer: RuntimeTraceWriter, *, extra: dict[str, Any] | None = None) -> pathlib.Path:
    path = run_dir / "runtime_trace_final_state.json"
    payload = {
        "status": status,
        "run_id": writer.run_id,
        "runtime_events_path": "runtime_events.jsonl",
        "event_counts": writer.event_counts,
        "last_event_id": writer.last_event_id,
        "errors": writer.errors,
        "paid_llm_api_calls_made": False,
        "activegraph_controlled_tau2": False,
        "state_packets_fed_back_to_tau2": False,
    }
    if extra:
        payload.update(to_jsonable(extra))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_summary(run_dir: pathlib.Path, status: str, writer: RuntimeTraceWriter, *, validated: list[str], deferred: list[str], command: str | None = None) -> pathlib.Path:
    path = run_dir / "runtime_trace_summary.md"
    lines = [
        "# tau2 runtime trace",
        "",
        f"- status: `{status}`",
        f"- run_id: `{writer.run_id}`",
        f"- runtime events: `{run_dir / 'runtime_events.jsonl'}`",
        f"- event count: `{sum(writer.event_counts.values())}`",
        f"- paid LLM/API calls made: `false`",
        f"- ActiveGraph control of tau2: `false`",
        f"- command: `{command or 'n/a'}`",
        "",
        "## Event counts",
        "",
    ]
    lines.extend(f"- `{name}`: `{count}`" for name, count in sorted(writer.event_counts.items()))
    lines.extend(["", "## Structurally validated hooks", ""])
    lines.extend(f"- `{name}`" for name in sorted(set(validated)))
    lines.extend(["", "## Deferred/live-only hooks", ""])
    lines.extend(f"- `{name}`" for name in sorted(set(deferred)))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
