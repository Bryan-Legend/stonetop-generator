"""Preview cards (Open Graph / search thumbnails) and the favicons.

Every page gets two images, drawn here from the page the build has just
written, never from artwork (the books' illustrations are © Lucie Arnoux and
are not published):

* ``cards/<code>/<slug>.png`` — 1200×630, the link preview Discord,
  Slack, Reddit and Facebook show, and Google's 16:9. A wine band carrying
  the standing stone and the edition's name, then the book and section, the
  page's title and its opening paragraphs, cut with "…" where they run out
  of room. Text is never shrunk to fit; titles are.
* ``cards/<code>/<slug>-square.png`` — 800×800, Google's 1:1. Search
  shows it at ~104px beside a result, so it carries the title alone, large.

Rendering every page in every language takes a while and the images change
only when a page's title or opening text does, so this runs under
``--cards`` only. ``cards/manifest.json`` records a hash of each
card's inputs, so a run redraws only what moved. A build without
``--cards`` still points every page at its cards when they exist
(``card_urls``), and falls back to the favicon when they do not.

Size matters here: ~3,900 pages × 2 images go into the repo and onto GitHub
Pages (1 GB cap), so the images are 48-colour PNGs (``PALETTE``) — text is
indistinguishable from full colour, and the band's gradient shows steps only
up close — squeezed by oxipng when it is installed (``pip install
pyoxipng``): ~57 KB a page for the pair, ~210 MB for the site.

Fonts: the wiki's own (``site/css/fonts``) for Latin and Cyrillic; the
system's for Japanese, Korean and Chinese (Yu Gothic, Malgun Gothic,
Microsoft YaHei / JhengHei on Windows, Noto Sans CJK elsewhere). A language
whose font is missing gets no cards, and says so.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from . import REPO_ROOT

# Bump when the design changes: every card is redrawn.
DESIGN_VERSION = 3

CARDS_DIR = "cards"
MANIFEST = "manifest.json"
WIDE = (1200, 630)
SQUARE = (800, 800)
SS = 2  # supersampling
# Colours per card. 16 bands the wine gradient into three stripes, 32 into
# six; 48 leaves steps only up close, at ~57 KB a page (64: ~63 KB).
PALETTE = 48

BG_PAGE = (16, 14, 14)
HEAD = (207, 190, 162)
BODY = (186, 170, 152)
MUTED = (159, 132, 117)
ANSWER = (196, 103, 127)
WINE = (93, 20, 43)
WINE_DEEP = (65, 13, 30)
# The favicon's wine is a touch brighter than the band's, to hold at 16px.
FAV_WINE = (110, 20, 44)
FAV_STONE = (244, 232, 210)

_STATE: dict = {"out": None, "enabled": False, "existing": None}


# ------------------------------------------------------------------ paths

def configure(out: Path, enabled: bool) -> None:
    """Called once per build (and per render worker) before any page."""
    _STATE["out"] = Path(out)
    _STATE["enabled"] = bool(enabled)
    _STATE["existing"] = None


def _existing() -> set[str]:
    if _STATE["existing"] is None:
        found: set[str] = set()
        root = _STATE["out"] / CARDS_DIR if _STATE["out"] else None
        if root and root.is_dir():
            for p in root.rglob("*.png"):
                found.add(p.relative_to(_STATE["out"]).as_posix())
        _STATE["existing"] = found
    return _STATE["existing"]


def page_key(path: str) -> tuple[str, str]:
    """(language code, slug) of a page from its path off the wiki root."""
    path = path.strip("/")
    code, _, rest = path.rpartition("/")
    slug = rest[:-5] if rest.endswith(".html") else rest
    return code or "en", slug or "index"


def card_files(code: str, slug: str) -> dict[str, str]:
    base = f"{CARDS_DIR}/{code}/{slug}"
    return {"wide": base + ".png", "square": base + "-square.png"}


def card_urls(path: str, base_url: str) -> dict[str, str] | None:
    """Absolute URLs of a page's cards, or None when it has none (yet).

    Under ``--cards`` every page that can be drawn will be, after the pages
    are written; otherwise only what is already on disk counts.
    """
    if _STATE["out"] is None:
        return None
    code, slug = page_key(path)
    files = card_files(code, slug)
    if _STATE["enabled"]:
        if not language_ready(code):
            return None
    elif not all(f in _existing() for f in files.values()):
        return None
    base = base_url.rstrip("/")
    return {k: f"{base}/{v}" for k, v in files.items()}


# ------------------------------------------------------------------ fonts

_WIN_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
_NOTO = [Path("/usr/share/fonts/opentype/noto"), Path("/usr/share/fonts/noto-cjk")]
# (bold, regular) candidates per CJK language; Noto's collection index per
# region (JP 0, KR 1, SC 2, TC 3).
_CJK = {
    "ja": ([("YuGothB.ttc", 0), ("meiryob.ttc", 0)], [("YuGothM.ttc", 0), ("meiryo.ttc", 0)], 0),
    "ko": ([("malgunbd.ttf", 0)], [("malgun.ttf", 0)], 1),
    "zh-Hans": ([("msyhbd.ttc", 0)], [("msyh.ttc", 0)], 2),
    "zh-Hant": ([("msjhbd.ttc", 0)], [("msjh.ttc", 0)], 3),
}
_SYMBOL = [("seguisym.ttf", 0)]
_FONT_CACHE: dict = {}


def _font_dir() -> Path:
    out = _STATE["out"] or (REPO_ROOT / "site")
    return Path(out) / "css" / "fonts"


def _find(cands: list[tuple[str, int]]) -> tuple[Path, int] | None:
    for name, idx in cands:
        p = _WIN_FONTS / name
        if p.is_file():
            return p, idx
    return None


def _cjk_font(code: str, bold: bool) -> tuple[Path, int] | None:
    if code not in _CJK:
        return None
    b, r, noto_idx = _CJK[code]
    hit = _find(b if bold else r)
    if hit:
        return hit
    for d in _NOTO:
        p = d / ("NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc")
        if p.is_file():
            return p, noto_idx
    return None


def language_ready(code: str) -> bool:
    return code not in _CJK or (
        _cjk_font(code, True) is not None and _cjk_font(code, False) is not None
    )


class _Face:
    """One font at one size, with the set of characters it can draw."""

    def __init__(self, path: Path, size: int, index: int = 0, wght: int | None = None):
        from PIL import ImageFont

        self.font = ImageFont.truetype(str(path), size * SS, index=index)
        if wght is not None:
            try:
                self.font.set_variation_by_axes([wght])
            except Exception:  # pragma: no cover - not a variable font
                pass
        key = (str(path), index)
        if key not in _FONT_CACHE:
            from fontTools.ttLib import TTFont

            tt = TTFont(str(path), fontNumber=index, lazy=True)
            _FONT_CACHE[key] = set(tt.getBestCmap() or {})
        self.cmap = _FONT_CACHE[key]


class Chain:
    """A font with fallbacks: each character is drawn in the first face that
    has it (Awery has no em dash; nothing Latin has kana)."""

    def __init__(self, faces: list[_Face]):
        self.faces = faces

    def runs(self, s: str) -> list[tuple[_Face, str]]:
        out: list[tuple[_Face, str]] = []
        for ch in s:
            face = next((f for f in self.faces if ord(ch) in f.cmap), None)
            if face is None:
                if ch.isspace():
                    face = self.faces[0]
                else:
                    continue  # a glyph nobody has: leave it out, not a box
            if out and out[-1][0] is face:
                out[-1] = (face, out[-1][1] + ch)
            else:
                out.append((face, ch))
        return out

    def width(self, s: str) -> float:
        return sum(f.font.getlength(t) for f, t in self.runs(s)) / SS

    def draw(self, d, x: float, baseline: float, s: str, fill) -> None:
        cx = x * SS
        for f, t in self.runs(s):
            d.text((cx, baseline * SS), t, font=f.font, fill=fill, anchor="ls")
            cx += f.font.getlength(t)


def _chain(code: str, kind: str, size: int) -> Chain:
    key = (code, kind, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    fd = _font_dir()
    faces: list[_Face] = []
    if kind == "title":
        faces.append(_Face(fd / "awery-smallcaps.woff2", size))
        faces.append(_Face(fd / "vollkorn-variable.woff2", size, wght=600))
    elif kind == "body":
        faces.append(_Face(fd / "vollkorn-variable.woff2", size, wght=400))
    else:  # label
        faces.append(_Face(fd / "source-sans-3-latin-600-normal.woff2", size))
        faces.append(_Face(fd / "vollkorn-variable.woff2", size, wght=600))
    cjk = _cjk_font(code, kind != "body")
    if cjk:
        faces.append(_Face(cjk[0], size, index=cjk[1]))
    sym = _find(_SYMBOL)
    if sym:
        faces.append(_Face(sym[0], size, index=sym[1]))
    ch = Chain(faces)
    _FONT_CACHE[key] = ch
    return ch


# --------------------------------------------------------------- wrapping

def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x3000 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF
        or 0xFF00 <= o <= 0xFFEF or 0x1100 <= o <= 0x11FF
    )


# Never at the start of a line / never at the end of one.
_NO_START = set("、。，．・：；？！）」』】〕》〉ー々ぁぃぅぇぉっゃゅょァィゥェォッャュョ,.;:!?)]}…%")
_NO_END = set("（「『【〔《〈([{")


def _breaks(s: str) -> list[int]:
    """Indices a line may break at: after a space, or between CJK letters."""
    out = []
    for i in range(1, len(s)):
        a, b = s[i - 1], s[i]
        if a == " ":
            out.append(i)
        elif a == "-" and i > 1 and s[i - 2].isalpha() and b.isalpha():
            out.append(i)  # after a compound's hyphen: "Dunkelwandler-" / "Umhang"
        elif (_is_cjk(a) or _is_cjk(b)) and not a.isspace() and not b.isspace():
            if b not in _NO_START and a not in _NO_END:
                out.append(i)
    out.append(len(s))
    return out


def wrap(s: str, chain: Chain, width: float) -> list[str]:
    s = " ".join(s.split())
    lines: list[str] = []
    start = 0
    while start < len(s):
        last_fit = None
        for b in _breaks(s[start:]):
            seg = s[start:start + b].strip()
            if chain.width(seg) <= width:
                last_fit = b
            else:
                break
        if last_fit is None:  # one word wider than the line: let it overflow
            last_fit = next(iter(_breaks(s[start:])))
        lines.append(s[start:start + last_fit].strip())
        start += last_fit
        while start < len(s) and s[start] == " ":
            start += 1
    return lines


def _ellipsize(line: str, chain: Chain, width: float) -> str:
    line = line.rstrip(" .,;:、。，")
    while line and chain.width(line + "…") > width:
        cut = _breaks(line)
        cut = [c for c in cut if c < len(line)]
        line = line[: cut[-1]].rstrip(" .,;:、。，") if cut else line[:-1]
    return line + "…"


def fit_title(code: str, title: str, width: float, max_lines: int, sizes) -> tuple[Chain, int, list[str]]:
    """The largest size at which the title fits ``max_lines``. A single word
    wider than the line ("Acknowledgements" on the square card) keeps
    shrinking past the listed sizes, down to half the smallest; only then is
    what does not fit cut with "…"."""
    sizes = list(sizes)
    floor = sizes[-1] // 2
    while sizes[-1] * 0.92 >= floor:
        sizes.append(int(sizes[-1] * 0.92))
    for sz in sizes:
        ch = _chain(code, "title", sz)
        lines = wrap(title, ch, width)
        if len(lines) <= max_lines and all(ch.width(l) <= width for l in lines):
            return ch, sz, lines
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(lines[-1], ch, width)
    lines = [l if ch.width(l) <= width else _ellipsize(l, ch, width) for l in lines]
    return ch, sz, lines


# ------------------------------------------------------------------ stone

# The standing stone from images/favicon.svg, in its own 32-unit box.
_MENHIR = [(5.6, 2.2), (10.6, 3.4), (12.6, 31.6), (8.2, 34.2), (3.4, 31.4), (4.6, 7.2)]


def menhir(x: float, y: float, h: float) -> list[tuple[float, float]]:
    pts = [(3.92 + 1.51 * px, -0.489 + 0.906 * py) for px, py in _MENHIR]
    minx = min(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    k = h / (max(p[1] for p in pts) - miny)
    return [((px - minx) * k + x, (py - miny) * k + y) for px, py in pts]


def menhir_width(h: float) -> float:
    return max(p[0] for p in menhir(0, 0, h))


# ------------------------------------------------------------------ cards

def _canvas(w: int, h: int, band: int):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (w * SS, h * SS), BG_PAGE)
    d = ImageDraw.Draw(img)
    for i in range(band * SS):
        t = i / (band * SS)
        d.line([(i, 0), (i, h * SS)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(WINE, WINE_DEEP)))
    return img, d


def _stone(d, band: int, top: float, h: float) -> None:
    d.polygon([(px * SS, py * SS) for px, py in menhir((band - menhir_width(h)) / 2, top, h)],
              fill=HEAD)


def _band_label(d, code: str, lines: list[str], band: int, y: float) -> None:
    """The edition's name under the stone: the game's name, then the rest
    smaller, each shrunk to fit the band."""
    for i, (s, size) in enumerate(zip(lines, (46, 32))):
        while size > 14:
            ch = _chain(code, "title", size)
            if ch.width(s) <= band - 36:
                break
            size -= 2
        ch.draw(d, (band - ch.width(s)) / 2, y + size * 0.8, s, HEAD)
        y += size * 1.15


def _encode(img, size: tuple[int, int]) -> bytes:
    from PIL import Image

    img = img.resize(size, Image.LANCZOS)
    q = img.quantize(PALETTE, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    b = io.BytesIO()
    q.save(b, "PNG", optimize=True)
    data = b.getvalue()
    try:
        import oxipng

        data = oxipng.optimize_from_memory(data, level=4)
    except ImportError:
        pass
    return data


def draw_wide(job: dict) -> bytes:
    code = job["code"]
    w, h = WIDE
    band = 300
    img, d = _canvas(w, h, band)
    mh = 330
    label_h = 92 if len(job["band"]) > 1 else 50
    top = (h - mh - label_h - 40) / 2
    _stone(d, band, top, mh)
    _band_label(d, code, job["band"], band, top + mh + 40)

    margin = 64
    x = band + margin
    tw = w - x - margin
    y = margin + 6
    if job["kicker"]:
        lab = _chain(code, "label", 22)
        lab.draw(d, x, y + 18, _ellipsize_fit(job["kicker"].upper(), lab, tw), ANSWER)
    ch, sz, lines = fit_title(code, job["title"], tw, 3, (80, 72, 64, 58, 52, 46))
    y = margin + 46
    for ln in lines:
        ch.draw(d, x, y + sz * 0.8, ln, HEAD)
        y += sz * 1.06
    y += 24

    cjk = code in _CJK
    size = 29 if cjk else 31
    body = _chain(code, "body", size)
    lead = size * (1.6 if cjk else 1.42)
    gap = lead * 0.45
    bottom = h - margin + 6
    paras = job["paras"]
    done = False
    for pi, p in enumerate(paras):
        plines = wrap(p, body, tw)
        for li, ln in enumerate(plines):
            more = li < len(plines) - 1 or pi < len(paras) - 1
            if y + lead * 2 > bottom and more:
                body.draw(d, x, y + size, _ellipsize(ln, body, tw), BODY)
                done = True
                break
            body.draw(d, x, y + size, ln, BODY)
            y += lead
        if done:
            break
        y += gap
        if y + lead > bottom:
            break
    return _encode(img, WIDE)


def _ellipsize_fit(s: str, chain: Chain, width: float) -> str:
    return s if chain.width(s) <= width else _ellipsize(s, chain, width)


def draw_square(job: dict) -> bytes:
    code = job["code"]
    n = 1200  # drawn at the wide card's scale, saved at SQUARE
    band = 230
    img, d = _canvas(n, n, band)
    mh = min(520, 520 * (band - 70) / menhir_width(520))
    _stone(d, band, (n - mh) / 2, mh)
    x, m = band + 70, 70
    tw = n - x - m
    ch, sz, lines = fit_title(code, job["title"], tw, 4, (230, 200, 176, 156, 140, 124, 110))
    lead = sz * 1.02
    y = (n - lead * len(lines)) / 2 - 10
    if job["kicker"]:
        lab = _chain(code, "label", 40)
        lab.draw(d, x, y - 40, _ellipsize_fit(job["kicker"].upper(), lab, tw), ANSWER)
    for ln in lines:
        ch.draw(d, x, y + sz * 0.8, ln, HEAD)
        y += lead
    ed = _chain(code, "title", 48)
    ed.draw(d, x, n - m - 2, _ellipsize_fit(job["edition"], ed, tw), MUTED)
    return _encode(img, SQUARE)


def render_job(job: dict) -> tuple[str, dict[str, bytes]]:
    return job["key"], {"wide": draw_wide(job), "square": draw_square(job)}


# ------------------------------------------------- reading the built pages

_SKIP_CLASSES = {
    "arcana-back", "arcana-tags", "arcana-title-line", "be-note", "card-title",
    "card-excerpt", "stat-block", "index-card", "index-grid", "pb-stats",
    "page-feedback", "be-letters", "infobox", "roll-table", "value-table",
}
_SKIP_TAGS = {"table", "nav", "figure", "script", "style", "aside", "header", "footer", "ul", "ol"}
_VOID = {"br", "img", "input", "hr", "meta", "link", "wbr", "source", "col", "area"}


class _Paras(HTMLParser):
    """The page's opening paragraphs: <p> text in <main>, up to the first
    heading after one has been read, outside lists, tables and stat blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[bool] = []  # per open element: inside a skipped one?
        self.paras: list[str] = []
        self.cur: list[str] | None = None
        self.stop = False

    def _skipped(self) -> bool:
        return bool(self.stack) and self.stack[-1]

    def handle_starttag(self, tag, attrs):
        if self.stop:
            return
        if tag in ("h2", "h3") and self.paras and not self._skipped():
            classes = set((dict(attrs).get("class") or "").split())
            if not classes & _SKIP_CLASSES:
                self.stop = True
                return
        if tag in _VOID:
            return
        classes = set((dict(attrs).get("class") or "").split())
        skip = self._skipped() or tag in _SKIP_TAGS or bool(classes & _SKIP_CLASSES)
        self.stack.append(skip)
        if tag == "p" and not skip:
            self.cur = []

    def handle_endtag(self, tag):
        if self.stop or tag in _VOID:
            return
        if tag == "p" and self.cur is not None:
            text = " ".join("".join(self.cur).split())
            if len(text) > 1:
                self.paras.append(text)
            self.cur = None
            if sum(len(p) for p in self.paras) > 1400:
                self.stop = True
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.cur is not None and not self._skipped():
            self.cur.append(data)


