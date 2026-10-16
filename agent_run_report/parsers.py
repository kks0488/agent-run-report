"""Streaming, best-effort readers. Raw messages never leave this module."""

import json
import math
import posixpath
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

UTC = timezone.utc
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")


def mapping(value):
    return value if isinstance(value, dict) else {}


def items(value):
    return value if isinstance(value, list) else []


def number(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value)) if math.isfinite(value) else 0
    return 0


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def records(path):
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


@dataclass
class Session:
    source: str
    session_id: str
    cwd: str = ""
    title: Optional[str] = None
    events: List[datetime] = field(default_factory=list)
    user_prompts: int = 0
    assistant_turns: int = 0
    models: Set[str] = field(default_factory=set)
    tools: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)
    tokens: Counter = field(default_factory=Counter)
    daily_tokens: Dict[str, Counter] = field(default_factory=dict)
    files: Set[str] = field(default_factory=set)
    subagent_activity: int = 0

    @property
    def start(self):
        return min(self.events) if self.events else None

    @property
    def end(self):
        return max(self.events) if self.events else None

    @property
    def active_seconds(self):
        ordered = sorted(set(self.events))
        return sum(min(300, (b - a).total_seconds()) for a, b in zip(ordered, ordered[1:]))

    def add_tokens(self, usage, when):
        self.tokens.update(usage)
        self.daily_tokens.setdefault(when.date().isoformat(), Counter()).update(usage)


def in_range(when, since, until):
    return when is not None and (since is None or when >= since) and (until is None or when < until)


def normalize_usage(usage, codex=False):
    usage = mapping(usage)
    cached = number(usage.get("cached_input_tokens" if codex else "cache_read_input_tokens"))
    written = number(usage.get("cache_write_input_tokens" if codex else "cache_creation_input_tokens"))
    # Codex includes cached tokens in input_tokens; Claude reports them separately.
    return Counter(input=max(0, number(usage.get("input_tokens")) - (cached if codex else 0)),
                   output=number(usage.get("output_tokens")), cache_read=cached, cache_write=written)


def touched_files(name, arguments, cwd):
    short = name.rsplit(".", 1)[-1].lower()
    data = mapping(arguments)
    paths = []
    if short in {"edit", "write", "multiedit", "notebookedit"}:
        paths = [data.get("file_path"), data.get("notebook_path"), data.get("path")]
        paths += [mapping(edit).get("file_path") for edit in items(data.get("edits"))]
    elif short == "apply_patch":
        patch = arguments if isinstance(arguments, str) else data.get("patch", data.get("input", ""))
        if isinstance(patch, str):
            paths = re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", patch, re.M)
    return {posixpath.normpath(p if p.startswith("/") else posixpath.join(cwd, p))
            for p in paths if isinstance(p, str) and p.strip()}


def tool_arguments(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, RecursionError):
            return value
    return value


def failed_output(value):
    """Recognize structured errors and shell exit markers, never arbitrary 'error' prose."""
    if isinstance(value, dict):
        if value.get("is_error") is True or value.get("status") in ("failed", "error"):
            return True
        for key in ("exit_code", "exitCode", "returncode"):
            code = value.get(key)
            if isinstance(code, (int, float)) and code != 0:
                return True
        return any(failed_output(value.get(k)) for k in ("output", "content", "text", "result"))
    if isinstance(value, list):
        return any(failed_output(part) for part in value)
    if isinstance(value, str):
        if re.search(r'(?:exited with (?:code|status)|exit code|["\']?(?:exit_code|returncode)["\']?\s*:)\s*[1-9]\d*', value, re.I):
            return True
        try:
            parsed = json.loads(value)
        except (ValueError, RecursionError):
            return False
        return failed_output(parsed) if isinstance(parsed, (dict, list)) else False
    return False


