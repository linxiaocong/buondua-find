# CLAUDE.md

Guidance for AI assistants working in this repository.

## What this is

`buondua-find` is an **OpenClaw skill**: a self-contained Python + Playwright
scraper that finds photo albums for a model/artist on `buondua.com` and extracts
each album's URL, tags, cover image, and MediaFire / TeraBox download links.

There is no package, no module hierarchy, and no build step. Two standalone CLI
scripts sit at the repo root and are run directly with `python`.

## Layout

```text
buondua-find/
├── SKILL.md            # OpenClaw skill manifest (YAML front matter: name, description)
├── README.md           # User-facing docs
├── main.py             # The scraper. All logic lives here (~700 lines, single file)
├── download_covers.py  # Standalone utility: reads scraper JSON, downloads covers
├── requirements.txt    # playwright>=1.40.0 — the only dependency
└── LICENSE             # GPL-3.0
```

`main.py` and `download_covers.py` share no code by design; the downloader only
consumes the JSON contract described below.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium   # skip in environments that preinstall Chromium
```

In this remote environment Chromium is already installed and
`PLAYWRIGHT_BROWSERS_PATH` is preconfigured — do **not** run
`playwright install`.

## Commands

```bash
# Keyword search (default mode)
python main.py "<artist_name>" [limit] [-o out.json]

# Tag search — browse an exact tag page instead
python main.py --tag "<tag_name>" [limit] [-o out.json]
python main.py -t "<tag_name>" [limit] [-o out.json]

# Visible browser (debugging)
HEADLESS=false python main.py "yeonyu" 2

# Download the covers listed in a results file
python download_covers.py results.json [-d covers_dir]
```

Argument parsing in `main.py` is hand-rolled (`extract_option` / `extract_flag`),
not `argparse`: options are stripped out of `sys.argv[1:]` first, then the
remaining words are joined into the search term, and a trailing all-digits
argument becomes the limit. So `python main.py Yuuri Rukawa 5` works without
quotes. `download_covers.py` does use `argparse`.

## How main.py flows

1. **Resolve a starting list page.**
   - *Keyword mode*: open the homepage, fill the search input, submit; fall back
     to `https://buondua.com/?search=<term>` if the input isn't found.
   - *Tag mode*: tag URLs carry unguessable numeric IDs (`/tag/hina-11388`), so
     the scraper searches the name, opens up to 5 result albums, and reads the
     real tag href off the first album whose own tag matches exactly. An inexact
     match falls back to the closest tag with a `[Tag] Warning:`. A tag page that
     returns HTTP >= 400 is a hard `sys.exit(1)`.
2. **Paginate the album list** up to `MAX_LIST_PAGES` (5), collecting
   `{title, href, cover}` per album via in-page JS. Visited list-page URLs are
   tracked in `visited_list_pages` to break redirect loops, and
   `javascript:;` hrefs (disabled pagination controls) are rejected.
3. **Visit each album detail page**, extract tags plus MediaFire/TeraBox links.
   If no links are found directly, `click_download_redirectors` clicks candidate
   shortener buttons and harvests the resolved targets.
4. **Filter for relevance** (keyword mode only), then print JSON to stdout or
   write it to `-o`.

## Output contract

An array of objects — `download_covers.py` and any downstream consumer depend on
these keys, so don't rename them:

```json
[
  {
    "title": "…",
    "url": "https://buondua.com/…",
    "cover": "https://buondua.com/media/albums/….jpg",
    "tags": ["yeonyu", "Korean"],
    "mediafire": ["https://ouo.io/tfk361"],
    "terabox": ["https://ouo.io/ZafWKi7"]
  }
]
```

`cover` is stripped of query strings and fragments (lazy-loading hashes like
`?e5a62e…`) so links stay permanent. `mediafire` / `terabox` may hold
shortener URLs (`ouo.io`) rather than final provider URLs — that is expected.

## Conventions to follow

