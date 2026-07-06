#!/usr/bin/env python3
"""Generate a cute contribution grid SVG from GitHub commit data (incl. private repos)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

GITHUB_API = "https://api.github.com/graphql"
USERNAME = os.environ.get("GITHUB_USERNAME", "jeanpeng1103")

# Deeper "commit garden" palette — richer greens, still cute
LEVELS = [
    ("#e4ebe6", 0),   # muted sage gray — no commits
    ("#7ec99a", 1),   # fresh mint
    ("#4fb87a", 4),   # rich green
    ("#2f9f62", 7),   # deep meadow
    ("#1f7a4c", 10),  # forest
    ("#b83279", 16),  # deep rose — super active days ✨
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAY_LABELS = [(1, "Mon"), (3, "Wed"), (5, "Fri")]

CELL = 15
GAP = 3
RADIUS = 4
PAD = 20
LABEL_W = 28
HEADER_H = 88
LEGEND_H = 36
FOOTER_H = 28


def github_request(query: str, variables: dict | None = None) -> dict:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Missing GH_PAT or GITHUB_TOKEN environment variable")

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    req = urllib.request.Request(
        GITHUB_API,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "cute-commit-garden",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise SystemExit(f"GitHub API error {exc.code}: {detail}") from exc

    if body.get("errors"):
        raise SystemExit(f"GraphQL errors: {body['errors']}")

    return body["data"]


def fetch_contribution_calendar() -> dict:
    """Pull full contribution calendar (private + public) for the authenticated user."""
    today = date.today()
    one_year_ago = today - timedelta(days=364)

    query = """
    query($from: DateTime!, $to: DateTime!) {
      viewer {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "from": f"{one_year_ago.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z",
    }
    data = github_request(query, variables)
    return data["viewer"]["contributionsCollection"]["contributionCalendar"]


def color_for_count(count: int) -> str:
    chosen = LEVELS[0][0]
    for color, minimum in LEVELS:
        if count >= minimum:
            chosen = color
    return chosen


def text_color_for_count(count: int) -> str:
    if count >= 4:
        return "#ffffff"
    if count >= 1:
        return "#1a4d32"
    return "#9aa89f"


def format_day_label(day_str: str) -> str:
    d = date.fromisoformat(day_str)
    return d.strftime("%b %-d, %Y") if os.name != "nt" else d.strftime("%b %d, %Y").replace(" 0", " ")


def contribution_label(count: int) -> str:
    noun = "contribution" if count == 1 else "contributions"
    return f"{count} {noun}"


def compute_streaks(weeks: list) -> tuple[int, int]:
    """Return (current_streak, longest_streak) in days with >=1 contribution."""
    days: list[tuple[date, int]] = []
    for week in weeks:
        for day in week["contributionDays"]:
            days.append((date.fromisoformat(day["date"]), day["contributionCount"]))

    days.sort(key=lambda item: item[0])
    longest = 0
    running = 0
    for _, count in days:
        if count > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    current = 0
    for _, count in reversed(days):
        if count > 0:
            current += 1
        else:
            break

    return current, longest


def month_positions(weeks: list, offset_x: int, offset_y: int) -> list[tuple[int, str]]:
    labels: list[tuple[int, str]] = []
    last_month = -1
    for week_idx, week in enumerate(weeks):
        first_day = week["contributionDays"][0]["date"]
        month = datetime.fromisoformat(first_day).month - 1
        if month != last_month:
            x = offset_x + week_idx * (CELL + GAP)
            labels.append((x, MONTHS[month]))
            last_month = month
    return labels


def grid_metrics(weeks: list) -> dict:
    grid_w = len(weeks) * (CELL + GAP) - GAP
    grid_h = 7 * (CELL + GAP) - GAP
    width = PAD * 2 + LABEL_W + grid_w
    height = PAD + HEADER_H + grid_h + LEGEND_H + FOOTER_H + PAD
    return {
        "grid_w": grid_w,
        "grid_h": grid_h,
        "width": width,
        "height": height,
        "offset_x": PAD + LABEL_W,
        "offset_y": PAD + HEADER_H,
    }


def render_header_parts(total: int, current_streak: int, longest_streak: int) -> list[str]:
    return [
        f'<text x="{PAD}" y="{PAD + 22}" font-family="ui-rounded, \'SF Pro Rounded\', \'Nunito\', system-ui, sans-serif" font-size="18" font-weight="700" fill="#6b4c7a">🌱 commit garden</text>',
        f'<text x="{PAD}" y="{PAD + 46}" font-family="ui-rounded, \'SF Pro Rounded\', \'Nunito\', system-ui, sans-serif" font-size="13" fill="#9b7fa8">{total:,} contributions in the last year</text>',
        f'<text x="{PAD}" y="{PAD + 64}" font-family="ui-rounded, \'SF Pro Rounded\', \'Nunito\', system-ui, sans-serif" font-size="11" fill="#b8a0c4">🔥 {current_streak} day streak  ·  🏆 best {longest_streak} days</text>',
    ]


def iter_days(weeks: list, offset_x: int, offset_y: int):
    for week_idx, week in enumerate(weeks):
        for day_idx, day in enumerate(week["contributionDays"]):
            count = day["contributionCount"]
            x = offset_x + week_idx * (CELL + GAP)
            y = offset_y + day_idx * (CELL + GAP)
            yield day, count, x, y


def render_svg(calendar: dict) -> str:
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    current_streak, longest_streak = compute_streaks(weeks)
    m = grid_metrics(weeks)
    width, height = m["width"], m["height"]
    offset_x, offset_y = m["offset_x"], m["offset_y"]
    grid_h = m["grid_h"]

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '  <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="140%">',
        '    <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#e8b4d4" flood-opacity="0.35"/>',
        "  </filter>",
        '  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '    <stop offset="0%" stop-color="#f4f8f5"/>',
        '    <stop offset="100%" stop-color="#e8f2ec"/>',
        "  </linearGradient>",
        "</defs>",
        "<style>",
        "  .day-cell { cursor: pointer; }",
        "  .day-cell .hover-tip { opacity: 0; transition: opacity 0.12s ease; pointer-events: none; }",
        "  .day-cell:hover .hover-tip { opacity: 1; }",
        "  .day-cell:hover .cell-rect { stroke: #1f7a4c; stroke-width: 1.5; }",
        "  .day-cell:hover .cell-count { opacity: 1; }",
        "  .cell-count { opacity: 0; pointer-events: none; font-weight: 700; }",
        "  .day-cell[data-count]:not([data-count='0']):hover .cell-count { opacity: 1; }",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="16" fill="url(#bg)" stroke="#8fbc9a" stroke-width="1.5"/>',
        *render_header_parts(total, current_streak, longest_streak),
    ]

    for x, label in month_positions(weeks, offset_x, offset_y):
        parts.append(
            f'<text x="{x}" y="{offset_y - 8}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#c4a8d4">{label}</text>'
        )

    for row, label in DAY_LABELS:
        y = offset_y + row * (CELL + GAP) + CELL - 2
        parts.append(
            f'<text x="{PAD}" y="{y}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#c4a8d4">{label}</text>'
        )

    for day, count, x, y in iter_days(weeks, offset_x, offset_y):
        fill = color_for_count(count)
        label = format_day_label(day["date"])
        tip = contribution_label(count)
        count_text = str(count) if count <= 99 else "99+"
        text_fill = text_color_for_count(count)
        tip_y = y - 6 if y > offset_y + 18 else y + CELL + 14

        parts.append(
            f'<g class="day-cell" data-count="{count}" data-date="{day["date"]}">'
            f'<title>{label}: {tip}</title>'
            f'<rect class="cell-rect" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RADIUS}" ry="{RADIUS}" fill="{fill}" filter="url(#soft-shadow)"/>'
        )
        if count > 0:
            font_size = 7 if count >= 10 else 8
            parts.append(
                f'<text class="cell-count" x="{x + CELL / 2}" y="{y + CELL / 2 + 3}" text-anchor="middle" '
                f'font-family="ui-rounded, system-ui, sans-serif" font-size="{font_size}" fill="{text_fill}">{count_text}</text>'
            )
        if count >= 16:
            parts.append(
                f'<text x="{x + CELL / 2}" y="{y + 5}" text-anchor="middle" font-size="6" fill="#fff" pointer-events="none">✦</text>'
            )
        parts.append(
            f'<g class="hover-tip">'
            f'<rect x="{x - 8}" y="{tip_y - 11}" width="{max(len(label) + len(tip) + 4, 18) * 5.2}" height="18" rx="6" fill="#6b4c7a" fill-opacity="0.92"/>'
            f'<text x="{x + CELL / 2}" y="{tip_y}" text-anchor="middle" font-family="ui-rounded, system-ui, sans-serif" font-size="9" fill="#fff">{tip}</text>'
            f"</g>"
            f"</g>"
        )

    legend_y = offset_y + grid_h + 18
    legend_x = offset_x
    parts.append(
        f'<text x="{legend_x}" y="{legend_y}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#b8a0c4">Less</text>'
    )
    lx = legend_x + 30
    for color, _ in LEVELS:
        parts.append(
            f'<rect x="{lx}" y="{legend_y - 9}" width="{CELL}" height="{CELL}" rx="{RADIUS}" fill="{color}" filter="url(#soft-shadow)"/>'
        )
        lx += CELL + 4
    parts.append(
        f'<text x="{lx + 4}" y="{legend_y}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#b8a0c4">More ✨</text>'
    )
    parts.append(
        f'<text x="{width - PAD}" y="{height - PAD + 4}" text-anchor="end" '
        f'font-family="ui-rounded, system-ui, sans-serif" font-size="9" fill="#d4b8e0">@{USERNAME}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def render_interactive_html(calendar: dict) -> str:
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    current_streak, longest_streak = compute_streaks(weeks)
    m = grid_metrics(weeks)
    width, height = m["width"], m["height"]
    offset_x, offset_y = m["offset_x"], m["offset_y"]
    grid_h = m["grid_h"]

    cells: list[str] = []
    for day, count, x, y in iter_days(weeks, offset_x, offset_y):
        fill = color_for_count(count)
        label = format_day_label(day["date"])
        tip = contribution_label(count)
        count_text = str(count) if count <= 99 else "99+"
        text_fill = text_color_for_count(count)
        sparkle = (
            f'<span class="sparkle">✦</span>' if count >= 16 else ""
        )
        count_markup = (
            f'<span class="cell-count" style="color:{text_fill}">{count_text}</span>' if count > 0 else ""
        )
        cells.append(
            f'<button type="button" class="day-cell" style="left:{x}px;top:{y}px;background:{fill}" '
            f'data-date="{label}" data-count="{tip}" aria-label="{label}: {tip}">'
            f"{count_markup}{sparkle}</button>"
        )

    month_labels = "".join(
        f'<span class="month" style="left:{x}px">{label}</span>'
        for x, label in month_positions(weeks, offset_x, offset_y)
    )
    day_labels = "".join(
        f'<span class="day-label" style="top:{offset_y + row * (CELL + GAP) + CELL - 10}px">{label}</span>'
        for row, label in DAY_LABELS
    )
    legend_cells = "".join(
        f'<span class="legend-swatch" style="background:{color}"></span>' for color, _ in LEVELS
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>commit garden · @{USERNAME}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, #f0f7f3 0%, #e3efe8 100%);
      font-family: ui-rounded, "SF Pro Rounded", "Nunito", system-ui, sans-serif;
    }}
    .wrap {{ position: relative; padding: 24px; }}
    .card {{
      position: relative;
      width: {width}px;
      height: {height}px;
      border-radius: 16px;
      background: linear-gradient(135deg, #f4f8f5 0%, #e8f2ec 100%);
      border: 1.5px solid #8fbc9a;
      box-shadow: 0 8px 24px rgba(232, 180, 212, 0.25);
      overflow: visible;
    }}
    .header {{
      position: absolute;
      left: {PAD}px;
      top: {PAD}px;
      color: #6b4c7a;
    }}
    .header h1 {{ margin: 0; font-size: 18px; }}
    .header p {{ margin: 6px 0 0; color: #9b7fa8; font-size: 13px; }}
    .header small {{ color: #b8a0c4; font-size: 11px; }}
    .grid-area {{
      position: absolute;
      left: 0;
      top: 0;
      width: {width}px;
      height: {height}px;
      pointer-events: none;
    }}
    .month, .day-label {{
      position: absolute;
      font-size: 10px;
      color: #c4a8d4;
      pointer-events: none;
    }}
    .month {{ top: {offset_y - 18}px; }}
    .day-label {{ left: {PAD}px; }}
    .day-cell {{
      position: absolute;
      width: {CELL}px;
      height: {CELL}px;
      border: none;
      border-radius: {RADIUS}px;
      padding: 0;
      cursor: pointer;
      pointer-events: auto;
      box-shadow: 0 1px 2px rgba(232, 180, 212, 0.35);
      transition: transform 0.12s ease, box-shadow 0.12s ease;
      display: grid;
      place-items: center;
    }}
    .day-cell:hover, .day-cell:focus-visible {{
      transform: scale(1.15);
      z-index: 2;
      box-shadow: 0 0 0 2px #8fbc9a, 0 4px 10px rgba(31, 122, 76, 0.25);
      outline: none;
    }}
    .cell-count {{
      font-size: 8px;
      font-weight: 700;
      line-height: 1;
      opacity: 0;
      transition: opacity 0.12s ease;
    }}
    .day-cell:hover .cell-count, .day-cell:focus-visible .cell-count {{
      opacity: 1;
    }}
    .sparkle {{
      position: absolute;
      top: 1px;
      font-size: 6px;
      color: #fff;
      pointer-events: none;
    }}
    .legend {{
      position: absolute;
      left: {offset_x}px;
      top: {offset_y + grid_h + 8}px;
      display: flex;
      align-items: center;
      gap: 4px;
      color: #b8a0c4;
      font-size: 10px;
      pointer-events: none;
    }}
    .legend-swatch {{
      width: {CELL}px;
      height: {CELL}px;
      border-radius: {RADIUS}px;
      box-shadow: 0 1px 2px rgba(232, 180, 212, 0.35);
    }}
    .footer {{
      position: absolute;
      right: {PAD}px;
      bottom: {PAD - 4}px;
      color: #d4b8e0;
      font-size: 9px;
      pointer-events: none;
    }}
    #tooltip {{
      position: fixed;
      pointer-events: none;
      padding: 6px 10px;
      border-radius: 8px;
      background: rgba(107, 76, 122, 0.94);
      color: #fff;
      font-size: 12px;
      line-height: 1.3;
      opacity: 0;
      transform: translate(-50%, calc(-100% - 10px));
      transition: opacity 0.1s ease;
      white-space: nowrap;
      z-index: 20;
      box-shadow: 0 4px 14px rgba(107, 76, 122, 0.3);
    }}
    #tooltip.visible {{ opacity: 1; }}
    #tooltip strong {{ display: block; font-size: 11px; color: #ffd8ec; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="header">
        <h1>🌱 commit garden</h1>
        <p>{total:,} contributions in the last year</p>
        <small>🔥 {current_streak} day streak · 🏆 best {longest_streak} days</small>
      </div>
      <div class="grid-area">
        {month_labels}
        {day_labels}
        {''.join(cells)}
        <div class="legend">
          <span>Less</span>
          {legend_cells}
          <span>More ✨</span>
        </div>
        <div class="footer">@{USERNAME}</div>
      </div>
    </div>
    <div id="tooltip"><strong></strong><span></span></div>
  </div>
  <script>
    const tip = document.getElementById("tooltip");
    const strong = tip.querySelector("strong");
    const span = tip.querySelector("span");

    function showTip(cell, x, y) {{
      strong.textContent = cell.dataset.date;
      span.textContent = cell.dataset.count;
      tip.style.left = x + "px";
      tip.style.top = y + "px";
      tip.classList.add("visible");
    }}

    function hideTip() {{
      tip.classList.remove("visible");
    }}

    document.querySelectorAll(".day-cell").forEach((cell) => {{
      cell.addEventListener("mouseenter", (e) => showTip(cell, e.clientX, e.clientY));
      cell.addEventListener("mousemove", (e) => showTip(cell, e.clientX, e.clientY));
      cell.addEventListener("mouseleave", hideTip);
      cell.addEventListener("focus", () => {{
        const rect = cell.getBoundingClientRect();
        showTip(cell, rect.left + rect.width / 2, rect.top);
      }});
      cell.addEventListener("blur", hideTip);
    }});
  </script>
</body>
</html>
"""


def demo_calendar() -> dict:
    """Fake data for local preview when no token is available."""
    import random

    random.seed(42)
    today = date.today()
    start = today - timedelta(days=364)
    start -= timedelta(days=start.weekday())  # align to Sunday

    weeks: list[dict] = []
    cursor = start
    while cursor <= today:
        days = []
        for _ in range(7):
            if cursor > today:
                count = 0
            else:
                roll = random.random()
                if roll < 0.35:
                    count = 0
                elif roll < 0.6:
                    count = random.randint(1, 3)
                elif roll < 0.85:
                    count = random.randint(4, 9)
                elif roll < 0.95:
                    count = random.randint(10, 15)
                else:
                    count = random.randint(16, 22)
            days.append({"date": cursor.isoformat(), "contributionCount": count})
            cursor += timedelta(days=1)
        weeks.append({"contributionDays": days})

    total = sum(d["contributionCount"] for w in weeks for d in w["contributionDays"])
    return {"totalContributions": total, "weeks": weeks}


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    svg_out = Path(os.environ.get("OUTPUT", str(root / "assets" / "contribution-graph.svg")))
    html_out = Path(os.environ.get("HTML_OUTPUT", str(root / "docs" / "index.html")))

    if "--demo" in sys.argv or not (os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")):
        if "--demo" not in sys.argv and not (os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")):
            print("No token found — generating demo preview. Pass --demo explicitly or set GH_PAT.", file=sys.stderr)
        calendar = demo_calendar()
    else:
        calendar = fetch_contribution_calendar()

    svg_out.parent.mkdir(parents=True, exist_ok=True)
    html_out.parent.mkdir(parents=True, exist_ok=True)
    svg_out.write_text(render_svg(calendar), encoding="utf-8")
    html_out.write_text(render_interactive_html(calendar), encoding="utf-8")
    print(f"Wrote {svg_out} ({calendar['totalContributions']} total contributions)")
    print(f"Wrote {html_out} (interactive hover version)")


if __name__ == "__main__":
    main()
