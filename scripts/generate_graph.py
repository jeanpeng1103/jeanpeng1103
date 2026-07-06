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

# Pastel "commit garden" palette — softer & cuter than default GitHub green
LEVELS = [
    ("#fff5f8", 0),   # cream pink — no commits
    ("#d4f5e9", 1),   # mint whisper
    ("#a8e6cf", 4),   # soft sage
    ("#7dcea0", 7),   # meadow
    ("#52b788", 10),  # forest mint
    ("#ff9ecd", 16),  # blossom pink — super active days ✨
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAY_LABELS = [(1, "Mon"), (3, "Wed"), (5, "Fri")]


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


def month_positions(weeks: list, cell: int, gap: int, offset_x: int, offset_y: int) -> list[tuple[int, str]]:
    labels: list[tuple[int, str]] = []
    last_month = -1
    for week_idx, week in enumerate(weeks):
        first_day = week["contributionDays"][0]["date"]
        month = datetime.fromisoformat(first_day).month - 1
        if month != last_month:
            x = offset_x + week_idx * (cell + gap)
            labels.append((x, MONTHS[month]))
            last_month = month
    return labels


def render_svg(calendar: dict) -> str:
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    current_streak, longest_streak = compute_streaks(weeks)

    cell = 13
    gap = 3
    radius = 4
    pad = 20
    label_w = 28
    header_h = 88
    legend_h = 36
    footer_h = 28

    grid_w = len(weeks) * (cell + gap) - gap
    grid_h = 7 * (cell + gap) - gap
    width = pad * 2 + label_w + grid_w
    height = pad + header_h + grid_h + legend_h + footer_h + pad

    offset_x = pad + label_w
    offset_y = pad + header_h

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '  <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="140%">',
        '    <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#e8b4d4" flood-opacity="0.35"/>',
        "  </filter>",
        '  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '    <stop offset="0%" stop-color="#fff9fc"/>',
        '    <stop offset="100%" stop-color="#f0fdf8"/>',
        "  </linearGradient>",
        "</defs>",
        f'<rect width="{width}" height="{height}" rx="16" fill="url(#bg)" stroke="#f5c6e0" stroke-width="1.5"/>',
        # Header
        f'<text x="{pad}" y="{pad + 22}" font-family="ui-rounded, \'SF Pro Rounded\', \'Nunito\', system-ui, sans-serif" font-size="18" font-weight="700" fill="#6b4c7a">🌱 commit garden</text>',
        f'<text x="{pad}" y="{pad + 46}" font-family="ui-rounded, \'SF Pro Rounded\', \'Nunito\', system-ui, sans-serif" font-size="13" fill="#9b7fa8">',
        f"{total:,} contributions in the last year",
        "</text>",
        f'<text x="{pad}" y="{pad + 64}" font-family="ui-rounded, \'SF Pro Rounded\', \'Nunito\', system-ui, sans-serif" font-size="11" fill="#b8a0c4">',
        f"🔥 {current_streak} day streak  ·  🏆 best {longest_streak} days",
        "</text>",
    ]

    # Month labels
    for x, label in month_positions(weeks, cell, gap, offset_x, offset_y):
        parts.append(
            f'<text x="{x}" y="{offset_y - 8}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#c4a8d4">{label}</text>'
        )

    # Day labels
    for row, label in DAY_LABELS:
        y = offset_y + row * (cell + gap) + cell - 2
        parts.append(
            f'<text x="{pad}" y="{y}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#c4a8d4">{label}</text>'
        )

    # Grid cells
    for week_idx, week in enumerate(weeks):
        for day_idx, day in enumerate(week["contributionDays"]):
            count = day["contributionCount"]
            x = offset_x + week_idx * (cell + gap)
            y = offset_y + day_idx * (cell + gap)
            fill = color_for_count(count)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="{radius}" ry="{radius}" '
                f'fill="{fill}" filter="url(#soft-shadow)">'
                f"<title>{day['date']}: {count} contribution{'s' if count != 1 else ''}</title>"
                f"</rect>"
            )
            if count >= 16:
                parts.append(
                    f'<text x="{x + cell / 2}" y="{y + cell / 2 + 3}" text-anchor="middle" '
                    f'font-size="7" fill="#fff" pointer-events="none">✦</text>'
                )

    # Legend
    legend_y = offset_y + grid_h + 18
    legend_x = offset_x
    parts.append(
        f'<text x="{legend_x}" y="{legend_y}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#b8a0c4">Less</text>'
    )
    lx = legend_x + 30
    for color, _ in LEVELS:
        parts.append(
            f'<rect x="{lx}" y="{legend_y - 9}" width="{cell}" height="{cell}" rx="{radius}" fill="{color}" filter="url(#soft-shadow)"/>'
        )
        lx += cell + 4
    parts.append(
        f'<text x="{lx + 4}" y="{legend_y}" font-family="ui-rounded, system-ui, sans-serif" font-size="10" fill="#b8a0c4">More ✨</text>'
    )

    parts.append(
        f'<text x="{width - pad}" y="{height - pad + 4}" text-anchor="end" '
        f'font-family="ui-rounded, system-ui, sans-serif" font-size="9" fill="#d4b8e0">@{USERNAME}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


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
    default_out = root / "assets" / "contribution-graph.svg"
    out = Path(os.environ.get("OUTPUT", str(default_out)))
    if "--demo" in sys.argv or not (os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")):
        if "--demo" not in sys.argv and not (os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")):
            print("No token found — generating demo preview. Pass --demo explicitly or set GH_PAT.", file=sys.stderr)
        calendar = demo_calendar()
    else:
        calendar = fetch_contribution_calendar()
    svg = render_svg(calendar)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"Wrote {out} ({calendar['totalContributions']} total contributions)")


if __name__ == "__main__":
    main()
