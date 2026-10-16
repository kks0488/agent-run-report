"""Aggregation and the explicit privacy boundary shared by HTML and JSON."""

import posixpath
import re
from collections import Counter
from datetime import timedelta
from pathlib import Path

from .parsers import TOKEN_KEYS


def redact_home(path, home=None):
    home = str(home or Path.home()).rstrip("/")
    return re.sub(re.escape(home) + r"(?=/|$)", "~", path)


def project_name(cwd, full_paths=False):
    if not cwd:
        return "Unknown project"
    redacted = redact_home(cwd)
    return redacted if full_paths else posixpath.basename(redacted.rstrip("/")) or "/"


def token_dict(tokens):
    return {key: tokens[key] for key in TOKEN_KEYS}


def summarize(sessions, full_paths=False, include_titles=False):
    tools, failures, tokens = Counter(), Counter(), Counter()
    projects, days, rows = {}, {}, []

    def day_row(day):
        return days.setdefault(day, {"sessions": 0, "active_seconds": 0, "tokens": Counter()})

    for session in sessions:
        tools.update(session.tools)
        failures.update(session.failures)
        tokens.update(session.tokens)
        project = project_name(session.cwd, full_paths)
        # Group by actual cwd so identically named repositories stay separate.
        group = projects.setdefault(session.cwd, {"project": project, "sessions": 0,
                                    "active_seconds": 0, "tool_calls": 0, "failures": 0, "tokens": 0})
        group["sessions"] += 1
        group["active_seconds"] += session.active_seconds
        group["tool_calls"] += sum(session.tools.values())
        group["failures"] += sum(session.failures.values())
        group["tokens"] += sum(session.tokens.values())
        for day in {event.date().isoformat() for event in session.events}:
            day_row(day)["sessions"] += 1
        ordered = sorted(set(session.events))
        for a, b in zip(ordered, ordered[1:]):
            end = a + timedelta(seconds=min(300, (b - a).total_seconds()))
            while a < end:
                midnight = a.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                stop = min(midnight, end)
                day_row(a.date().isoformat())["active_seconds"] += (stop - a).total_seconds()
                a = stop
        for day, usage in session.daily_tokens.items():
            day_row(day)["tokens"].update(usage)
        row = {"source": session.source, "session_id": session.session_id[:12],
               "project": project, "start": session.start.isoformat(), "end": session.end.isoformat(),
               "active_seconds": session.active_seconds, "user_prompts": session.user_prompts,
               "assistant_turns": session.assistant_turns, "models": sorted(session.models),
               "tools": dict(session.tools), "failed_tool_calls": sum(session.failures.values()),
               "failures_by_tool": dict(session.failures), "tokens": token_dict(session.tokens),
               "files_touched": len(session.files), "subagent_activity": session.subagent_activity}
        if full_paths:
            row["files"] = sorted(redact_home(path) for path in session.files)
        if include_titles and session.title:
            row["title"] = redact_home(session.title)
        rows.append(row)
    # Include quiet days between observations for honest time-series spacing.
    if days:
        from datetime import date
        first, last = date.fromisoformat(min(days)), date.fromisoformat(max(days))
        while first <= last:
            day_row(first.isoformat())
            first += timedelta(days=1)
    calls, errors, total_tokens = sum(tools.values()), sum(failures.values()), sum(tokens.values())
    report = {"date_range": {"start": min((s.start for s in sessions), default=None).isoformat() if sessions else None,
                              "end": max((s.end for s in sessions), default=None).isoformat() if sessions else None},
              "sources": sorted({s.source for s in sessions}),
              "totals": {"sessions": len(sessions), "active_seconds": sum(s.active_seconds for s in sessions),
                         "tool_calls": calls, "failed_tool_calls": errors,
                         "failure_rate": errors / calls if calls else 0, "tokens": token_dict(tokens),
                         "total_tokens": total_tokens},
              "tools": dict(tools.most_common()), "failures_by_tool": dict(failures.most_common()),
              "days": [{"date": day, **values, "tokens": token_dict(values["tokens"])}
                       for day, values in sorted(days.items())],
              "projects": sorted(projects.values(), key=lambda p: p["active_seconds"], reverse=True),
              "sessions": rows,
              "privacy": {"include_titles": include_titles, "full_paths": full_paths}}
    report["insights"] = insights(report)
    return report


def insights(report):
    result = []
    if report["days"]:
        busiest = max(report["days"], key=lambda d: (d["active_seconds"], d["sessions"]))
        result.append(f"Busiest day: {busiest['date']}, with {busiest['active_seconds'] / 3600:.1f} active hours across {busiest['sessions']} sessions.")
    if report["projects"]:
        project = report["projects"][0]
        result.append(f"Most active project: {project['project']} ({project['active_seconds'] / 3600:.1f} active hours).")
    eligible = [(report["failures_by_tool"].get(name, 0) / calls, name, calls)
                for name, calls in report["tools"].items() if calls >= 10]
    if eligible:
        rate, name, calls = max(eligible)
        result.append(f"Highest observed tool failure rate (10+ calls): {name}, {rate:.1%} across {calls:,} calls.")
    total = report["totals"]["total_tokens"]
    if total:
        result.append(f"Cache reads account for {report['totals']['tokens']['cache_read'] / total:.1%} of recorded tokens.")
    return result
