"""Command-line interface; all processing stays on the local machine."""

import argparse
import json
import re
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .metrics import redact_home, summarize
from .parsers import UTC, load_sessions
from .render import render_html


def parse_since(value, now):
    if re.fullmatch(r"[1-9]\d*d", value):
        try:
            return now - timedelta(days=int(value[:-1]))
        except OverflowError:
            raise ValueError("--since day count is too large") from None
    return parse_date(value, "--since")


def parse_date(value, flag):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{flag} must be YYYY-MM-DD" + (" or a day count such as 7d" if flag == "--since" else ""))
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError(f"{flag} is not a valid calendar date") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="See what your AI coding agents actually did. Local logs → one offline HTML report.")
    parser.add_argument("--since", metavar="7d|30d|YYYY-MM-DD", help="default: last 30 days; demo: all fixture dates")
    parser.add_argument("--until", metavar="YYYY-MM-DD", help="include this entire UTC date")
    parser.add_argument("--source", choices=("all", "claude", "codex"), default="all")
    parser.add_argument("--project", metavar="SUBSTR", help="case-insensitive substring of the project path")
    parser.add_argument("--out", default="agent-run-report.html", help="HTML output path")
    parser.add_argument("--json", dest="json_out", metavar="PATH", help="also write privacy-filtered JSON")
    parser.add_argument("--claude-dir", default="~/.claude/projects", metavar="PATH")
    parser.add_argument("--codex-dir", default="~/.codex/sessions", metavar="PATH")
    parser.add_argument("--include-titles", action="store_true", help="opt in to session titles (may contain private text)")
    parser.add_argument("--full-paths", action="store_true", help="opt in to project paths and touched file paths; redact home")
    parser.add_argument("--open", action="store_true", help="open the finished local HTML report in your browser")
    parser.add_argument("--demo", action="store_true", help="use only bundled, synthetic sessions")
    parser.add_argument("--version", action="version", version=f"agent-run-report {__version__}")
    args = parser.parse_args(argv)
    now = datetime.now(UTC)
    try:
        since = parse_since(args.since, now) if args.since else (None if args.demo else now - timedelta(days=30))
        until = parse_date(args.until, "--until") + timedelta(days=1) if args.until else None
        if since and until and since >= until:
            raise ValueError("--since must be on or before --until")
    except (ValueError, OverflowError) as exc:
        parser.error(str(exc))
    output = Path(args.out).expanduser()
    json_output = Path(args.json_out).expanduser() if args.json_out else None
    if json_output and json_output.resolve() == output.resolve():
        parser.error("--out and --json must be different files")
    directories = {"claude": args.claude_dir, "codex": args.codex_dir}
    if args.demo:
        directories = {source: Path(__file__).parent / "demo" / source for source in directories}
    if args.source != "all":
        directories = {args.source: directories[args.source]}
    privacy = "Privacy: local only; prompt text and tool input/output are never included; "
    privacy += "titles " + ("included" if args.include_titles else "hidden") + "; "
    privacy += "paths included (home → ~)." if args.full_paths else "file names and full paths hidden."
    print(privacy)
    sessions = load_sessions(directories, since, until, args.project, args.include_titles)
    if not sessions:
        print("No matching sessions found. Looked in:")
        for source, directory in directories.items():
            print(f"  {source}: {redact_home(str(Path(directory).expanduser()))}")
        print("Try a wider --since range, --project filter, directory override, or --demo.")
        return 1
    report = summarize(sessions, args.full_paths, args.include_titles)
    try:
        output.write_text(render_html(report), encoding="utf-8")
        if json_output:
            json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Could not write report: {exc.strerror or type(exc).__name__}", file=sys.stderr)
        return 1
    totals = report["totals"]
    print(f"{totals['sessions']:,} sessions · {totals['active_seconds']/3600:.1f} active hours · "
          f"{totals['tool_calls']:,} tool calls · {totals['failed_tool_calls']:,} failures "
          f"({totals['failure_rate']:.1%}) · {totals['total_tokens']:,} tokens")
    print(f"HTML: {redact_home(str(output.resolve()))}")
    if json_output:
        print(f"JSON: {redact_home(str(json_output.resolve()))}")
    if args.open:
        try:
            webbrowser.open(output.resolve().as_uri())
        except webbrowser.Error:
            print("Report saved; browser could not be opened.", file=sys.stderr)
    return 0