def opening_paragraphs(page_html: str) -> list[str]:
    i = page_html.find("<main")
    j = page_html.find("</main>", i)
    if i < 0:
        return []
    p = _Paras()
    p.feed(page_html[i: j if j > 0 else None])
    # A paragraph that introduces a list the card does not show ("…can
    # suffer:") is left out.
    return [t for t in p.paras if not t.rstrip().endswith((":", "："))]


_JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _jsonld(page_html: str) -> list[dict]:
    m = _JSONLD_RE.search(page_html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return []
    return data.get("@graph", [data]) if isinstance(data, dict) else []


def _ui(code: str) -> dict:
    if code == "en":
        return {}
    try:
        return json.loads((REPO_ROOT / "i18n" / "ui" / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def band_lines(edition: str, game: str) -> list[str]:
    """"Stonetop Web Edition" → ["Stonetop", "Web Edition"]; "石顶网页版" →
    ["石顶", "网页版"]. The game's name leads, the rest goes under it."""
    if game and edition.startswith(game):
        rest = edition[len(game):].strip(" ,-・·、")
        if rest:
            if not _is_cjk(rest[0]):
                rest = rest[0].upper() + rest[1:]
            return [game, rest]
    return [edition]


def job_for(path: Path, out: Path, ui_cache: dict) -> dict | None:
    rel = path.relative_to(out).as_posix()
    code, slug = page_key(rel)
    text = path.read_text(encoding="utf-8")
    if '<main class="content' not in text:
        return None
    graph = _jsonld(text)
    page = next((g for g in graph if g.get("@type") in ("Article", "CollectionPage")), None)
    if not page:
        return None
    title = page.get("headline") or page.get("name") or ""
    if code not in ui_cache:
        ui_cache[code] = _ui(code)
    ui = ui_cache[code]
    from .articles import BOOKS

    book_labels = {b["id"]: b["label"] for b in BOOKS}
    book_labels.update(ui.get("books") or {})
    kicker = []
    parts = page.get("isPartOf")
    if isinstance(parts, list) and parts:
        book = (parts[0].get("@id") or "").rpartition("#")[2]
        if book in book_labels:
            kicker.append(book_labels[book])
    crumbs = next((g for g in graph if g.get("@type") == "BreadcrumbList"), None)
    items = (crumbs or {}).get("itemListElement") or []
    if len(items) == 3:
        hub = items[1].get("name") or ""
        if hub and hub not in kicker:
            kicker.append(hub)
    from .chrome import EDITION_NAME, SITE_NAME

    edition = ui.get("edition") or EDITION_NAME
    game = SITE_NAME
    bt = (ui.get("book_titles") or {}).get("book1") or ""
    if " — " in bt:
        game = bt.split(" — ", 1)[1]
    return {
        "key": f"{code}/{slug}",
        "code": code,
        "slug": slug,
        "title": html.unescape(title),
        "kicker": " · ".join(kicker),
        "paras": opening_paragraphs(text),
        "band": band_lines(edition, game),
        "edition": edition,
    }


def _digest(job: dict) -> str:
    keep = {k: job[k] for k in ("title", "kicker", "paras", "band", "edition")}
    keep["v"] = DESIGN_VERSION
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def all_languages() -> list[str]:
    """Every translation in i18n/langs.json — the cards of a language a
    --langs run left out are kept, not swept."""
    data = json.loads((REPO_ROOT / "i18n" / "langs.json").read_text(encoding="utf-8"))
    return [t["code"] for t in data.get("targets", [])]


def build_cards(out: Path, codes: list[str], jobs_n: int = 1) -> None:
    """Draw every page's cards that changed since the last ``--cards`` run,
    and delete the cards of pages that are gone."""
    out = Path(out)
    root = out / CARDS_DIR
    mpath = root / MANIFEST
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    ui_cache: dict = {}
    jobs: list[dict] = []
    skipped_langs = []
    for code in ["en", *codes]:
        if not language_ready(code):
            skipped_langs.append(code)
            continue
        folder = out if code == "en" else out / code
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.html")):
            job = job_for(p, out, ui_cache)
            if job:
                jobs.append(job)
    if skipped_langs:
        print(f"  cards: no font for {', '.join(skipped_langs)} — those pages keep the favicon")

    todo = []
    for job in jobs:
        files = card_files(job["code"], job["slug"])
        job["digest"] = _digest(job)
        if manifest.get(job["key"]) == job["digest"] and all((out / f).is_file() for f in files.values()):
            continue
        todo.append(job)

    if todo:
        print(f"  cards: drawing {len(todo)} of {len(jobs)} pages…")
        if jobs_n > 1 and len(todo) > 8:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(jobs_n, initializer=configure, initargs=(out, True)) as ex:
                results = ex.map(render_job, todo, chunksize=8)
                _store(out, todo, results, manifest)
        else:
            _store(out, todo, map(render_job, todo), manifest)
    else:
        print(f"  cards: all {len(jobs)} pages up to date")

    keep = {job["key"] for job in jobs}
    keep_files = {f for job in jobs for f in card_files(job["code"], job["slug"]).values()}
    gone = 0
    if root.is_dir():
        for p in root.rglob("*.png"):
            if p.relative_to(out).as_posix() not in keep_files:
                p.unlink()
                gone += 1
    if gone:
        print(f"  cards: removed {gone} for pages that are gone")
    manifest = {k: v for k, v in sorted(manifest.items()) if k in keep}
    root.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    _STATE["existing"] = None
    write_favicons(out)


def _store(out: Path, todo: list[dict], results, manifest: dict) -> None:
    by_key = {j["key"]: j for j in todo}
    for key, images in results:
        job = by_key[key]
        files = card_files(job["code"], job["slug"])
        for kind, data in images.items():
            p = out / files[kind]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        manifest[key] = job["digest"]


# --------------------------------------------------------------- favicons

def _favicon(n: int, *, rounded: bool = True):
    """The wine tile with the cream stone. Google crops a favicon to a circle,
    so the stone is sized to stay inside the inscribed one (85% tall); the
    rounded corners only show in a browser tab."""
    from PIL import Image, ImageDraw

    m = n * 4
    img = Image.new("RGBA", (m, m), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, m - 1, m - 1], radius=m * 0.22, fill=FAV_WINE)
    else:
        d.rectangle([0, 0, m - 1, m - 1], fill=FAV_WINE)
    h = m * 0.85
    w = menhir_width(h)
    d.polygon(menhir((m - w) / 2, (m - h) / 2, h), fill=FAV_STONE)
    return img.resize((n, n), Image.LANCZOS)


def favicon_svg() -> str:
    h = 32 * 0.85
    pts = menhir(0, 0, h)
    w = max(p[0] for p in pts)
    path = " ".join(f"{x + (32 - w) / 2:.2f} {y + (32 - h) / 2:.2f}" for x, y in pts)
    hexs = lambda c: "#%02x%02x%02x" % c
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" '
        'role="img" aria-label="Stonetop Web Edition">\n'
        "  <title>Stonetop Web Edition</title>\n"
        "  <!-- Generated by generator/cards.py (write_favicons) — edit it there.\n"
        "       The stone is the same silhouette as .site-title::before in css/wiki.css. -->\n"
        f'  <rect width="32" height="32" rx="7" fill="{hexs(FAV_WINE)}"/>\n'
        f'  <path fill="{hexs(FAV_STONE)}" d="M{path}z"/>\n'
        "</svg>\n"
    )


def _write_if_changed(p: Path, data: bytes) -> None:
    try:
        if p.read_bytes() == data:
            return
    except OSError:
        pass
    p.write_bytes(data)


def write_favicons(out: Path) -> None:
    """favicon.svg/.png/.ico, the 192px icon, the Apple touch icon, and a
    copy of the .ico at the root, where crawlers look first."""
    out = Path(out)
    img_dir = out / "images"

    def png(im) -> bytes:
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        return b.getvalue()

    _write_if_changed(img_dir / "favicon.svg", favicon_svg().encode("utf-8"))
    _write_if_changed(img_dir / "favicon.png", png(_favicon(512)))
    _write_if_changed(img_dir / "favicon-192.png", png(_favicon(192)))
    # iOS rounds the corners itself and wants no transparency.
    _write_if_changed(img_dir / "apple-touch-icon.png", png(_favicon(180, rounded=False).convert("RGB")))
    b = io.BytesIO()
    _favicon(256).save(b, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    _write_if_changed(img_dir / "favicon.ico", b.getvalue())
    _write_if_changed(out / "favicon.ico", b.getvalue())