**Scraping fixes belong in the JS, not in Python.** Nearly all DOM work happens
inside `page.evaluate('''…''')` strings. Keep new selector logic there so it runs
in one round trip.

**Every comment in this codebase explains a bug that was fixed.** The comments
are the regression-test suite for a project with no tests — preserve them when
editing nearby code, and add one in the same style when you fix a scraping bug.
The invariants they encode:

- *Footer / related-album exclusion.* 404 pages and 0-result searches still
  render unrelated albums in the footer and in related-item grids. Every
  extractor filters via an `isInsideFooter` walk and scopes tags to
  `.article-tags`, excluding `.item-tags, .items-row, .blog, aside, footer,
  .sidebar`. Without this, the wrong tag gets resolved and other models' names
  pollute the tag list, which in turn breaks the relevance filter.
- *Link classification is tiered and order-dependent* (`href` domain → anchor
  `innerText` → parent container, and the parent tier only fires when
  unambiguous). Albums render `<div>MediaFire | TeraBox</div>` with both links in
  one parent, so a parent-first check misclassifies them.
- *CJK-aware relevance matching* (`matches_artist`). Latin terms match on whole
  token boundaries so `hina` doesn't match `Qiuzi_china` or `Hinata Matsumoto`;
  CJK terms keep substring semantics because those scripts have no word
  separators. Matching runs against title, tags, **and** the percent-decoded URL
  slug — CJK titles have romanized slugs, and `unquote` is required or a CJK term
  can never match its own slug.
- *`limit` counts albums that pass the filter*, not candidates examined — the
  check is `len(processed_albums) >= limit`, so `5` always yields 5 usable rows.
- *Search by raw name, not a hyphenated slug.* `?search=yuuri-rukawa` returns 0
  results; `?search=Yuuri+Rukawa` returns the real albums.
- *`context.expect_page` raises on timeout* when a click navigates in the same
  tab instead of opening one, so the same-tab path must live in the
  `except PlaywrightTimeoutError` branch — it cannot be detected by inspecting
  `page_info.value`.
- *Button indices are re-resolved after every click*, and the page is navigated
  back to `album_url` first, because a prior click may have moved the tab.

**Windows is a first-class target.** Both scripts reconfigure stdout/stderr to
UTF-8 at import to avoid encoding crashes in `cp1252` terminals, and
`sanitize_filename` strips control characters plus trailing dots/spaces and caps
titles at `MAX_TITLE_LEN` (80) for `MAX_PATH`. Keep both behaviors.

**Be resilient, not strict.** Navigation and DOM calls are wrapped in
`try/except` that log a `[Phase] Warning: …` and continue. Reserve `sys.exit(1)`
for cases where continuing would produce actively wrong output (unresolvable tag,
404 tag page, missing option value).

**Log with a bracketed phase prefix** on stdout: `[Init]`, `[Nav]`, `[Search]`,
`[Tag]`, `[Scrape]`, `[Album]`, `[Filter]`, `[Limit]`, `[Done]`, `[Error]`.
Errors and usage go to `stderr`. Note that progress logging shares `stdout` with
the JSON payload, so machine consumers should use `-o`.

**Rate limiting.** `download_covers.py` sleeps 1.5s between downloads and sends a
`Referer: https://buondua.com/` header (the CDN requires it). Don't remove either.

## Testing

There is no test suite, linter, or CI. Verification is manual — run the scraper
against a known artist with a small limit and check the JSON:

```bash
python main.py "yeonyu" 2
```

Network access to `buondua.com` is required, so this can't be validated offline.
When changing extraction logic, exercise **both** modes (keyword and `--tag`),
since they take different paths to the list page, and `--tag` deliberately skips
the relevance filter.

## Keeping docs in sync

`README.md` and `SKILL.md` both document the CLI surface and the JSON keys. Any
change to flags, output fields, or environment variables must be reflected in
both, plus this file.

## Git workflow

Development happens on feature branches; push with
`git push -u origin <branch-name>`. Do not open a pull request unless explicitly
asked.
