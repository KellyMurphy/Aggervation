"""Extract the board layout from the Illustrator SVG export.

Uses the named zone rectangles in the SVG (``<Color>_base_zone``,
``<Color>_start_zone``, ``<Color>_home_zone``) to classify holes, then
writes ``src/aggervation/layout_data.py``.

Run from the project root:
    uv run python tools/extract_layout.py
"""

from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "basics" / "Aggravation 4 Player Full Size.svg"
OUT_PATH = ROOT / "src" / "aggervation" / "layout_data.py"

NS = "{http://www.w3.org/2000/svg}"
COLORS = ["Red", "Green", "Blue", "Yellow"]
HOLE_MAX_RADIUS = 10  # anything bigger is background art
NEIGHBOR_DIST = 60  # holes on the track are ~41-46 units apart
HOLES_PER_ZONE = 4
EXPECTED_TRACK_LEN = 96

Point = tuple[float, float]


def parse_transform(text: str | None):
    """Return a function mapping SVG (global) coords into the element's local coords.

    Only handles the ``translate(...) rotate(...)`` forms Illustrator emits here.
    """
    tx = ty = 0.0
    angle = 0.0
    if text:
        m = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", text)
        if m:
            tx, ty = float(m.group(1)), float(m.group(2))
        m = re.search(r"rotate\(([-\d.]+)\)", text)
        if m:
            angle = math.radians(float(m.group(1)))
    # global = T + R(angle) * local  =>  local = R(-angle) * (global - T)
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)

    def to_local(p: Point) -> Point:
        x, y = p[0] - tx, p[1] - ty
        return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)

    return to_local


def rect_contains(rect: ET.Element, p: Point) -> bool:
    x, y = float(rect.get("x", 0)), float(rect.get("y", 0))
    w, h = float(rect.get("width")), float(rect.get("height"))
    lx, ly = parse_transform(rect.get("transform"))(p)
    return x <= lx <= x + w and y <= ly <= y + h


def order_loop(points: list[Point]) -> list[Point]:
    """Walk nearest neighbours to put the track holes in loop order, clockwise on screen."""
    remaining = list(points)
    loop = [remaining.pop(0)]
    while remaining:
        cur = loop[-1]
        nxt = min(remaining, key=lambda p: math.dist(cur, p))
        if math.dist(cur, nxt) > NEIGHBOR_DIST:
            sys.exit(f"Track walk broke at {cur}; nearest hole {nxt} is too far away")
        loop.append(nxt)
        remaining.remove(nxt)
    if math.dist(loop[-1], loop[0]) > NEIGHBOR_DIST:
        sys.exit("Track does not close into a loop")
    # Shoelace: with y pointing down, a positive sum means clockwise on screen.
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:] + loop[:1]))
    if area < 0:
        loop.reverse()
    return loop


def main() -> None:
    root = ET.parse(SVG_PATH).getroot()
    view_box = [float(v) for v in root.get("viewBox").split()]

    holes: list[Point] = [
        (float(c.get("cx")), float(c.get("cy")))
        for c in root.iter(f"{NS}circle")
        if float(c.get("r")) <= HOLE_MAX_RADIUS
    ]
    rects = {r.get("id"): r for r in root.iter(f"{NS}rect") if r.get("id")}

    bases: dict[str, list[Point]] = {}
    homes: dict[str, list[Point]] = {}
    starts: dict[str, Point] = {}
    claimed: set[Point] = set()

    for color in COLORS:
        base = [p for p in holes if rect_contains(rects[f"{color}_base_zone"], p)]
        home = [p for p in holes if rect_contains(rects[f"{color}_home_zone"], p)]
        start = [p for p in holes if rect_contains(rects[f"{color}_start_zone"], p)]
        if len(base) != HOLES_PER_ZONE or len(home) != HOLES_PER_ZONE or len(start) != 1:
            sys.exit(f"{color}: found {len(base)} base, {len(home)} home, {len(start)} start holes")
        bases[color], homes[color], starts[color] = base, home, start[0]
        claimed.update(base, home)

    track = order_loop([p for p in holes if p not in claimed])
    if len(track) != EXPECTED_TRACK_LEN:
        sys.exit(f"Track has {len(track)} holes, expected {EXPECTED_TRACK_LEN}")

    # Put Red's start at index 0 so indices read naturally.
    first = track.index(starts["Red"])
    track = track[first:] + track[:first]

    players = {}
    for color in COLORS:
        home = homes[color]
        # The home entry is the track hole closest to the home row.
        entry = min(range(len(track)), key=lambda i: min(math.dist(track[i], h) for h in home))
        # Order home holes from the entry inward.
        home_sorted = sorted(home, key=lambda h: math.dist(track[entry], h))
        # Order base holes nearest-the-start first.
        base_sorted = sorted(bases[color], key=lambda b: math.dist(starts[color], b))
        players[color.upper()] = {
            "start_index": track.index(starts[color]),
            "home_entry_index": entry,
            "base": base_sorted,
            "home": home_sorted,
        }

    write_output(view_box, track, players)
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}: track={len(track)} holes")
    for color, info in players.items():
        print(f"  {color:6} start={info['start_index']:2} home_entry={info['home_entry_index']:2}")


def fmt_pt(p: Point) -> str:
    return f"({p[0]:.2f}, {p[1]:.2f})"


def fmt_pts(points: list[Point], indent: str) -> str:
    rows = [", ".join(fmt_pt(p) for p in points[i : i + 6]) for i in range(0, len(points), 6)]
    return "[\n" + "".join(f"{indent}    {r},\n" for r in rows) + f"{indent}]"


def write_output(view_box: list[float], track: list[Point], players: dict) -> None:
    lines = [
        '"""Board layout extracted from the SVG. Generated by tools/extract_layout.py - do not edit."""',
        "",
        f"VIEWBOX = ({view_box[2]:.2f}, {view_box[3]:.2f})",
        "",
        "# Main track, in clockwise (movement) order. Index 0 is Red's start hole.",
        f"TRACK = {fmt_pts(track, '')}",
        "",
        "# Per player: base holes (nearest the start first), home holes (entry first),",
        "# the track index of the start hole, and the track index you turn off at into home.",
        "PLAYERS = {",
    ]
    for color, info in players.items():
        lines += [
            f'    "{color}": {{',
            f'        "start_index": {info["start_index"]},',
            f'        "home_entry_index": {info["home_entry_index"]},',
            f'        "base": {fmt_pts(info["base"], " " * 8)},',
            f'        "home": {fmt_pts(info["home"], " " * 8)},',
            "    },",
        ]
    lines += ["}", ""]
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
