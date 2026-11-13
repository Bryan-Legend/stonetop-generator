"""The publisher's site and the official playkit PDFs, linked.

The books send readers to "the playkit at www.lampblackandbrimstone.com"
for print-ready playbooks, inserts and handouts. On every page, in every
language, ``add_playkit``:

* links each bare ``lampblackandbrimstone.com`` to the publisher's Stonetop
  page, and the first "Lampblack & Brimstone" to the site;
* links the first mention of the Setting Overview and the Moves & Gear
  handout to its PDF — in a translation, under the name that language gives
  it, read off its getting-started translation (the book sets both names in
  bold there, so the bold runs line up);
* appends a "Playkit PDFs" section: the whole list on ``playbooks-inserts``
  and ``getting-started`` (before "Review the setting"), a class's three printings on its playbook, the
  steading playbook's two, and the inserts file on each insert.

The URLs (``links/playkit.json``) are files in the Dropbox folder Lampblack
& Brimstone shares; each file has its own link token. The words come from
``i18n/ui/<code>.json`` → ``sheet.playkit`` through ``UI()``, the class
names from the page titles of the language being rendered.
"""

from __future__ import annotations

import html
import json
import re

from . import REPO_ROOT

SITE_URL = "https://www.lampblackandbrimstone.com/"
STONETOP_URL = "https://www.lampblackandbrimstone.com/stonetop"
_SITE_RE = re.compile(r"(?<![A-Za-z0-9./@-])((?:www\.)?lampblackandbrimstone\.com)(?![A-Za-z0-9/-])", re.I)
_NAME_RE = re.compile(r"Lampblack (?:&amp;|&|and) Brimstone")
_UNSPACED_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")  # kana, CJK, hangul
FULL_LIST = ("playbooks-inserts", "getting-started")
# Where a page wants its section, when not at the end: before this heading
# (Getting Started: right after the list of materials to print).
PLACE_BEFORE = {"getting-started": "review-the-setting"}

_data: dict | None = None
_terms: dict[str, dict[str, str]] = {}


def playkit() -> dict:
    global _data
    if _data is None:
        path = REPO_ROOT / "links" / "playkit.json"
        _data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return _data


def _inside(body: str, pos: int) -> bool:
    """True when ``pos`` is inside a link, a heading, or a tag's attributes."""
    opened = body.rfind("<a ", 0, pos)
    if opened >= 0 and body.rfind("</a>", 0, pos) < opened:
        return True
    for h in ("h1", "h2", "h3", "h4"):
        opened = body.rfind("<" + h, 0, pos)
        if opened >= 0 and body.rfind("</" + h + ">", 0, pos) < opened:
            return True
    return body.rfind("<", 0, pos) > body.rfind(">", 0, pos)


def _link(url: str, text: str, title: str) -> str:
    return (
        f'<a class="ref-link" href="{html.escape(url, quote=True)}" target="_blank"'
        f' rel="noopener" title="{html.escape(title, quote=True)}">{text}</a>'
    )


def _wrap(body: str, rx: re.Pattern, url: str, title: str, first_only: bool) -> str:
    out, last = [], 0
    for m in rx.finditer(body):
        if _inside(body, m.start()):
            continue
        out.append(body[last:m.start()])
        out.append(_link(url, m.group(0), title))
        last = m.end()
        if first_only:
            break
    if not out:
        return body
    out.append(body[last:])
    return "".join(out)


