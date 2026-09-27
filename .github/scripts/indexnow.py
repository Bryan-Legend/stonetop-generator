#!/usr/bin/env python3
"""
Tell IndexNow (Bing, Yandex, Seznam, Naver …) which pages a deploy changed.

Optional and separable: the "IndexNow" step in .github/workflows/pages.yml is
the only caller; delete that step (and this file) to stop pinging. It never
fails the deploy: every problem is printed as a warning and it exits 0.

Usage: indexnow.py CHANGED_URLS_FILE DEPLOYED_SITEMAP

It first waits (up to ~10 minutes) for GitHub Pages to serve the sitemap that
was just pushed, so the pages are live before crawlers come for them, then
sends every changed/new URL in one POST. No changed URLs, no request.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = "stonetop-wiki.github.io"
KEY = "f76aed92590244927c1369c70551a6a3"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10_000  # IndexNow's per-request limit


def warn(msg: str) -> None:
    print(f"::warning::IndexNow: {msg}")


def fetch(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, OSError):
        return None


def wait_for_deploy(sitemap: bytes, tries: int = 30, pause: float = 20) -> bool:
    want = hashlib.sha256(sitemap).hexdigest()
    for i in range(tries):
        got = fetch(f"https://{HOST}/sitemap.xml?deploy={int(time.time())}")
        if got is not None and hashlib.sha256(got).hexdigest() == want:
            return True
        time.sleep(pause)
    return False


def main(argv: list[str]) -> int:
    changed_file, sitemap_file = Path(argv[1]), Path(argv[2])
    try:
        urls = [u.strip() for u in changed_file.read_text("utf-8").splitlines()]
    except OSError:
        warn(f"no {changed_file}; nothing to submit")
        return 0
    urls = [u for u in dict.fromkeys(urls) if u.startswith(f"https://{HOST}/")]
    if not urls:
        print("IndexNow: no changed pages; nothing to submit")
        return 0
    if len(urls) > MAX_URLS:
        warn(f"{len(urls)} changed URLs; submitting the first {MAX_URLS}")
        urls = urls[:MAX_URLS]

    if not wait_for_deploy(sitemap_file.read_bytes()):
        warn("the new sitemap is not live after 10 minutes; submitting anyway")
    body = json.dumps(
        {"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": urls}
    ).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, text = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        warn(f"request failed: {e}")
        return 0
    print(f"IndexNow: submitted {len(urls)} URLs → HTTP {status} {text[:500]}")
    if status not in (200, 202):
        warn(f"HTTP {status}: {text[:300]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as e:  # never fail the deploy
        warn(f"unexpected error: {e!r}")
        sys.exit(0)
