"""``tokens.json`` — the 2 Minute Tabletop token drawn at a stat block's head.

The tokens are licensed for the wiki (2026-11-07). The source set (~1.5 GB of
PNGs under ``2 Minute Tabletop/``) is gitignored; only the tokens chosen in
``tokens.json`` reach the site, cropped to the figure and converted to WebP in
``images/tokens/``. A build without the source set keeps the images already
there, so a clone of the repo still builds the same pages.

``tokens.json``: ``{"tokens": {"<slug>#<stat-block id>": {"name", "choice",
"options"}}}``. ``choice`` is null (undecided), ``"none"``, or a list of token
ids — ``F:<Category>/<file>.png`` (Fairbanks) or ``D:…`` (Davy). Picked on
the contact sheet in Dropbox ``2MTT tokens/``.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from . import REPO_ROOT

TOKENS_FILE = REPO_ROOT / "tokens.json"
SOURCE_ROOTS = {
    "F": REPO_ROOT / "2 Minute Tabletop" / "Fairbanks - Preferred",
    "D": REPO_ROOT / "2 Minute Tabletop" / "Davy",
    # Recolours, made by the build from recolors.json (generator/recolor.py).
    "R": REPO_ROOT / "2 Minute Tabletop" / "Recolors",
}
OUT_DIR = "images/tokens"
SIZE = 400  # longest side kept: the sources are 375px, so the figure at full size
            # (shown 130 CSS px tall, so 2x+ on a sharp screen)
QUALITY = 86

_CHOICES: dict[str, list[str]] | None = None
_DIMS: dict[str, tuple[int, int]] = {}


def choices() -> dict[str, list[str]]:
    """``<slug>#<id>`` → the token ids chosen for it (only decided ones)."""
    global _CHOICES
    if _CHOICES is None:
        _CHOICES = {}
        try:
            data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for key, v in (data.get("tokens") or {}).items():
            c = v.get("choice")
            if isinstance(c, str) and c != "none":
                c = [c]
            if isinstance(c, list) and c:
                _CHOICES[key] = [t for t in c if isinstance(t, str) and ":" in t]
    return _CHOICES


def out_name(token: str) -> str:
    """``F:Humanoid/Human Rogue 6.png`` → ``f-humanoid-human-rogue-6.webp``."""
    stem = token.rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") + ".webp"


def token_html(slug: str | None, anchor: str | None, wrap: str = "stat-tokens") -> str:
    """The ``<span class="stat-tokens">`` for a stat block, or ``""``.

    ``wrap`` names the span for other places a token stands: a class's
    iconic token (``<playbook>#class``) is ``class-tokens``, at the head of
    its playbook and beside its name on Welcome to Stonetop."""
    if not slug or not anchor:
        return ""
    picked = choices().get(f"{slug}#{anchor}")
    if not picked:
        return ""
    imgs = []
    for t in picked:
        name = out_name(t)
        w, h = _dims(name)
        imgs.append(
            f'<img class="stat-token" src="{OUT_DIR}/{html.escape(name)}" alt="" '
            f'width="{w}" height="{h}" loading="lazy">'
        )
    many = " many" if len(imgs) > 1 else ""
    return f'<span class="{wrap}{many}" aria-hidden="true">{"".join(imgs)}</span>'


def _dims(name: str) -> tuple[int, int]:
    if name not in _DIMS:
        _DIMS[name] = (SIZE, SIZE)
        try:
            from PIL import Image

            with Image.open(_SITE / OUT_DIR / name) as im:
                _DIMS[name] = im.size
        except Exception:
            pass
    return _DIMS[name]


_SITE = REPO_ROOT / "site"


def configure(site: Path) -> None:
    global _SITE
    _SITE = site


def write_images(site: Path) -> None:
    """Write ``images/tokens/`` for the chosen tokens; drop the ones no longer
    chosen. A token whose source PNG is missing keeps the image it had."""
    from .recolor import make_recolors

    make_recolors(SOURCE_ROOTS)
    out = site / OUT_DIR
    wanted: dict[str, str] = {}
    for picked in choices().values():
        for t in picked:
            wanted[out_name(t)] = t
    if not wanted and not out.is_dir():
        return
    out.mkdir(parents=True, exist_ok=True)
    made = kept = 0
    missing: list[str] = []
    for name, t in sorted(wanted.items()):
        dst = out / name
        src = SOURCE_ROOTS.get(t[0], Path("/nonexistent")) / t[2:]
        if not src.is_file():
            if not dst.is_file():
                missing.append(t)
            continue
        if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
            kept += 1
            continue
        from PIL import Image

        with Image.open(src) as im:
            im = im.convert("RGBA")
            box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
            if box:
                im = im.crop(box)
            im.thumbnail((SIZE, SIZE), Image.LANCZOS)
            im.save(dst, "WEBP", quality=QUALITY, method=6)
        _DIMS.pop(name, None)
        made += 1
    gone = 0
    for p in out.glob("*.webp"):
        if p.name not in wanted:
            p.unlink()
            gone += 1
    print(f"  tokens: {len(wanted)} images ({made} written, {gone} removed)")
    for t in missing:
        print(f"WARNING: token source missing, no image: {t}")


def class_token_image(slug: str | None) -> str | None:
    """The first token of a class or insert (``<slug>#class``), as a path
    under ``images/`` — the page's hover-preview thumbnail."""
    picked = choices().get(f"{slug}#class") if slug else None
    return f"tokens/{out_name(picked[0])}" if picked else None


def thumb_html(slug: str, anchor: str, prefix: str = "") -> str:
    """A Bestiary tile's figure: every token chosen for the block (a group
    shows them all, overlapping), or the empty box, so the names line up."""
    picked = choices().get(f"{slug}#{anchor}")
    if not picked:
        return '<span class="be-token" aria-hidden="true"></span>'
    imgs = []
    for t in picked:
        name = out_name(t)
        w, h = _dims(name)
        imgs.append(
            f'<img src="{prefix}{OUT_DIR}/{html.escape(name)}" alt="" '
            f'width="{w}" height="{h}" loading="lazy">'
        )
    many = " many" if len(imgs) > 1 else ""
    return f'<span class="be-token{many}" aria-hidden="true">{"".join(imgs)}</span>'
