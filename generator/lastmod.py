"""
Sitemap ``<lastmod>``: the date a page's output last changed, not the build date.

A page keeps the ``<lastmod>`` it already had for as long as its HTML stays
the same; only a page whose output actually changed (or a new page) gets a new
date. Two places apply the rule, sharing this module:

* **The build** (``build.py``). Before it clears last run's pages it takes a
  :func:`snapshot` of the wiki folder: every URL in the old ``sitemap.xml``,
  with that sitemap's ``<lastmod>`` and a digest of the page's file. After the
  new pages are written, :func:`resolve` compares digests: same → the old
  date, different or new → today. Two builds with no source change therefore
  write the same ``sitemap.xml``. With no previous sitemap to go on (a fresh
  output folder), a page takes the date of the last git commit that changed
  its file, if it is committed and unmodified, else today.

* **The deploy** (``python -m generator.lastmod deploy``, run by
  ``.github/workflows/pages.yml``). The site about to be published is compared
  with the site that is live now (a checkout of stonetop.cc),
  page by page: see :func:`reconcile_with_live`. That catches anything the
  build did not see (a hand edit, a build from a clean folder) and yields the
  list of URLs that really changed, for IndexNow.

Pages are compared after :func:`normalize`, which drops what may differ
without the page changing: line endings (Windows builds write CRLF) and
trailing whitespace. The generator writes no build timestamps, cache-busting
hashes or "generated on" lines today; should one appear, add its pattern to
``VOLATILE`` so it cannot make every page look changed.

Standard library only: the deploy job runs it without installing anything.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

SITEMAP = "sitemap.xml"

# Byte patterns replaced before hashing — content that can change from build
# to build while the page does not. None exist today (the build output is
# byte-for-byte reproducible); keep this list for when one does.
VOLATILE: tuple[re.Pattern[bytes], ...] = ()

_URL_RE = re.compile(
    r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]*)</lastmod>)?", re.S
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def today() -> str:
    return datetime.date.today().isoformat()


def normalize(data: bytes) -> bytes:
    data = data.replace(b"\r\n", b"\n")
    for pat in VOLATILE:
        data = pat.sub(b"", data)
    data = re.sub(rb"[ \t]+\n", b"\n", data)
    return data.rstrip()


def digest(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(normalize(data)).hexdigest()


def loc_to_relpath(loc: str, base_url: str) -> str | None:
    """``https://site/de/x.html`` → ``de/x.html``; ``https://site/`` → ``index.html``."""
    base = base_url.rstrip("/") + "/"
    if not loc.startswith(base):
        return None
    rel = loc[len(base):].split("#", 1)[0].split("?", 1)[0]
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    if ".." in rel.split("/"):
        return None
    return rel


def read_sitemap(path: Path) -> dict[str, str]:
    """``{loc: lastmod}`` in document order; ``{}`` if there is no sitemap."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {
        html.unescape(loc.strip()): (mod or "").strip()
        for loc, mod in _URL_RE.findall(text)
    }


def render_sitemap(entries: dict[str, str]) -> str:
    rows = [
        "  <url><loc>" + html.escape(loc) + "</loc>"
        "<lastmod>" + mod + "</lastmod></url>"
        for loc, mod in entries.items()
    ]
    return "\n".join(
        ['<?xml version="1.0" encoding="UTF-8"?>']
        + ['<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        + rows
        + ["</urlset>", ""]
    )


# ------------------------------------------------------------------ build

Snapshot = dict[str, tuple[str, str | None]]


def snapshot(out: Path, base_url: str) -> Snapshot:
    """``{loc: (lastmod, digest)}`` for the wiki as it stands before a build."""
    snap: Snapshot = {}
    for loc, mod in read_sitemap(out / SITEMAP).items():
        rel = loc_to_relpath(loc, base_url)
        if rel is None or not _DATE_RE.match(mod):
            continue
        snap[loc] = (mod, digest(out / rel))
    return snap


def git_dates(out: Path) -> dict[str, str]:
    """``{relpath: YYYY-MM-DD}``: the last commit that changed each file under
    ``out``, for files committed and unmodified since. ``{}`` without git."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=out,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout

    try:
        top = Path(git("rev-parse", "--show-toplevel").strip())
        prefix = out.resolve().relative_to(top.resolve()).as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        dirty = set(git("diff", "--name-only", "HEAD", "--", ".").split("\n"))
        log = git("log", "--format=@%cs", "--name-only", "--", ".")
    except (OSError, subprocess.CalledProcessError, ValueError):
        return {}
    dates: dict[str, str] = {}
    date = ""
    for line in log.splitlines():
        if line.startswith("@"):
            date = line[1:]
        elif line and line not in dirty and line.startswith(prefix):
            dates.setdefault(line[len(prefix):], date)  # newest first
    return dates


