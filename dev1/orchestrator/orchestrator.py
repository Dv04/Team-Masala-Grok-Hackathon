#!/usr/bin/env python3
"""Team Masala Chief of Staff (dept `orchestrator`).

Takes a founder request, decomposes it with Grok structured output (or a labeled
mock plan when XAI_API_KEY is absent), routes tasks through the shared
department service, and tracks them. The Pulse Studio chain is self-driving
once research emits `trend_spotted` or `/api/pulse/start` accepts the kickoff:
this process only starts that chain and reports status. It does not re-route
design, QA, listing, marketing, ops, or finance steps the chain already owns.

Stdlib only. Never logs secrets or PII.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

DEPTS = (
    "orchestrator", "research", "marketing", "sales", "support", "engineering",
    "finance", "legal", "integrations", "hr", "design", "ops", "qa",
)
# Steps the Pulse chain runs by itself after trend_spotted / /api/pulse/start.
PULSE_CHAIN_DEPTS = frozenset({
    "design", "qa", "legal", "engineering", "sales", "marketing", "ops", "finance",
})
STATUSES = ("queued", "running", "needs_approval", "approved", "rejected", "done", "failed")
XAI_BASE = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
SERVICE = os.environ.get("DEPT_SERVICE_URL", "http://127.0.0.1:8810").rstrip("/")
ORCH_PORT = int(os.environ.get("ORCH_PORT", "8820"))
ACTOR = "dev1-orchestrator"
SECRET_RE = re.compile(
    r"(xai-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,})"
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")

PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": ["pulse", "general"]},
        "summary": {"type": "string"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "dept": {"type": "string", "enum": list(DEPTS)},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "needs_approval": {"type": "boolean"},
                },
                "required": ["dept", "title", "detail", "needs_approval"],
            },
        },
    },
    "required": ["intent", "summary", "tasks"],
}

_KEYWORD_DEPTS = (
    ("research", ("research", "trend", "competitor", "market", "strategy")),
    ("marketing", ("marketing", "campaign", "caption", "social post", "content")),
    ("sales", ("sales", "lead", "pipeline", "prospect")),
    ("support", ("support", "ticket", "customer")),
    ("engineering", ("engineering", "bug", "implement", "build the", "listing")),
    ("finance", ("finance", "margin", "invoice", "revenue")),
    ("legal", ("legal", "contract", "compliance", "terms of")),
    ("integrations", ("integration", "webhook", "connector")),
    ("hr", ("hire", "hiring", "candidate", "recruit")),
    ("design", ("design", "logo", "brand kit", "visual")),
    ("ops", ("ops", "fulfill", "anomaly", "order")),
    ("qa", ("qa", "quality check", "approval gate")),
)
_APPROVAL_WORDS = ("refund", "payment", "price", "pricing", "contract", "discount", "wire", "legal")


def mode_from_env() -> str:
    return "live" if os.environ.get("XAI_API_KEY") else "mock"


def scrub(text: str, limit: int = 500) -> str:
    """Drop secrets and contact PII before anything is logged or posted."""
    s = SECRET_RE.sub("[redacted]", str(text or ""))
    s = EMAIL_RE.sub("[redacted-email]", s)
    s = PHONE_RE.sub("[redacted-phone]", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def new_id(prefix: str = "orch") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def is_pulse_text(text: str) -> bool:
    t = (text or "").lower()
    keys = ("pulse studio", "pulse", "what's trending", "whats trending", "what is trending", "trending today")
    return any(k in t for k in keys)


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 10,
               headers: dict | None = None) -> tuple[int, Any]:
    """JSON HTTP. Uses httpx when it is installed; otherwise stdlib urllib.
    Callers that talk to a model pass only XAI_BASE (https://api.x.ai/v1).
    """
    hdrs = {"accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        import httpx
    except ImportError:
        httpx = None
    if httpx is not None:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, json=body, headers=hdrs)
        raw = resp.text or ""
        try:
            parsed = resp.json() if raw.strip() else {}
        except Exception:
            parsed = {"error": raw[:300]}
        return resp.status_code, parsed
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={**hdrs, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            parsed = json.loads(raw) if raw else {"error": str(e.reason)}
        except json.JSONDecodeError:
            parsed = {"error": raw[:300] or str(e.reason)}
        return e.code, parsed


class ServiceError(RuntimeError):
    pass


class DeptClient:
    """Minimal client for the shared department service. No dependency on dev1/common."""

    def __init__(self, base: str = SERVICE, transport: Callable | None = None):
        self.base = base.rstrip("/")
        self._transport = transport  # (method, url, body) -> (status, parsed)

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 10) -> tuple[int, Any]:
        url = path if path.startswith("http") else f"{self.base}{path}"
        if self._transport:
            return self._transport(method, url, body)
        return _http_json(method, url, body, timeout=timeout)

    def health(self) -> dict:
        code, data = self._call("GET", "/health")
        if code != 200:
            raise ServiceError(f"dept service unhealthy: HTTP {code}")
        return data if isinstance(data, dict) else {"ok": False}

    def post_event(self, task_id: str, status: str, summary: str, mode: str,
                   output: dict | None = None, parent_id: str | None = None,
                   needs_approval: bool | None = None) -> dict:
        if status not in STATUSES:
            raise ValueError(f"bad status {status}")
        ev = {
            "dept": "orchestrator",
            "task_id": task_id,
            "actor": ACTOR,
            "status": status,
            "summary": scrub(summary, 200),
            "mode": mode if mode in ("live", "mock") else "mock",
            "output": _safe_output(output or {}),
        }
        if parent_id:
            ev["parent_id"] = parent_id
        if needs_approval is not None:
            ev["needs_approval"] = bool(needs_approval)
        elif status == "needs_approval":
            ev["needs_approval"] = True
        code, data = self._call("POST", "/api/events", ev)
        if code != 200 or not (isinstance(data, dict) and data.get("ok")):
            err = data.get("error") if isinstance(data, dict) else data
            raise ServiceError(f"POST /api/events failed ({code}): {err}")
        return data.get("event") or ev

    def create_task(self, dept: str, title: str, detail: str, parent_id: str,
                    meta: dict | None = None) -> dict:
        dept = (dept or "").strip().lower()
        if dept not in DEPTS or dept == "orchestrator":
            raise ValueError(f"cannot route to dept {dept!r}")
        body = {
            "for_dept": dept,
            "title": scrub(title, 180),
            "detail": scrub(detail, 800),
            "parent_id": parent_id,
            "actor": ACTOR,
            "source": "orchestrator",
            "meta": _safe_output(meta or {}),
        }
        code, data = self._call("POST", "/api/tasks", body)
        if code != 200 or not (isinstance(data, dict) and data.get("ok")):
            err = data.get("error") if isinstance(data, dict) else data
            raise ServiceError(f"POST /api/tasks failed ({code}): {err}")
        return data.get("task") or {}

    def pulse_start(self, request_text: str, parent_id: str) -> tuple[str, Any]:
        """Ask the department service to start the Pulse chain. 404/405 => unavailable.

        Body matches departments POST /api/pulse/start: no trend means the service
        emits research trend_spotted from its backup list (source backup). We do
        not invent an X trend here.
        """
        body = {
            "why": scrub(request_text, 200) or "founder asked for what is trending today",
            "source": "backup",
            "parent_id": parent_id,
            "actor": ACTOR,
        }
        try:
            code, data = self._call("POST", "/api/pulse/start", body, timeout=5)
        except Exception as e:  # network: service up for other routes, this one missing
            return "error", {"error": type(e).__name__}
        if code in (404, 405, 501):
            return "unavailable", data if isinstance(data, dict) else {"status": code}
        if code >= 400:
            return "error", data if isinstance(data, dict) else {"status": code}
        return "ok", data

    def events(self, task_id: str | None = None, dept: str | None = None, limit: int = 200) -> list[dict]:
        q = [f"limit={int(limit)}"]
        if task_id:
            q.append("task_id=" + urllib.request.quote(task_id))
        if dept:
            q.append("dept=" + urllib.request.quote(dept))
        code, data = self._call("GET", "/api/events?" + "&".join(q))
        if code != 200 or not isinstance(data, dict):
            raise ServiceError(f"GET /api/events failed ({code})")
        evs = data.get("events") or []
        return [e for e in evs if isinstance(e, dict)]


def _safe_output(obj: Any, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = scrub(str(k), 60)
            if key in ("kind",) and str(v) == "chain_stalled":
                # Never emit a duplicate chain_stalled; integrations owns that signal.
                continue
            out[key] = _safe_output(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_safe_output(v, depth + 1) for v in obj[:20]]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return scrub(str(obj), 400)


def heuristic_plan(text: str, max_tasks: int) -> dict:
    """Labeled mock decomposition. Used when no key is set, or Grok fails."""
    text_l = (text or "").lower()
    if is_pulse_text(text):
        return {
            "intent": "pulse",
            "summary": "Pulse Studio kickoff: route to research only; the chain drives itself after trend_spotted.",
            "tasks": [{
                "dept": "research",
                "title": "Spot today's X trend for Pulse Studio",
                "detail": "Founder asked to launch from today's trend. Emit trend_spotted {trend, why, source:'x'}. "
                          "Downstream design, QA, listing, marketing, order, and finance run without another orchestrator route.",
                "needs_approval": False,
            }],
            "planner": "mock",
        }
    tasks = []
    for dept, words in _KEYWORD_DEPTS:
        if any(w in text_l for w in words):
            approval = dept in ("legal", "finance") or any(w in text_l for w in _APPROVAL_WORDS)
            tasks.append({
                "dept": dept,
                "title": scrub(f"{dept}: {text}", 120),
                "detail": scrub(text, 400),
                "needs_approval": approval and dept in ("legal", "finance", "support", "sales"),
            })
    if not tasks:
        tasks.append({
            "dept": "research",
            "title": "Clarify and research the founder request",
            "detail": scrub(text, 400) or "Empty founder request",
            "needs_approval": False,
        })
    # Approval-worthy wording adds a legal heads-up without dropping the other work.
    if any(w in text_l for w in _APPROVAL_WORDS) and not any(t["needs_approval"] for t in tasks):
        if len(tasks) < max_tasks:
            tasks.append({
                "dept": "legal",
                "title": "Review founder request for approval",
                "detail": "Wording touches payment, pricing, refund, or contract. Surface for optional founder approval.",
                "needs_approval": True,
            })
    return {
        "intent": "general",
        "summary": scrub(text, 180) or "Founder request",
        "tasks": tasks[:max_tasks],
        "planner": "mock",
    }


def grok_plan(text: str, max_tasks: int, max_calls: int, calls: list[int]) -> dict | None:
    """One structured chat-completions call. Returns None when there is no key.
    Reasoning models reject stop / presence_penalty / frequency_penalty, so those are omitted.
    """
    key = os.environ.get("XAI_API_KEY")
    if not key or calls[0] >= max_calls:
        return None
    model = os.environ.get("GROK_TEXT_MODEL") or os.environ.get("GROK_FAST_MODEL") or "grok-4"
    prompt = (
        "You are the Chief of Staff for an autonomous company. Decompose the founder request into tasks. "
        f"Use only these dept strings: {', '.join(DEPTS)}. "
        "If the request is to launch Pulse Studio or 'something on what is trending', set intent to pulse and "
        "return ONLY one research task. Do not list design, qa, legal, engineering, sales, marketing, ops, or finance "
        "for a pulse request: that chain runs itself after research emits trend_spotted. "
        "For any other request, set intent to general. Mark needs_approval true for legal, payment, pricing, refund, "
        f"or contract work. Return at most {max_tasks} tasks. No names, emails, phone numbers, or secrets. "
        "The research task for pulse must say to emit trend_spotted with trend, why, and source x."
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": scrub(text, 1500)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "orchestrator_plan", "strict": True, "schema": PLAN_SCHEMA},
        },
    }
    calls[0] += 1
    # Hard-wired to xAI. No other provider, no penalty/stop params (reasoning models reject them).
    try:
        code, data = _http_json(
            "POST", f"{XAI_BASE}/chat/completions", body, timeout=30,
            headers={"Authorization": "Bearer " + key},
        )
    except Exception:
        return None
    if code != 200 or not isinstance(data, dict):
        return None
    try:
        content = data["choices"][0]["message"]["content"]
        plan = json.loads(content)
    except Exception:
        return None
    if not isinstance(plan, dict) or "tasks" not in plan:
        return None
    plan["planner"] = "grok"
    plan["model"] = model
    return plan


def normalize_plan(plan: dict, max_tasks: int, source_text: str) -> dict:
    planner = plan.get("planner") or "mock"
    if plan.get("intent") == "pulse":
        intent = "pulse"
    elif plan.get("intent") == "general":
        intent = "general"
    elif planner == "mock" and is_pulse_text(source_text):
        intent = "pulse"
    else:
        intent = "pulse" if is_pulse_text(source_text) else "general"
    tasks = []
    for raw in plan.get("tasks") or []:
        if not isinstance(raw, dict):
            continue
        dept = str(raw.get("dept") or "").strip().lower()
        if dept not in DEPTS or dept == "orchestrator":
            continue
        if intent == "pulse" and dept in PULSE_CHAIN_DEPTS:
            continue  # chain owns these
        tasks.append({
            "dept": dept,
            "title": scrub(raw.get("title") or f"{dept} task", 160),
            "detail": scrub(raw.get("detail") or source_text, 800),
            "needs_approval": bool(raw.get("needs_approval")),
        })
        if len(tasks) >= max_tasks:
            break
    if intent == "pulse":
        tasks = [t for t in tasks if t["dept"] == "research"][:1] or heuristic_plan(source_text, 1)["tasks"]
    if not tasks:
        tasks = heuristic_plan(source_text if intent != "pulse" else "research the founder request", max_tasks)["tasks"]
        if intent != "pulse":
            intent = "general"
    return {
        "intent": intent,
        "summary": scrub(plan.get("summary") or source_text, 180),
        "tasks": tasks[:max_tasks],
        "planner": plan.get("planner") or "mock",
        "model": plan.get("model"),
    }


class Orchestrator:
    def __init__(self, client: DeptClient | None = None, max_tasks: int = 6, max_grok_calls: int = 3,
                 planner: Callable[[str, int], dict] | None = None):
        self.client = client or DeptClient()
        self.max_tasks = max(1, int(max_tasks))
        self.max_grok_calls = max(0, int(max_grok_calls))
        self._planner = planner
        self._grok_calls = [0]
        self._lock = threading.Lock()
        self.requests: dict[str, dict] = {}

    def plan(self, text: str) -> dict:
        if self._planner:
            raw = self._planner(text, self.max_tasks)
            raw.setdefault("planner", "mock")
            return normalize_plan(raw, self.max_tasks, text)
        live = grok_plan(text, self.max_tasks, self.max_grok_calls, self._grok_calls)
        if live:
            return normalize_plan(live, self.max_tasks, text)
        return normalize_plan(heuristic_plan(text, self.max_tasks), self.max_tasks, text)

    def submit(self, text: str, intent: str | None = None) -> dict:
        text = scrub(text, 1500)
        if not text:
            raise ValueError("founder request is empty")
        self.client.health()
        plan = self.plan(text)
        if intent == "pulse":
            plan = normalize_plan({"intent": "pulse", "summary": plan.get("summary"), "tasks": plan.get("tasks"),
                                   "planner": plan.get("planner"), "model": plan.get("model")}, self.max_tasks, text)
        mode = "live" if plan.get("planner") == "grok" else "mock"
        req_id = new_id("req")
        record = {
            "request_id": req_id,
            "text": text,
            "intent": plan["intent"],
            "summary": plan["summary"],
            "mode": mode,
            "planner": plan.get("planner"),
            "model": plan.get("model"),
            "tasks": [],
            "grok_calls": self._grok_calls[0],
            "pulse_start": None,
            "stalls_noted": [],
        }
        self.client.post_event(req_id, "queued", f"Founder request accepted: {plan['summary']}", mode,
                               {"kind": "founder_request", "intent": plan["intent"], "planner": plan.get("planner")})
        self.client.post_event(req_id, "running", f"Routing {len(plan['tasks'])} task(s), intent={plan['intent']}", mode,
                               {"kind": "routing", "intent": plan["intent"], "task_count": len(plan["tasks"])})
        if plan["intent"] == "pulse":
            state, info = self.client.pulse_start(text, req_id)
            record["pulse_start"] = state
            if state == "ok" and isinstance(info, dict):
                record["trend_task"] = info.get("trend_task")
            self.client.post_event(
                req_id, "running",
                f"Pulse kickoff via /api/pulse/start: {state}. Chain drives itself after trend_spotted.",
                mode,
                {"kind": "pulse_kickoff", "pulse_start": state,
                 "note": "orchestrator does not route design/qa/listing/marketing/ops/finance"},
            )
            if state == "error":
                record["pulse_start_error"] = scrub(json.dumps(info), 200)
        for task in plan["tasks"]:
            self._route(record, task, mode, retry_of=None)
        self._finish_request_event(record, mode)
        with self._lock:
            self.requests[req_id] = record
        return self.status(req_id)

    def pulse(self, text: str | None = None) -> dict:
        text = text or "Launch something on what's trending today"
        return self.submit(text, intent="pulse")

    def _route(self, record: dict, task: dict, mode: str, retry_of: str | None) -> dict | None:
        if len(record["tasks"]) >= self.max_tasks and not retry_of:
            return None
        # A retry counts against the cap too, but one retry of an existing task is allowed
        # even when the original fill used the whole budget (the retry replaces, it doesn't stack).
        if record["intent"] == "pulse" and task["dept"] in PULSE_CHAIN_DEPTS:
            return None
        meta = {"kind": "pulse_kickoff" if record["intent"] == "pulse" else "routed_task",
                "needs_approval": task.get("needs_approval", False)}
        if record["intent"] == "pulse":
            meta["expect"] = "trend_spotted"
            meta["product"] = "Pulse Studio"
        if retry_of:
            meta["retry_of"] = retry_of
            meta["attempt"] = 2
        created = self.client.create_task(task["dept"], task["title"], task["detail"], record["request_id"], meta)
        child_id = created.get("task_id") or new_id(task["dept"][:8])
        entry = {
            "task_id": child_id,
            "dept": task["dept"],
            "title": task["title"],
            "needs_approval": bool(task.get("needs_approval")),
            "retries": 1 if retry_of else 0,
            "retry_of": retry_of,
            "status": "queued",
        }
        record["tasks"].append(entry)
        if task.get("needs_approval"):
            self.client.post_event(
                record["request_id"], "needs_approval",
                f"Needs approval (optional, other work continues): {task['dept']} — {task['title']}",
                mode,
                {"kind": "needs_approval", "for_dept": task["dept"], "task_id": child_id},
                needs_approval=True,
            )
        return entry

    def _finish_request_event(self, record: dict, mode: str) -> None:
        approvals = [t for t in record["tasks"] if t.get("needs_approval")]
        status = "needs_approval" if approvals and not any(not t.get("needs_approval") for t in record["tasks"]) else "running"
        # Mixed: surface approval but keep the request running so the rest is not blocked.
        if approvals and status != "needs_approval":
            status = "running"
        summary = f"Routed {len(record['tasks'])} task(s)"
        if record["intent"] == "pulse":
            summary = f"Pulse routed to research ({record.get('pulse_start')}); tracking chain"
        if approvals:
            summary += f"; {len(approvals)} needs_approval (not blocking)"
        self.client.post_event(record["request_id"], status, summary, mode, {
            "kind": "routed",
            "intent": record["intent"],
            "tasks": [{"task_id": t["task_id"], "dept": t["dept"]} for t in record["tasks"]],
            "pulse_start": record.get("pulse_start"),
        }, needs_approval=bool(approvals) and status == "needs_approval")

    def reconcile(self, request_id: str) -> dict:
        """Read /api/events, note stalls, surface approvals, retry a failed routed task once."""
        record = self.requests.get(request_id)
        if not record:
            raise KeyError(request_id)
        evs = self.client.events(limit=400)
        mode = record["mode"]
        by_task: dict[str, dict] = {}
        for ev in evs:
            tid = ev.get("task_id")
            if tid:
                by_task[tid] = ev  # log is chronological; last wins
        # Child status from the event log.
        for entry in record["tasks"]:
            ev = by_task.get(entry["task_id"])
            if ev and ev.get("status") in STATUSES:
                entry["status"] = ev["status"]
        # needs_approval anywhere on our children, without stopping the others.
        for ev in evs:
            if ev.get("status") != "needs_approval":
                continue
            if ev.get("task_id") == request_id or ev.get("parent_id") == request_id or ev.get("task_id") in by_task:
                if ev.get("parent_id") == request_id or ev.get("task_id") in {t["task_id"] for t in record["tasks"]}:
                    entry_ids = {t["task_id"] for t in record["tasks"]}
                    if ev.get("task_id") in entry_ids:
                        for t in record["tasks"]:
                            if t["task_id"] == ev["task_id"]:
                                t["needs_approval"] = True
                                t["status"] = "needs_approval"
        # Stalls: integrations owns chain_stalled. Observe once, do not re-emit that kind.
        for ev in evs:
            if not _is_stall(ev):
                continue
            sid = ev.get("task_id") or ""
            if sid in record["stalls_noted"]:
                continue
            # Only stalls tied to this request's chain (parent or same tree) or a global integrations stall
            # during this request. We note every integrations chain_stalled seen while reconciling this request
            # once, which is the coordination point dev3 asked for.
            if ev.get("dept") != "integrations" and ev.get("parent_id") not in (request_id, None) and ev.get("parent_id") != request_id:
                related = ev.get("parent_id") == request_id or ev.get("task_id") in {t["task_id"] for t in record["tasks"]}
                if not related:
                    continue
            record["stalls_noted"].append(sid)
            self.client.post_event(
                request_id, "running",
                f"Observed chain_stalled on {ev.get('dept')} task {sid}; not re-raising",
                mode,
                {"kind": "stall_noted", "source_task_id": sid, "source_dept": ev.get("dept"),
                 "source_summary": scrub(ev.get("summary") or "", 160)},
            )
        # Retry / reassign once. Never retry depts the pulse chain already drives.
        for entry in list(record["tasks"]):
            if entry["status"] != "failed" or entry["retries"] >= 1:
                continue
            if record["intent"] == "pulse" and entry["dept"] != "research":
                continue
            self.client.post_event(
                request_id, "running",
                f"Retry once: reassign {entry['dept']} task {entry['task_id']}",
                mode,
                {"kind": "retry", "retry_of": entry["task_id"], "dept": entry["dept"]},
            )
            self._route(record, {
                "dept": entry["dept"],
                "title": entry["title"],
                "detail": f"Retry of {entry['task_id']}. Original failed once.",
                "needs_approval": entry.get("needs_approval", False),
            }, mode, retry_of=entry["task_id"])
            entry["retries"] = 1
        return self.status(request_id)

    def status(self, request_id: str, refresh: bool = False) -> dict:
        if refresh:
            return self.reconcile(request_id)
        record = self.requests.get(request_id)
        if not record:
            raise KeyError(request_id)
        evs: list[dict] = []
        try:
            evs = self.client.events(limit=400)
        except ServiceError:
            evs = []
        child_ids = {t["task_id"] for t in record["tasks"]}
        trend_task = record.get("trend_task")
        if trend_task:
            child_ids.add(trend_task)
        latest: dict[str, dict] = {}
        steps_seen = []
        trend = bool(trend_task)
        listing = False
        approvals = []
        chain_ids = {request_id, trend_task} - {None}
        for ev in evs:
            tid = ev.get("task_id")
            if tid in child_ids or tid == request_id:
                latest[tid] = ev
            out = ev.get("output") or {}
            if not isinstance(out, dict):
                out = {}
            kind = out.get("kind")
            parent = ev.get("parent_id")
            in_chain = parent in chain_ids or tid in child_ids or tid == request_id
            if in_chain and ev.get("dept") and ev["dept"] not in steps_seen and ev["dept"] != "orchestrator":
                steps_seen.append(ev["dept"])
            if kind == "trend_spotted" and (in_chain or tid == trend_task):
                trend = True
            if kind == "listing_live" and (in_chain or parent == trend_task or tid == trend_task):
                listing = True
            if ev.get("status") == "needs_approval" and (tid in child_ids or parent in chain_ids):
                approvals.append({"task_id": tid, "dept": ev.get("dept"), "summary": scrub(ev.get("summary") or "", 160)})
        tasks_out = []
        for t in record["tasks"]:
            ev = latest.get(t["task_id"])
            status = ev.get("status") if ev else t.get("status", "queued")
            tasks_out.append({**t, "status": status})
        stalls = []
        for ev in evs:
            if _is_stall(ev) and (ev.get("task_id") in record["stalls_noted"] or ev.get("parent_id") == request_id):
                stalls.append({"task_id": ev.get("task_id"), "dept": ev.get("dept"),
                               "summary": scrub(ev.get("summary") or "", 160)})
        terminal = [t["status"] for t in tasks_out]
        if tasks_out and all(s in ("done", "failed", "rejected") for s in terminal) and not approvals:
            req_status = "failed" if any(s == "failed" for s in terminal) else "done"
        elif approvals:
            req_status = "needs_approval" if all(t.get("needs_approval") or t["status"] == "needs_approval" for t in tasks_out) else "running"
        else:
            req_status = latest.get(request_id, {}).get("status", "running")
        return {
            "request_id": request_id,
            "intent": record["intent"],
            "mode": record["mode"],
            "planner": record.get("planner"),
            "summary": record["summary"],
            "status": req_status,
            "tasks": tasks_out,
            "needs_approval": approvals,
            "stalls": stalls,
            "pulse": {
                "pulse_start": record.get("pulse_start"),
                "trend_task": record.get("trend_task"),
                "trend_spotted": trend,
                "listing_live": listing,
                "steps_seen": steps_seen,
            },
            "budget": {
                "max_tasks": self.max_tasks,
                "tasks_routed": len(record["tasks"]),
                "grok_calls": record.get("grok_calls", 0),
                "max_grok_calls": self.max_grok_calls,
            },
        }

    def close_if_settled(self, request_id: str) -> dict:
        """Post done/failed on the orchestrator request when every routed task is terminal.
        needs_approval does not count as settled, and does not block siblings already done.
        """
        st = self.reconcile(request_id)
        record = self.requests[request_id]
        if record.get("closed"):
            return st
        tasks = st["tasks"]
        if not tasks:
            return st
        if any(t["status"] in ("queued", "running", "needs_approval") for t in tasks):
            return st
        mode = record["mode"]
        if any(t["status"] == "failed" for t in tasks):
            self.client.post_event(request_id, "failed", "One or more routed tasks failed after a single retry", mode,
                                   {"kind": "request_closed", "tasks": tasks})
        else:
            self.client.post_event(request_id, "done", f"Founder request complete ({record['intent']})", mode,
                                   {"kind": "request_closed", "intent": record["intent"]})
        record["closed"] = True
        return self.status(request_id)


def _is_stall(ev: dict) -> bool:
    out = ev.get("output") or {}
    if isinstance(out, dict) and out.get("kind") == "chain_stalled":
        return True
    summary = (ev.get("summary") or "").lower()
    return ev.get("dept") == "integrations" and "chain_stalled" in summary


# ---------- HTTP ----------
_ORCH: Orchestrator | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "masala-orchestrator/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> dict:
        n = int(self.headers.get("content-length") or 0)
        if n <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode() or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            mode = mode_from_env()
            svc = "unknown"
            try:
                h = _ORCH.client.health() if _ORCH else {}
                svc = "up" if h.get("ok") else "down"
            except Exception:
                svc = "down"
            self._send(200, {"ok": True, "dept": "orchestrator", "mode": mode, "port": ORCH_PORT,
                             "dept_service": svc, "actor": ACTOR})
            return
        if path == "/requests":
            ids = list((_ORCH.requests if _ORCH else {}).keys())
            self._send(200, {"requests": ids})
            return
        if path.startswith("/status/"):
            rid = path[len("/status/"):]
            try:
                self._send(200, _ORCH.status(rid, refresh="refresh" in self.path))
            except KeyError:
                self._send(404, {"ok": False, "error": "unknown request"})
            except Exception as e:
                self._send(502, {"ok": False, "error": scrub(str(e), 200)})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._read()
        try:
            if path == "/request":
                self._send(200, _ORCH.submit(str(body.get("text") or "")))
                return
            if path == "/pulse":
                self._send(200, _ORCH.pulse(str(body.get("text") or "") or None))
                return
            if path.startswith("/reconcile/"):
                self._send(200, _ORCH.reconcile(path[len("/reconcile/"):]))
                return
        except ValueError as e:
            self._send(400, {"ok": False, "error": scrub(str(e), 200)})
            return
        except (ServiceError, urllib.error.URLError, TimeoutError, OSError) as e:
            self._send(502, {"ok": False, "error": scrub(str(e), 200)})
            return
        self._send(404, {"ok": False, "error": "not found"})


def serve(port: int = ORCH_PORT) -> None:
    global _ORCH
    _ORCH = Orchestrator()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"orchestrator listening on http://127.0.0.1:{port} mode={mode_from_env()} service={SERVICE}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Team Masala orchestrator / chief of staff")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("request", help="decompose a founder request and route it")
    r.add_argument("text")
    r.add_argument("--max-tasks", type=int, default=6)
    u = sub.add_parser("pulse", help="kick off the Pulse Studio chain via research + /api/pulse/start")
    u.add_argument("text", nargs="?", default="Launch something on what's trending today")
    s = sub.add_parser("status", help="re-read /api/events for a request and retry failures once")
    s.add_argument("request_id")
    sv = sub.add_parser("serve", help="HTTP on 127.0.0.1 (default port 8820)")
    sv.add_argument("--port", type=int, default=ORCH_PORT)
    args = p.parse_args(argv)
    if args.cmd == "serve":
        serve(args.port)
        return 0
    orch = Orchestrator(max_tasks=getattr(args, "max_tasks", 6))
    try:
        if args.cmd == "request":
            out = orch.submit(args.text)
        elif args.cmd == "pulse":
            out = orch.pulse(args.text)
        else:
            # status without in-memory record: report events only
            try:
                out = orch.status(args.request_id, refresh=True)
            except KeyError:
                evs = orch.client.events(task_id=args.request_id, limit=50)
                out = {"request_id": args.request_id, "events": evs, "note": "no in-memory request; showing log"}
    except (ServiceError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(json.dumps({"ok": False, "error": scrub(str(e), 300)}), flush=True)
        return 1
    print(json.dumps(out, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