def handout_terms(code: str | None) -> dict[str, str]:
    """``{handout key: its name in the language}`` — English for ``None``."""
    names = playkit().get("handout_names") or {}
    if not code:
        return dict(names)
    if code in _terms:
        return _terms[code]
    got: dict[str, str] = {}
    def body(path):
        return [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    en_p = REPO_ROOT / "extracted" / "book1" / "getting-started.txt"
    tr_p = REPO_ROOT / "i18n" / "corpus" / code / "book1" / "getting-started.txt"
    if en_p.is_file() and tr_p.is_file():
        en, tr = body(en_p), body(tr_p)
        bold = lambda l: re.findall(r"<b>(.*?)</b>", l)
        if len(en) == len(tr):
            for key, name in names.items():
                for i, line in enumerate(en):
                    runs = bold(line)
                    if name in runs:
                        tr_runs = bold(tr[i])
                        if len(tr_runs) == len(runs):
                            got[key] = tr_runs[runs.index(name)].strip(" «»\"“”„「」")
                        break
    _terms[code] = got
    return got


def _term_re(term: str) -> re.Pattern:
    esc = re.escape(html.escape(term, quote=False))
    if _UNSPACED_RE.search(term):
        return re.compile(esc)
    return re.compile(r"(?<!\w)" + esc + r"(?!\w)", re.I)


def link_mentions(body: str, code: str | None = None) -> str:
    """The site, the publisher's name and the handouts' names, linked."""
    body = _wrap(body, _SITE_RE, STONETOP_URL, "Lampblack & Brimstone", False)
    body = _wrap(body, _NAME_RE, SITE_URL, "Lampblack & Brimstone", True)
    urls = playkit().get("handouts") or {}
    english = handout_terms(None)
    for key, term in handout_terms(code).items():
        if key not in urls:
            continue
        before = body
        for t in dict.fromkeys([term, english.get(key, term)]):
            body = _wrap(body, _term_re(t), urls[key], "Dropbox (PDF)", True)
            if body != before:
                break
    return body


def _ui(word: str, default: str) -> str:
    from .structure import UI
    return UI("playkit/" + word, default)


def _title(slug: str) -> str:
    """The page's title in the language being rendered, else English."""
    from . import structure
    return structure._TITLES.get(slug) or (playkit().get("titles") or {}).get(slug) or slug


def _a(url: str, label: str) -> str:  # a PDF in the list
    return (
        f'<a class="ref-link playkit-pdf" href="{html.escape(url, quote=True)}"'
        f' target="_blank" rel="noopener" title="Dropbox (PDF)">{html.escape(label)}</a>'
    )


def _formats(urls: dict) -> str:
    names = {
        "spreads": _ui("spreads", "spreads"),
        "booklet": _ui("booklet", "booklet"),
        "1-up": _ui("1up", "1-up"),
        "3-up": _ui("3up", "3-up"),
    }
    return " · ".join(_a(url, names.get(k, k)) for k, url in urls.items())


def _li(label: str, inner: str) -> str:
    return f"<li><strong>{html.escape(label)}</strong>: {inner}</li>"


def playkit_html(slug: str, code: str | None = None) -> str:
    """The "PDFs" section for ``slug``, or ``""`` when it prints none."""
    d = playkit()
    if not d:
        return ""
    playbooks = d.get("playbooks") or {}
    items: list[str] = []
    if slug in FULL_LIST:
        items.append(f"<li>{_a(d['all'], _ui('all', 'All nine character playbooks'))}</li>")
        for pb, urls in playbooks.items():
            items.append(_li(_title(pb), _formats(urls)))
        items.append(f"<li>{_a(d['inserts'], _ui('inserts', 'Playbook inserts'))}</li>")
        items.append(_li(_ui("gm", "GM playbook"), _formats(d["gm"])))
        items.append(_li(_title("steading-playbook"), _formats(d["steading-playbook"])))
        names = {**handout_terms(None), **handout_terms(code)}
        hand = d.get("handouts") or {}
        for key in ("setting-overview", "moves-gear"):
            if key in hand:
                items.append(f"<li>{_a(hand[key], names.get(key, key))}</li>")
        if "arcana" in hand:
            items.append(f"<li>{_a(hand['arcana'], _ui('arcana', 'Arcana cards'))}</li>")
        items.append(f"<li>{_a(d['printing'], _ui('printing', 'Printing instructions'))}</li>")
        if d.get("errata"):
            items.append(f"<li>{_a(d['errata'], _ui('errata', 'Errata'))}</li>")
    elif slug in playbooks:
        items.append(_li(_title(slug), _formats(playbooks[slug])))
        items.append(f"<li>{_a(d['inserts'], _ui('inserts', 'Playbook inserts'))}</li>")
        items.append(f"<li>{_a(d['printing'], _ui('printing', 'Printing instructions'))}</li>")
    elif slug == "steading-playbook":
        items.append(_li(_title(slug), _formats(d[slug])))
        items.append(f"<li>{_a(d['printing'], _ui('printing', 'Printing instructions'))}</li>")
    elif slug in (d.get("insert_pages") or ()):
        items.append(f"<li>{_a(d['inserts'], _ui('inserts', 'Playbook inserts'))}</li>")
        items.append(f"<li>{_a(d['printing'], _ui('printing', 'Printing instructions'))}</li>")
    else:
        return ""
    folder = _a(d["folder"], _ui("folder", "the whole playkit folder"))
    return (
        '<section class="playkit">'
        f'<h2 id="playkit-pdfs">{html.escape(_ui("heading", "Playkit PDFs"))}</h2>'
        f'<ul class="bullets">{"".join(items)}</ul>'
        f"<p>{html.escape(_ui('browse', 'Or browse {folder}.')).replace('{folder}', folder)}</p>"
        "</section>"
    )


def add_playkit(body: str, slug: str, code: str | None = None) -> str:
    """``body`` with the site, the publisher and the handouts linked, and
    the page's PDFs added — at the end, or before the heading
    ``PLACE_BEFORE`` names."""
    body = link_mentions(body, code)
    section = playkit_html(slug, code)
    if not section:
        return body
    anchor = PLACE_BEFORE.get(slug)
    if anchor:
        m = re.search(r'<h[1-6][^>]*\bid="' + re.escape(anchor) + '"', body)
        if m:
            return body[:m.start()] + section + "\n" + body[m.start():]
    return body + section