def resolve(
    locs: list[str],
    out: Path,
    base_url: str,
    previous: Snapshot,
    *,
    date: str | None = None,
    fallback: Callable[[], dict[str, str]] = lambda: {},
) -> dict[str, str]:
    """``{loc: lastmod}`` for the pages just written to ``out``."""
    date = date or today()
    seeds: dict[str, str] | None = None
    result: dict[str, str] = {}
    for loc in locs:
        rel = loc_to_relpath(loc, base_url)
        prev = previous.get(loc)
        if prev and prev[1] is not None and rel and prev[1] == digest(out / rel):
            result[loc] = prev[0]
        elif not previous and rel:
            if seeds is None:
                seeds = fallback()
            result[loc] = min(seeds.get(rel, date), date)
        else:
            result[loc] = date
    return result


# ----------------------------------------------------------------- deploy


def reconcile_with_live(
    site: Path,
    live: Path | None,
    base_url: str,
    *,
    date: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Rewrite nothing; return ``(lastmods, changed_locs)`` for ``site``.

    ``lastmods`` starts from the ``<lastmod>`` in ``site``'s own sitemap (what
    the build recorded) and is checked against the live site:

    * unchanged since live → the earlier of the live and recorded dates (so a
      build from a clean folder cannot move an old page's date forward);
    * changed or new → the recorded date if the build dated it after the live
      one, else ``date`` (a change the build did not see, e.g. a hand edit).

    Without a live checkout (or its sitemap) the recorded dates stand and
    nothing is reported as changed.
    """
    date = date or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    recorded = read_sitemap(site / SITEMAP)
    live_mods = read_sitemap(live / SITEMAP) if live else {}
    if not live_mods:
        return dict(recorded), []
    lastmods: dict[str, str] = {}
    changed: list[str] = []
    for loc, rec in recorded.items():
        rec = rec if _DATE_RE.match(rec) else date
        rec = min(rec, date)
        rel = loc_to_relpath(loc, base_url)
        live_mod = live_mods.get(loc, "")
        new_d = digest(site / rel) if rel else None
        old_d = digest(live / rel) if rel and live else None
        if old_d is not None and new_d == old_d and _DATE_RE.match(live_mod):
            lastmods[loc] = min(live_mod, rec)
        else:
            if old_d is None or new_d != old_d:
                changed.append(loc)
            lastmods[loc] = rec if rec > live_mod else date
    return lastmods, changed


def _cmd_deploy(args: argparse.Namespace) -> int:
    site = Path(args.site)
    live = Path(args.live) if args.live else None
    if live is not None and not (live / SITEMAP).is_file():
        print(f"lastmod: no live sitemap at {live}; keeping the build's dates")
        live = None
    lastmods, changed = reconcile_with_live(site, live, args.base_url)
    (site / SITEMAP).write_text(render_sitemap(lastmods), encoding="utf-8")
    if args.changed_out:
        Path(args.changed_out).write_text(
            "".join(u + "\n" for u in changed), encoding="utf-8"
        )
    dates: dict[str, int] = {}
    for d in lastmods.values():
        dates[d] = dates.get(d, 0) + 1
    print(f"lastmod: {len(lastmods)} URLs, {len(changed)} changed since live")
    print("lastmod: dates " + json.dumps(dict(sorted(dates.items())[-10:])))
    return 0


def _cmd_reseed(args: argparse.Namespace) -> int:
    """Re-date an existing sitemap from git history (one-off / recovery)."""
    out = Path(args.out)
    current = read_sitemap(out / SITEMAP)
    if not current:
        print(f"lastmod: no sitemap in {out}", file=sys.stderr)
        return 1
    lastmods = resolve(
        list(current), out, args.base_url, {}, fallback=lambda: git_dates(out)
    )
    (out / SITEMAP).write_text(render_sitemap(lastmods), encoding="utf-8")
    print(f"lastmod: re-dated {len(lastmods)} URLs from git history")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m generator.lastmod")
    p.add_argument("--base-url", default="https://stonetop.cc")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deploy", help="carry lastmod over from the live site")
    d.add_argument("--site", required=True, help="the site about to be published")
    d.add_argument("--live", help="a checkout of the site as published now")
    d.add_argument("--changed-out", help="write the changed/new URLs here")
    d.set_defaults(func=_cmd_deploy)
    r = sub.add_parser("reseed", help="re-date a sitemap from git history")
    r.add_argument("--out", default="Stonetop_Wiki")
    r.set_defaults(func=_cmd_reseed)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