def parse_claude(path, since=None, until=None, include_titles=False):
    sessions = {}
    calls, failed, seen_blocks, usage_seen = {}, set(), set(), {}
    for row in records(path):
        sid = row.get("sessionId")
        if not isinstance(sid, str) or not sid:
            continue
        session = sessions.setdefault(sid, Session("claude", sid))
        if isinstance(row.get("cwd"), str):
            session.cwd = row["cwd"]
        kind = row.get("type")
        if kind == "ai-title" and include_titles and isinstance(row.get("aiTitle"), str):
            session.title = row["aiTitle"]
        if kind not in ("user", "assistant", "system"):
            continue
        when = timestamp(row.get("timestamp"))
        if not in_range(when, since, until):
            continue
        session.events.append(when)
        message = mapping(row.get("message"))
        content = items(message.get("content"))
        if row.get("isSidechain") is True:
            session.subagent_activity += 1
        if kind == "user":
            # Tool results use the user role, but are not human prompts.
            if not content or any(mapping(b).get("type") in ("text", "input_text") for b in content):
                if not row.get("isMeta"):
                    session.user_prompts += 1
            for block in content:
                block = mapping(block)
                bid = block.get("tool_use_id")
                call = (sid, bid if isinstance(bid, str) else len(session.events))
                if block.get("type") == "tool_result" and failed_output(block) and call not in failed:
                    session.failures[calls.get(call, "(unattributed)")] += 1
                    failed.add(call)
        elif kind == "assistant":
            mid = message.get("id") if isinstance(message.get("id"), str) else None
            key = (sid, mid or len(session.events))
            if key not in usage_seen:
                session.assistant_turns += 1
            model = message.get("model")
            if isinstance(model, str):
                session.models.add(model)
            current = normalize_usage(message.get("usage"))
            previous = usage_seen.get(key, Counter())
            delta = Counter({k: max(0, current[k] - previous[k]) for k in TOKEN_KEYS})
            session.add_tokens(delta, when)
            usage_seen[key] = previous | current
            for index, block in enumerate(content):
                block = mapping(block)
                if block.get("type") != "tool_use" or not isinstance(block.get("name"), str):
                    continue
                bid = block.get("id")
                block_key = (sid, bid if isinstance(bid, str) else (key, index))
                if block_key in seen_blocks:
                    continue
                seen_blocks.add(block_key)
                name = block["name"]
                session.tools[name] += 1
                if isinstance(bid, str):
                    calls[(sid, bid)] = name
                session.files.update(touched_files(name, block.get("input"), session.cwd))
    return [s for s in sessions.values() if s.events]


