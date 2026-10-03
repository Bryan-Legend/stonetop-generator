# Stonetop Web Edition

The generator behind the **Stonetop Web Edition** — a free, searchable, hyperlinked
edition of both *Stonetop* rulebooks, built from the PDFs.

**Read it online: <https://stonetop.cc/>**

The Web Edition includes:

- Every chapter and article of Book I and Book II (moves, places, peoples, powers, …)
- The playbooks and inserts as fillable sheets, with stat rolls and HP tracking
- Minor & major arcana as interactive cards (checkboxes for unlocks / progress / consequences)
- A bestiary of every stat block in both books
- Full-text search, hover previews, and dice rollers
- Deep links between page references and monster/stat blocks
- English plus twenty more languages
- Optional campaign sync, so the whole table shares ticked boxes, countdowns and HP

## Requirements

- **Python 3.10+** (3.11+ recommended)
- To **build the wiki**: nothing else. The books' text is checked in under
  [`extracted/`](extracted/README.md), one plain-text file per article, and the
  wiki is built from that.
- To **re-extract the text**: the book **1-up** PDFs (2nd printing works well) and
  PyMuPDF (`pip install -r requirements.txt`).

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/Bryan-Legend/stonetop-generator.git
cd stonetop-generator

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt   # PyMuPDF — only needed to extract from the PDFs
```

### 2. Build

```bash
python stonetop-generator.py
```

That reads `extracted/` and writes the wiki into `site/` in about ten
seconds. No PDF is opened.

To **re-extract the text** — after a change to the extractor, or a new printing —
put the 1-up PDFs in an input folder (optional `Maps/` subfolder for campaign map
sheets), then:

```bash
python stonetop-generator.py --extract --input /path/to/folder-with-pdfs
```

Extraction takes about a minute and rewrites `extracted/`; `git diff extracted/`
then shows exactly which lines of text changed, before any HTML is looked at.

| Flag | Meaning | Default |
|------|---------|---------|
| `-o` / `--output` | Wiki folder. Chrome stays in place; only book-derived files are written. | `site/` |
| `--corpus DIR` | The extracted text to build from (and to write when extracting). | `extracted/` |
| `--extract` | Re-extract from the PDFs into the corpus, then build. Without it a PDF is only opened for a book the corpus lacks. | off |
| `--extract-only` | Extract and stop; write no wiki. | off |
| `-i` / `--input` | Folder containing the 1-up book PDFs. Optional: `Maps/`. Only read when extracting. | current working directory |
| `--books book1 book2` | Limit the run to the listed books (faster while iterating). | every book in the corpus |
| `--langs de fr ja` | Build only these translations (`none` for English only). See [Languages](#languages). | every language with a translated page |
| `--maps` | Include the Maps page and its images (needs the Book II PDF). | off |

`python -m generator` is the same entry point.

### 3. Open it

```text
site/index.html
```

Or serve locally (avoids some `file://` restrictions):

```bash
cd site
python -m http.server 8000
# then visit http://localhost:8000
```
## How it is put together

```text
stonetop-generator.py   entry point (python -m generator is the same)
generator/                   the package
  text.py        markers, inline-format sentinels, line classifiers — shared by both phases
  extract.py     PDF → marker lines (the only module that needs PyMuPDF)
  articles.py    the BOOKS table, PDF outline → article list, chapter splits, arcana numbering
  corpus.py      marker lines ↔ extracted/ (the on-disk format, documented in the module)
  structure.py   marker lines → article HTML: headings, tables, stat blocks, playbook sheets, links
  arcana.py      marker lines → arcana card HTML
  chrome.py      page shell, sidebar, hub pages, pages/ overrides, home page, sitemap
  lastmod.py     sitemap <lastmod>: a page's date moves only when its HTML changes
  i18n.py        translations as data (i18n/)
  build.py       command line and the two phases
extracted/                   the books' text, one file per article — see extracted/README.md
tests/                       python -m unittest discover -s tests
```

**Two phases.** *Extract* reads a 1-up PDF's span fonts and vector drawings and
emits *marker lines* — plain strings, each opening with a marker for its role
(heading, bullet, checkbox, value-table row …) and carrying bold and italic
inline. *Build* turns those lines into HTML. The marker lines are written to
`extracted/` between the two, in a tab-separated text format made to be read,
diffed, and translated, so the second phase never needs the PDFs.

## Languages

The wiki is published in English plus twenty more languages, each in its own
directory under the wiki root:

```text
/welcome-to-the-worlds-end.html        English
/de/welcome-to-the-worlds-end.html     German
/ja/welcome-to-the-worlds-end.html     Japanese
```

Translations are checked-in data under [`i18n/`](i18n/README.md) — not
something the build re-derives — so a rebuild never disturbs one. Each page
gets a self-canonical, a reciprocal `hreflang` cluster with `x-default`,
translated chrome and metadata, and a crawlable language switcher in the
sidebar; nothing anywhere redirects on `Accept-Language`. Slugs and section
ids stay English in every language, which keeps deep links portable and keeps
a reader's ticked checkboxes shared between a page and its translations.

Pages with no translation yet stay English in that language's sidebar, marked
`EN`, and link back up to the English page.

Adding a page or a language: **[`i18n/README.md`](i18n/README.md)**. What is
translated and what never is: **[`i18n/GLOSSARY.md`](i18n/GLOSSARY.md)**.

## Adventure sites

The table-ready adventure sheets that used to live under `site/sites/`
have their own repository and site: [stonetop-adventures](https://github.com/Bryan-Legend/stonetop-adventures),
published at <https://bryan-legend.github.io/stonetop-adventures/>.

## License

**Generator code** and the wiki chrome (CSS/JS/templates) are MIT — see [LICENSE](LICENSE).

**Book text** (the `<slug>.html` pages at the wiki root, plus the generated index and search
data) is from *Stonetop* and *Stonetop: The Wider World and Other Wonders*, written by
Jeremy Strandberg and published by Lampblack & Brimstone. Both books' copyright pages
(second printing, July 2026) state:

> All text herein is released under a CC BY-SA 4.0 license.
> Some concepts and procedures are derived from Dungeon World, by Sage LaTorra & Adam Koebel,
> released under a CC BY license.

That text is reproduced here under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), reflowed from the PDFs into
HTML, and **the Web Edition is shared under the same license**.

Not affiliated with or endorsed by Lampblack & Brimstone.
