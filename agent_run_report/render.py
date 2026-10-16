"""A self-contained report: no assets, libraries, or network connections."""

from html import escape
from math import isclose, log10, floor


def e(value):
    return escape(str(value), quote=True)


def compact(value):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{value:g}"


def tick_label(value, mode):
    if mode == "hours":
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if mode == "tokens":
        return compact(value)
    return f"{value:,.0f}"


def nice_ticks(value, mode):
    """Return (value, label) ticks with a rounded upper bound and readable steps."""
    value = max(1, value)
    magnitude = 10 ** floor(log10(value))
    maximum = next(multiplier * magnitude for multiplier in (1, 2, 2.5, 5, 10)
                   if multiplier * magnitude >= value)
    precision = 1 if mode == "hours" else 0
    intervals = next(count for count in (4, 5, 2, 1)
                     if isclose(maximum / count, round(maximum / count, precision)))
    return [(maximum * index / intervals, tick_label(maximum * index / intervals, mode))
            for index in range(intervals + 1)]


def duration(seconds):
    return f"{seconds / 3600:.1f}h" if seconds >= 3600 else f"{seconds / 60:.1f}m"


def svg_start(label, width=640, height=240):
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{e(label)}"><title>{e(label)}</title>'


def daily_chart(days, mode):
    label = {"sessions": "Sessions per day", "hours": "Active hours per day", "tokens": "Tokens per day"}[mode]
    if not days:
        return '<p class="muted">No activity recorded.</p>'
    if mode == "tokens":
        series = [[d["tokens"]["input"], d["tokens"]["output"],
                   d["tokens"]["cache_read"] + d["tokens"]["cache_write"]] for d in days]
    else:
        series = [[d["sessions"] if mode == "sessions" else d["active_seconds"] / 3600] for d in days]
    ticks = nice_ticks(max(sum(values) for values in series), mode)
    maximum = ticks[-1][0]
    # A full font-size per character leaves room even for wide system-font glyphs.
    left = max(48, max(len(text) for _, text in ticks) * 12 + 20)
    chart = [svg_start(label), f'<line x1="{left}" y1="195" x2="628" y2="195" class="axis"/>']
    for value, text in ticks:
        y = 195 - 165 * value / maximum
        chart.append(f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{text}</text>')
        if value:
            chart.append(f'<line x1="{left}" y1="{y}" x2="628" y2="{y}" class="grid"/>')
    step = (628 - left) / len(days)
    for index, (day, values) in enumerate(zip(days, series)):
        bottom = 195
        for part, value in enumerate(values):
            height = 165 * value / maximum
            color = ("input", "output", "cache")[part] if mode == "tokens" else ("output" if mode == "hours" else "input")
            chart.append(f'<rect x="{left + index * step + step * .14:.2f}" y="{bottom - height:.2f}" '
                         f'width="{step * .72:.2f}" height="{height:.2f}" class="{color}">'
                         f'<title>{e(day["date"])}: {tick_label(value, mode)}</title></rect>')
            bottom -= height
        stride = max(1, (len(days) + 7) // 8)
        if index % stride == 0:
            chart.append(f'<text x="{left + (index + .5) * step:.2f}" y="218" text-anchor="middle">{e(day["date"][5:])}</text>')
    chart.append('</svg>')
    return "".join(chart)


def bar_chart(values, label, failure=False):
    entries = sorted(values.items(), key=lambda pair: pair[1], reverse=True)[:10]
    if not entries:
        return '<p class="muted">No failures recorded.</p>' if failure else '<p class="muted">No tool calls recorded.</p>'
    height = 38 * len(entries) + 20
    chart = [svg_start(label, height=height)]
    maximum = nice_ticks(max(value for _, value in entries), "counts")[-1][0]
    names = [name if len(name) <= 24 else name[:21] + "…" for name, _ in entries]
    labels = [tick_label(value, "counts") for _, value in entries]
    left = max(193, max(map(len, names)) * 12 + 26)
    right = max(map(len, labels)) * 12 + 20
    width = 640 - left - right
    for index, ((name, value), short, text) in enumerate(zip(entries, names, labels)):
        y = index * 38 + 10
        chart.append(f'<text x="{left - 13}" y="{y + 17}" text-anchor="end">{e(short)}<title>{e(name)}</title></text>'
                     f'<rect x="{left}" y="{y}" width="{width * value / maximum:.2f}" height="25" rx="4" '
                     f'class="{"failure" if failure else "input"}"><title>{e(name)}: {value:,}</title></rect>'
                     f'<text x="{left + 10 + width * value / maximum:.2f}" y="{y + 17}">{text}</text>')
    chart.append('</svg>')
    return "".join(chart)


CSS = """
:root{color-scheme:light dark;--bg:#f3f5fa;--card:#fff;--ink:#1c2639;--muted:#5b6980;
--line:#dfe5ef;--accent:#5265db;--green:#218772;--cache:#af74ca;--red:#c95162}
@media(prefers-color-scheme:dark){:root{--bg:#101521;--card:#1a2232;--ink:#e4ebf9;
--muted:#a3b0c7;--line:#303d52;--accent:#8999ff;--green:#5ec6ae;--cache:#c395dc;--red:#f08392}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,sans-serif}
main{max-width:1440px;margin:auto;padding:40px 28px}h1{font-size:clamp(28px,4vw,42px);letter-spacing:-1.4px;line-height:1.2;margin:8px 0}
h2{font-size:18px;margin:0 0 18px}p{margin:8px 0}.eyebrow{color:var(--accent);font-weight:750;letter-spacing:2px;font-size:12px}
.muted,footer{color:var(--muted)}.badge{display:inline-block;border:1px solid var(--line);padding:3px 10px;border-radius:20px;font-size:12px}
.stats{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:28px 0}
.stat,.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;min-width:0}
.stat strong{display:block;font-size:27px;line-height:1.4}.stat span{color:var(--muted);font-size:12px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:18px 0}.wide{grid-column:1/-1}
svg{width:100%;height:auto;display:block}svg text{fill:var(--muted);font:12px system-ui,sans-serif}
.axis,.grid{stroke:var(--line);stroke-width:1}.grid{stroke-dasharray:3 4}.input{fill:var(--accent)}.output{fill:var(--green)}
.cache{fill:var(--cache)}.failure{fill:var(--red)}.legend{display:flex;gap:18px;font-size:12px;color:var(--muted)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.insights{border-left:4px solid var(--accent)}
ul{padding-left:22px;margin:0}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:13px 12px;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-size:12px}
td:first-child{font-weight:600}td.wrap{white-space:normal;min-width:170px;overflow-wrap:anywhere}tbody tr:hover{background:var(--bg)}
th button{font:inherit;font-weight:650;color:inherit;background:none;border:0;cursor:pointer;padding:0}th button:focus-visible{outline:2px solid var(--accent)}
input{width:min(100%,340px);padding:10px 13px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:9px;font:inherit;margin:0 0 18px}
details{font-size:12px;max-width:350px}summary{cursor:pointer;color:var(--accent)}.detail{white-space:normal;overflow-wrap:anywhere}
.section{margin-top:20px}footer{font-size:12px;margin:28px 0}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
@media(max-width:950px){.stats{grid-template-columns:repeat(3,1fr)}}
@media(max-width:650px){main{padding:24px 12px}.charts{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.panel{padding:16px}}
"""

JS = """
const table = document.getElementById('sessions');
const search = document.getElementById('search');
search.addEventListener('input', () => {
  const term = search.value.toLocaleLowerCase();
  let visible = 0;
  table.tBodies[0].querySelectorAll('tr').forEach(row => {
    row.hidden = !row.textContent.toLocaleLowerCase().includes(term);
    if (!row.hidden) visible++;
  });
  document.getElementById('matches').textContent = visible + ' sessions shown';
});
table.querySelectorAll('th button').forEach((button, index) => {
  button.addEventListener('click', () => {
    const th = button.parentElement;
    const asc = th.getAttribute('aria-sort') !== 'ascending';
    table.querySelectorAll('th').forEach(h => h.removeAttribute('aria-sort'));
    th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
    const rows = Array.from(table.tBodies[0].rows);
    rows.sort((a,b) => {
      const x = a.cells[index].dataset.sort, y = b.cells[index].dataset.sort;
      const result = button.dataset.numeric === 'true' ? Number(x)-Number(y) : x.localeCompare(y);
      return asc ? result : -result;
    });
    rows.forEach(row => table.tBodies[0].appendChild(row));
  });
});
"""


def cell(text, sort=None, css=""):
    return f'<td class="{css}" data-sort="{e(text if sort is None else sort)}">{e(text)}</td>'


def render_html(report):
    totals = report["totals"]
    period = report["date_range"]
    date_label = f"{(period['start'] or '')[:10]} — {(period['end'] or '')[:10]} · UTC"
    stats = [("Sessions", f"{totals['sessions']:,}"), ("Active hours", f"{totals['active_seconds']/3600:.1f}"),
             ("Tool calls", f"{totals['tool_calls']:,}"), ("Failures", f"{totals['failed_tool_calls']:,}"),
             ("Failure rate", f"{totals['failure_rate']:.1%}"), ("Tokens", f"{totals['total_tokens']:,}")]
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
             '<title>Agent Run Report</title><style>', CSS, '</style></head><body><main>',
             '<header><div class="eyebrow">LOCAL ACTIVITY · PRIVATE BY DEFAULT</div><h1>See what your agents actually did.</h1>',
             f'<p class="muted">{e(date_label)}</p><p>',
             " ".join(f'<span class="badge">{e(source)}</span>' for source in report["sources"]),
             '</p></header><section class="stats" aria-label="Totals">']
    parts += [f'<div class="stat"><strong>{e(value)}</strong><span>{label}</span></div>' for label, value in stats]
    parts += ['</section><section class="panel insights"><h2>Insights</h2><ul>',
              "".join(f'<li>{e(insight)}</li>' for insight in report["insights"]), '</ul></section>',
              '<div class="charts">']
    for title, content in [("Sessions per day", daily_chart(report["days"], "sessions")),
                           ("Active hours per day", daily_chart(report["days"], "hours")),
                           ("Top 10 tools", bar_chart(report["tools"], "Top tools")),
                           ("Failures by tool", bar_chart(report["failures_by_tool"], "Failures by tool", True)),
                           ("Tokens per day", daily_chart(report["days"], "tokens"))]:
        parts.append(f'<section class="panel{" wide" if title == "Tokens per day" else ""}"><h2>{title}</h2>{content}')
        if title == "Tokens per day":
            parts.append('<div class="legend"><span><i class="dot" style="background:var(--accent)"></i>Input</span><span><i class="dot" style="background:var(--green)"></i>Output</span><span><i class="dot" style="background:var(--cache)"></i>Cache read + write</span></div>')
        parts.append('</section>')
    parts.append('</div><section class="panel section"><h2>By project</h2><div class="table-wrap"><table><thead><tr>')
    parts += [f'<th scope="col">{label}</th>' for label in ("Project", "Sessions", "Active time", "Tool calls", "Failures", "Tokens")]
    parts.append('</tr></thead><tbody>')
    for project in report["projects"]:
        parts.append('<tr>' + cell(project["project"], css="wrap") + cell(f'{project["sessions"]:,}') +
                     cell(duration(project["active_seconds"])) + cell(f'{project["tool_calls"]:,}') +
                     cell(f'{project["failures"]:,}') + cell(f'{project["tokens"]:,}') + '</tr>')
    parts.append('</tbody></table></div></section><section class="panel section"><h2>Sessions</h2>')
    parts.append('<label for="search" class="sr-only">Search sessions</label><input id="search" type="search" placeholder="Search project, source, model…">')
    parts.append(f'<p id="matches" class="muted" aria-live="polite">{totals["sessions"]} sessions shown</p>')
    parts.append('<div class="table-wrap"><table id="sessions"><thead><tr>')
    columns = [("Project", False), ("Source", False), ("Session", False), ("Start (UTC)", False),
               ("End (UTC)", False), ("Active", True), ("Prompts", True), ("Assistant", True),
               ("Tools", True), ("Failures", True), ("Tokens", True), ("Files", True), ("Subagent activity", True), ("Models / details", False)]
    for label, numeric in columns:
        parts.append(f'<th scope="col"><button type="button" data-numeric="{str(numeric).lower()}">{label} ↕</button></th>')
    parts.append('</tr></thead><tbody>')
    for row in report["sessions"]:
        project = cell(row["project"], css="wrap")
        if row.get("title"):
            project = project.replace('</td>', f'<br><small>{e(row["title"])}</small></td>')
        parts.append('<tr>' + project + cell(row["source"]) + cell(row["session_id"]) +
                     cell(row["start"][:16].replace("T", " "), row["start"]) +
                     cell(row["end"][:16].replace("T", " "), row["end"]) +
                     cell(duration(row["active_seconds"]), row["active_seconds"]) + cell(row["user_prompts"]) +
                     cell(row["assistant_turns"]) + cell(sum(row["tools"].values())) + cell(row["failed_tool_calls"]) +
                     cell(f'{sum(row["tokens"].values()):,}', sum(row["tokens"].values())) +
                     cell(row["files_touched"]) + cell(row["subagent_activity"]))
        models = ", ".join(row["models"]) or "Unknown model"
        detail = f'<div class="detail">Models: {e(models)}<br>'
        detail += '<br>'.join(f'{e(name)}: {count:,} calls' for name, count in sorted(row["tools"].items()))
        detail += '<br>' + ' · '.join(f'{key.replace("_", " ")}: {value:,}' for key, value in row["tokens"].items())
        if row.get("files"):
            detail += '<br>Files:<br>' + '<br>'.join(e(path) for path in row["files"])
        parts.append(f'<td data-sort="{e(models)}"><details><summary>{e(models)}</summary>{detail}</div></details></td></tr>')
    parts.append('</tbody></table></div></section><footer>Generated locally by agent-run-report · No uploads or external resources. ')
    parts.append('Prompt text and tool inputs/outputs are never included. ')
    parts.append('Titles: ' + ('included' if report["privacy"]["include_titles"] else 'hidden') + '. ')
    parts.append('Paths: ' + ('included; home replaced with ~' if report["privacy"]["full_paths"] else 'project basenames only; file names hidden') + '.<br>')
    parts.append('Active time sums event gaps capped at 5 minutes; overlapping sessions are summed. Days and dates use UTC. '
                 'Tokens are recorded usage, with cached input separated from input. '
                 'Failures include reported tool errors and unattributed error events. '
                 'Missing or unrecognized log fields may make counts incomplete.</footer></main><script>')
    parts += [JS, '</script></body></html>']
    return "".join(parts)