def parse_codex(path, since=None, until=None, include_titles=False):
    session = Session("codex", Path(path).stem.removeprefix("rollout-"))
    calls, failed, seen_calls, seen_messages = {}, set(), set(), set()
    cumulative = Counter()
    subagent = False
    # New logs contain both token_usage_record and token_count. Their snapshots
    # can lag each other, so keep a high-water mark rather than treating a lower
    # snapshot as a reset (which would add the entire session total again).
    for row in records(path):
        payload = mapping(row.get("payload"))
        kind, typ = row.get("type"), payload.get("type")
        when = timestamp(row.get("timestamp")) or timestamp(payload.get("timestamp"))
        if kind == "session_meta":
            sid = payload.get("id", payload.get("session_id"))
            if isinstance(sid, str):
                session.session_id = sid
            source = payload.get("source", payload.get("thread_source"))
            subagent = isinstance(source, dict) and "subagent" in source
        if kind in ("session_meta", "turn_context"):
            if isinstance(payload.get("cwd"), str):
                session.cwd = payload["cwd"]
            if isinstance(payload.get("model"), str):
                session.models.add(payload["model"])
        total_usage, last_usage = None, None
        if kind == "event_msg" and typ == "token_count":
            info = mapping(payload.get("info"))
            total_usage, last_usage = info.get("total_token_usage"), info.get("last_token_usage")
        elif kind == "token_usage_record":
            total_usage, last_usage = payload.get("thread_token_usage"), payload.get("usage")
        delta = Counter()
        if isinstance(total_usage, dict):
            current = normalize_usage(total_usage, codex=True)
            delta = Counter({k: max(0, current[k] - cumulative[k]) for k in TOKEN_KEYS})
            cumulative = cumulative | current
        elif isinstance(last_usage, dict):
            delta = normalize_usage(last_usage, codex=True)
        if not in_range(when, since, until):
            continue
        if kind not in ("session_meta", "turn_context", "response_item", "event_msg", "token_usage_record"):
            continue
        session.events.append(when)
        session.add_tokens(delta, when)
        if subagent:
            session.subagent_activity += 1
        if kind == "response_item" and typ == "message":
            role = payload.get("role")
            mid = payload.get("id")
            key = mid if isinstance(mid, str) else len(session.events)
            if key not in seen_messages:
                seen_messages.add(key)
                session.user_prompts += int(role == "user")
                session.assistant_turns += int(role == "assistant")
        elif kind == "response_item" and typ in ("function_call", "custom_tool_call"):
            name = payload.get("name")
            if not isinstance(name, str):
                continue
            cid = payload.get("call_id", payload.get("id"))
            key = cid if isinstance(cid, str) else len(session.events)
            if key in seen_calls:
                continue
            seen_calls.add(key)
            calls[key] = name
            session.tools[name] += 1
            session.files.update(touched_files(name, tool_arguments(payload.get("arguments", payload.get("input"))), session.cwd))
            if name.rsplit(".", 1)[-1] in ("spawn_agent", "Task", "Agent"):
                session.subagent_activity += 1
        elif kind == "response_item" and typ in ("function_call_output", "custom_tool_call_output"):
            cid = payload.get("call_id")
            key = cid if isinstance(cid, str) else len(session.events)
            if failed_output(payload) and key not in failed:
                session.failures[calls.get(key, "(unattributed)")] += 1
                failed.add(key)
        elif kind == "event_msg" and typ in ("error", "error_event", "task_failed", "tool_error"):
            cid = payload.get("call_id")
            key = cid if isinstance(cid, str) else ("event", len(session.events))
            if key not in failed:
                session.failures[calls.get(key, "(unattributed)")] += 1
                failed.add(key)
    return [session] if session.events else []


def discover(directory, source, since=None):
    """mtime is an inexpensive prefilter; event timestamps are authoritative."""
    base = Path(directory).expanduser()
    pattern = "rollout-*.jsonl" if source == "codex" else "*.jsonl"
    if base.is_file():
        candidates = [base]
    else:
        candidates = base.rglob(pattern)
    for path in candidates:
        try:
            if path.is_file() and (since is None or path.stat().st_mtime >= since.timestamp()):
                yield path
        except OSError:
            continue


def load_sessions(directories, since=None, until=None, project=None, include_titles=False):
    merged = {}
    for source, directory in directories.items():
        parser = parse_claude if source == "claude" else parse_codex
        for path in discover(directory, source, since):
            for session in parser(path, since, until, include_titles):
                if project and project.casefold() not in session.cwd.casefold():
                    continue
                key = (source, session.session_id)
                previous = merged.get(key)
                if previous is None:
                    merged[key] = session
                    continue
                previous.events.extend(session.events)
                previous.user_prompts += session.user_prompts
                previous.assistant_turns += session.assistant_turns
                previous.subagent_activity += session.subagent_activity
                previous.models.update(session.models)
                previous.files.update(session.files)
                previous.title = previous.title or session.title
                for attr in ("tools", "failures", "tokens"):
                    getattr(previous, attr).update(getattr(session, attr))
                for day, usage in session.daily_tokens.items():
                    previous.daily_tokens.setdefault(day, Counter()).update(usage)
    return sorted(merged.values(), key=lambda s: s.start, reverse=True)
