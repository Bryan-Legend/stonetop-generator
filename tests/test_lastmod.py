"""Sitemap <lastmod> follows page output (``generator/lastmod.py``).

Run with ``python -m unittest`` from the repository root.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import lastmod  # noqa: E402

BASE = "https://example.org"


def site(root: Path, pages: dict[str, str], mods: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, body in pages.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(body.encode())
    (root / "sitemap.xml").write_text(
        lastmod.render_sitemap({BASE + "/" + k: v for k, v in mods.items()}),
        encoding="utf-8",
    )
    return root


class LastmodTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_paths(self):
        self.assertEqual(lastmod.loc_to_relpath(BASE + "/", BASE), "index.html")
        self.assertEqual(lastmod.loc_to_relpath(BASE + "/de/a.html", BASE), "de/a.html")
        self.assertEqual(lastmod.loc_to_relpath(BASE + "/de/", BASE), "de/index.html")
        self.assertIsNone(lastmod.loc_to_relpath("https://other/a.html", BASE))
        self.assertIsNone(lastmod.loc_to_relpath(BASE + "/../x", BASE))

    def test_normalize_ignores_line_endings(self):
        self.assertEqual(
            lastmod.normalize(b"<p>a</p>  \r\n<p>b</p>\r\n"),
            lastmod.normalize(b"<p>a</p>\n<p>b</p>\n"),
        )

    def test_build_keeps_dates_of_unchanged_pages(self):
        out = site(
            self.tmp / "out",
            {"index.html": "home", "a.html": "A", "b.html": "B"},
            {"": "2026-01-01", "a.html": "2026-01-02", "b.html": "2026-01-03"},
        )
        snap = lastmod.snapshot(out, BASE)
        (out / "b.html").write_text("B, edited")
        (out / "c.html").write_text("new")
        locs = [BASE + "/", BASE + "/a.html", BASE + "/b.html", BASE + "/c.html"]
        got = lastmod.resolve(locs, out, BASE, snap, date="2026-02-01")
        self.assertEqual(
            list(got.values()),
            ["2026-01-01", "2026-01-02", "2026-02-01", "2026-02-01"],
        )

    def test_build_without_previous_sitemap_uses_fallback(self):
        out = self.tmp / "fresh"
        out.mkdir()
        (out / "a.html").write_text("A")
        (out / "b.html").write_text("B")
        got = lastmod.resolve(
            [BASE + "/a.html", BASE + "/b.html"], out, BASE, {},
            date="2026-02-01", fallback=lambda: {"a.html": "2026-01-05"},
        )
        self.assertEqual(list(got.values()), ["2026-01-05", "2026-02-01"])

    def test_deploy_against_live(self):
        pages = {"index.html": "home", "a.html": "A", "b.html": "B"}
        live = site(
            self.tmp / "live", pages,
            {"": "2026-01-10", "a.html": "2026-01-10", "b.html": "2026-01-10",
             "gone.html": "2026-01-10"},
        )
        new = site(
            self.tmp / "new",
            {**pages, "b.html": "B2", "a.html": "A\r\n", "n.html": "N"},
            # what the build recorded: a is older than live (git-seeded), b
            # dated by the build, index hand-edited later without a rebuild
            {"": "2026-01-10", "a.html": "2026-01-01", "b.html": "2026-01-20",
             "n.html": "2026-01-20"},
        )
        (new / "index.html").write_text("home, hand edit")
        mods, changed = lastmod.reconcile_with_live(new, live, BASE, date="2026-01-25")
        self.assertEqual(mods, {
            BASE + "/": "2026-01-25",          # changed, build did not see it
            BASE + "/a.html": "2026-01-01",    # unchanged: earlier date wins
            BASE + "/b.html": "2026-01-20",    # changed, build's date
            BASE + "/n.html": "2026-01-20",    # new
        })
        self.assertEqual(changed, [BASE + "/", BASE + "/b.html", BASE + "/n.html"])

    def test_deploy_without_live_keeps_recorded(self):
        new = site(self.tmp / "new2", {"a.html": "A"}, {"a.html": "2026-01-01"})
        mods, changed = lastmod.reconcile_with_live(new, None, BASE, date="2026-03-01")
        self.assertEqual(mods, {BASE + "/a.html": "2026-01-01"})
        self.assertEqual(changed, [])

    def test_sitemap_round_trip(self):
        entries = {BASE + "/": "2026-01-01", BASE + "/a&b.html": "2026-01-02"}
        path = self.tmp / "sitemap.xml"
        path.write_text(lastmod.render_sitemap(entries), encoding="utf-8")
        self.assertEqual(lastmod.read_sitemap(path), entries)


if __name__ == "__main__":
    unittest.main()
