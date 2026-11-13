"""``recolors.json`` — 2 Minute Tabletop tokens recoloured for Stonetop.

A token whose colours are wrong for the book (the Ruined Tower's blue magpies
are "like big crows with white-and-azure plumage"; no token is) is made from
one that has the right shape. Each recipe names its source token and a list
of rules; the build writes the result to ``2 Minute Tabletop/Recolors/``
(gitignored, like the sets it is made from) and it is chosen in
``tokens.json`` as ``R:<Category>/<File>.png``, like any other token.

``recolors.json``::

    {"version": 1, "recolors": {"Beast/Blue Magpies.png": {
        "from": "D:Beast/Swarm of Birds.png",
        "note": "…",
        "alpha_min": 130,        # pixels fainter than this (the drop shadow) stay
        "dark_max": 0.12,        # pixels darker than this (the ink outline) stay
        "stretch": 2.0,          # luminance is multiplied by this before a ramp
        "rules": [               # first match wins; a pixel no rule takes stays
            {"hue": [0.92, 0.05], "sat_min": 0.45, "val_min": 0.35, "color": [20, 20, 28]},
            {"sat_min": 0.5, "ramp": [[0, [10, 12, 22]], [0.4, [40, 125, 215]], [1, [255, 255, 255]]]},
            {"ramp": [...]}
        ]}}}

A ``ramp`` maps the pixel's (stretched) luminance onto colour stops, so the
drawing's shading survives; a ``color`` sets it flat; ``"keep": true`` leaves
it (a rule ahead of the others, for eyes or a beak). ``"normalize": [lo, hi]``
first stretches the image's own luminance percentiles ``lo``–``hi`` (of the
pixels a rule could touch) to 0–1, so one ramp suits a pale source and a dark
one alike. ``hue`` is a range in
0–1 (it may wrap past 1, as red does); ``sat_min``/``sat_max``/``val_min``/
``val_max`` bound the HSV saturation and value.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path

from . import REPO_ROOT

RECOLORS_FILE = REPO_ROOT / "recolors.json"
OUT_ROOT = REPO_ROOT / "2 Minute Tabletop" / "Recolors"


def recipes() -> dict[str, dict]:
    try:
        data = json.loads(RECOLORS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("recolors") or {}


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _ramp_at(ramp, v: float):
    stops = [(float(p), tuple(c)) for p, c in ramp]
    if v <= stops[0][0]:
        return stops[0][1]
    for (v0, c0), (v1, c1) in zip(stops, stops[1:]):
        if v <= v1:
            return _lerp(c0, c1, (v - v0) / (v1 - v0) if v1 > v0 else 0)
    return stops[-1][1]


def _matches(rule: dict, h: float, s: float, v: float) -> bool:
    hue = rule.get("hue")
    if hue:
        a, b = hue
        if a <= b and not (a <= h <= b):
            return False
        if a > b and not (h >= a or h <= b):
            return False
    if s < rule.get("sat_min", 0) or s > rule.get("sat_max", 1):
        return False
    if v < rule.get("val_min", 0) or v > rule.get("val_max", 1):
        return False
    return True


def recolor(src: Path, spec: dict):
    """The recoloured image (PIL, RGBA)."""
    from PIL import Image

    im = Image.open(src).convert("RGBA")
    px = im.load()
    amin = spec.get("alpha_min", 0)
    dark = spec.get("dark_max", 0)
    stretch = spec.get("stretch", 1.0)
    rules = spec.get("rules") or []
    lo, hi = 0.0, 1.0
    if spec.get("normalize"):
        lums = sorted(
            (0.299 * r + 0.587 * g + 0.114 * b) / 255
            for r, g, b, a in im.getdata()
            if a >= max(amin, 1) and max(r, g, b) / 255 >= dark
        )
        if lums:
            p_lo, p_hi = spec["normalize"]
            lo = lums[int(p_lo / 100 * (len(lums) - 1))]
            hi = lums[int(p_hi / 100 * (len(lums) - 1))]
            if hi <= lo:
                lo, hi = 0.0, 1.0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < amin or a == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if v < dark:
                continue
            for rule in rules:
                if not _matches(rule, h, s, v):
                    continue
                if rule.get("keep"):
                    pass
                elif "color" in rule:
                    px[x, y] = (*rule["color"], a)
                elif "ramp" in rule:
                    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                    lum = max(0.0, (lum - lo) / (hi - lo))
                    px[x, y] = (*_ramp_at(rule["ramp"], min(1.0, lum * stretch)), a)
                break
    return im


def make_recolors(source_roots: dict[str, Path]) -> None:
    """Write every recipe's image that is missing or older than its recipe
    file or its source."""
    made = 0
    for name, spec in recipes().items():
        tok = spec.get("from") or ""
        src = source_roots.get(tok[:1], Path("/nonexistent")) / tok[2:]
        dst = OUT_ROOT / name
        if not src.is_file():
            continue
        newest = max(src.stat().st_mtime, RECOLORS_FILE.stat().st_mtime)
        if dst.is_file() and dst.stat().st_mtime >= newest:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        recolor(src, spec).save(dst)
        made += 1
    if made:
        print(f"  tokens: {made} recolour(s) made")
