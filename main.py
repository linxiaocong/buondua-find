import os
import sys
import json
from urllib.parse import quote_plus, unquote
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding crashes on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import re

MAX_LIST_PAGES = 5

MEDIAFIRE_DOMAINS = ('mediafire.com',)
TERABOX_DOMAINS = ('terabox.com', 'teraboxapp.com', 'nephobox.com', 'dubox.com', 'freedidi.com')

KEEP_CHARS = r'a-zA-Z0-9\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af'
CJK_RE = re.compile(r'[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')

def normalize_text(text):
    if not text:
        return ""
    return re.sub(rf'[^{KEEP_CHARS}]', '', text).lower()

def tokenize(text):
    """Split on separators (spaces, hyphens, underscores...) and normalize each token."""
    if not text:
        return []
    return [t for t in (normalize_text(part) for part in re.split(rf'[^{KEEP_CHARS}]+', text)) if t]

def matches_artist(artist_name, target):
    """True when artist_name occurs in target as a whole token (or token sequence).

    Plain substring matching produced false positives \u2014 searching "hina" matched
    "Qiuzi_china" and "Hinata Matsumoto". CJK scripts have no word separators, so
    those terms keep substring semantics.
    """
    norm_artist = normalize_text(artist_name)
    if not norm_artist or not target:
        return False
    if CJK_RE.search(norm_artist):
        return norm_artist in normalize_text(target)

    artist_tokens = tokenize(artist_name)
    target_tokens = tokenize(target)
    if not artist_tokens or len(target_tokens) < len(artist_tokens):
        return False
    span = len(artist_tokens)
    return any(target_tokens[i:i + span] == artist_tokens
               for i in range(len(target_tokens) - span + 1))

def classify_url(url):
    """Return 'mediafire', 'terabox' or None for a resolved download URL."""
    if not url:
        return None
    lowered = url.lower()
    if any(d in lowered for d in MEDIAFIRE_DOMAINS):
        return 'mediafire'
    if any(d in lowered for d in TERABOX_DOMAINS):
        return 'terabox'
    return None

def add_link(album_data, url):
    """Record a download URL under its provider bucket. Returns True if it was new."""
    kind = classify_url(url)
    if kind and url not in album_data[kind]:
        album_data[kind].append(url)
        return True
    return False

def harvest_download_links(pw_page, album_data):
    """Collect download links from a redirect target, whether it landed on the
    provider itself or on an interstitial page linking to it."""
    if add_link(album_data, pw_page.url):
        return

    try:
        hrefs = pw_page.evaluate('''() => Array.from(document.querySelectorAll('a'))
            .map(a => a.href || '')
            .filter(Boolean)''')
    except Exception as e:
        print(f'[Album] Warning: could not read links from {pw_page.url}: {e}')
        return

    for href in hrefs:
        add_link(album_data, href)

CLICKABLE_SELECTOR = 'a, button, input[type="button"]'

def click_download_redirectors(context, page, album_url, album_data):
    """Click through shortener/redirect buttons on an album page to resolve the
    real MediaFire / TeraBox targets. Assumes `page` is already on `album_url`."""
    buttons_to_click = page.evaluate('''(selector) => {
        const buttons = Array.from(document.querySelectorAll(selector));
        return buttons
            .map((btn, index) => {
                const text = btn.innerText.trim().toLowerCase();
                const href = btn.getAttribute('href') || '';
                const isDownload = text.includes('download') || text.includes('tải') || text.includes('下载') || text.includes('link') || text.includes('drive') || text.includes('click here');
                const isExternal = href.includes('redirect') || href.includes('link') || href.includes('go.buondua.com') || href.includes('download') || href.includes('external');
                return { index, text, href, shouldClick: isDownload || isExternal };
            })
            .filter(b => b.shouldClick);
    }''', CLICKABLE_SELECTOR)

    if not buttons_to_click:
        return

    print(f"[Album] Found {len(buttons_to_click)} potential download redirectors. Clicking them...")
    for btn_info in buttons_to_click:
        try:
            # A previous click may have navigated this tab away from the album;
            # restore it so the recorded button indices still line up.
            if page.url != album_url:
                page.goto(album_url, wait_until='domcontentloaded')
                page.wait_for_timeout(1000)

            btns = page.query_selector_all(CLICKABLE_SELECTOR)
            if btn_info['index'] >= len(btns):
                continue
            target_btn = btns[btn_info['index']]
            url_before = page.url

            # The button may open a new tab or navigate in place. expect_page raises
            # on timeout when no tab is opened, so the same-tab case has to be
            # handled in an except branch rather than by testing page_info.value.
            new_page = None
            try:
                with context.expect_page(timeout=6000) as page_info:
                    target_btn.click()
                new_page = page_info.value
            except PlaywrightTimeoutError:
                new_page = None

            if new_page:
                print(f"[Album] Opened new tab: {new_page.url}")
                try:
                    new_page.wait_for_load_state('domcontentloaded')
                    new_page.wait_for_timeout(3000)
                    harvest_download_links(new_page, album_data)
                finally:
                    new_page.close()
            else:
                page.wait_for_timeout(1500)
                if page.url != url_before:
                    print(f"[Album] Navigated in the same tab: {page.url}")
                    harvest_download_links(page, album_data)
                    try:
                        page.go_back(wait_until='domcontentloaded')
                    except Exception as nav_err:
                        print(f"[Album] Warning: could not go back: {nav_err}")
        except Exception as click_err:
            print(f"[Album] Warning: redirector click failed ({btn_info.get('text', '')!r}): {click_err}")

def extract_option(args, names):
    """Pull an option and its value out of args. Exits if the value is missing."""
    for name in names:
        if name in args:
            idx = args.index(name)
            if idx + 1 >= len(args):
                print(f'Error: "{name}" requires a value.', file=sys.stderr)
                sys.exit(1)
            return args[:idx] + args[idx + 2:], args[idx + 1]
    return args, None

def extract_flag(args, names):
    """Remove every occurrence of a boolean flag from args."""
    found = False
    for name in names:
        while name in args:
            args.remove(name)
            found = True
    return args, found

def main():
    args = sys.argv[1:]

    # Extract --output or -o option
    args, output_file = extract_option(args, ["--output", "-o"])

    # Extract --tag or -t flag
    args, search_by_tag = extract_flag(args, ["--tag", "-t"])

    if not args:
        print("Error: Please provide an artist/model name or tag as an argument.", file=sys.stderr)
        print("Usage: python main.py \"<artist_name>\" [limit] [-o <output_file>]", file=sys.stderr)
        print("       python main.py --tag \"<tag_name>\" [limit] [-o <output_file>]", file=sys.stderr)
        sys.exit(1)

    # If the last argument is a number, treat it as the limit
    limit = None
    if len(args) > 1 and args[-1].isdigit():
        limit = int(args[-1])
        artist_name = " ".join(args[:-1]).strip()
    else:
        artist_name = " ".join(args).strip()

    if search_by_tag:
        print(f'[Init] Searching by tag: "{artist_name}" on buondua.com...')
    else:
        print(f'[Init] Searching for albums of: "{artist_name}" on buondua.com...')
    if limit is not None:
        print(f'[Init] Processing is limited to the first {limit} albums.')
    if output_file:
        print(f'[Init] Output JSON results will be written to: {output_file}')

    # HEADLESS=false runs with a visible browser window (documented in README.md / SKILL.md)
    headless = os.environ.get('HEADLESS', '').strip().lower() not in ('false', '0', 'no')
    if not headless:
        print('[Init] HEADLESS=false detected, launching a visible browser window.')

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            if search_by_tag:
                # Tag mode: resolve the full tag URL (includes numeric ID, e.g. /tag/hina-11388)
                # Step 1: search for the tag name to find albums that contain this tag
                tag_query = artist_name.lower().replace(' ', '-')
                # Search with the raw name, not the hyphenated slug: "?search=yuuri-rukawa"
                # returns 0 results while "?search=Yuuri Rukawa" returns the real albums.
                search_url = f'https://buondua.com/?search={quote_plus(artist_name)}'
                print(f'[Tag] Searching for "{artist_name}" to resolve tag URL...')
                try:
                    page.goto(search_url, wait_until='domcontentloaded')
                except Exception as e:
                    print(f'[Tag] Warning: search navigation error, continuing: {e}')
                page.wait_for_timeout(3000)

                # Step 2: collect candidate album links from the actual search results
                candidate_albums = page.evaluate('''() => {
                    const isInsideFooter = (el) => {
                        let node = el;
                        while (node && node !== document.body) {
                            if (node.tagName === 'FOOTER') return true;
                            if (node.className && typeof node.className === 'string' && node.className.includes('footer')) return true;
                            node = node.parentElement;
                        }
                        return false;
                    };
                    // Prefer the real result grids. The footer carries unrelated albums that
                    // are still present on 404 and "0 search result" pages, and picking one
                    // of those resolves the wrong tag entirely. Search results are split
                    // across several .blog grids, so collect from all of them.
                    const grids = Array.from(document.querySelectorAll('.blog')).filter(g => !isInsideFooter(g));
                    const scopes = grids.length > 0 ? grids : [document.body];
                    const anchors = [];
                    scopes.forEach(s => anchors.push(...Array.from(s.querySelectorAll('a'))));
                    const found = [];
                    for (const a of anchors) {
                        if (isInsideFooter(a)) continue;
                        try {
                            const path = new URL(a.href).pathname;
                            const parts = path.split('/').filter(Boolean);
                            if (parts.length === 1 && parts[0].includes('-') && parts[0].length > 5
                                && !path.startsWith('/tag/') && !path.startsWith('/category/')
                                && found.indexOf(a.href) === -1) {
                                found.push(a.href);
                            }
                        } catch(e) {}
                    }
                    return found.slice(0, 5);
                }''')

                if not candidate_albums:
                    print(f'[Tag] Error: the search for "{artist_name}" returned no albums, '
                          f'so the tag URL could not be resolved.', file=sys.stderr)
                    print('[Tag] Check the spelling, or use the exact tag name shown on an album page.',
                          file=sys.stderr)
                    sys.exit(1)

                tag_url = None
                partial_match = None
                # Step 3: the first result is not always the right model, so check a few
                # of them for a tag that matches exactly before settling for a near miss.
                for candidate in candidate_albums:
                    print(f'[Tag] Checking result for a matching tag: {candidate}')
                    try:
                        page.goto(candidate, wait_until='domcontentloaded')
                    except Exception as e:
                        print(f'[Tag] Warning: could not open result: {e}')
                        continue
                    page.wait_for_timeout(2000)

                    tag_match = page.evaluate('''(tagName) => {
                        const norm = tagName.toLowerCase().replace(/[^a-z0-9]/g, '');
                        // Only consider this album's own tags; the related-albums grid at the
                        // bottom of the page carries other models' tags.
                        const scope = document.querySelector('.article-tags') || document;
                        const tagLinks = Array.from(scope.querySelectorAll('a[href*="/tag/"]'));
                        const normOf = (a) => a.innerText.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
                        for (const a of tagLinks) {
                            if (normOf(a) === norm) return { href: a.href, label: a.innerText.trim(), exact: true };
                        }
                        // Fallback: partial match
                        for (const a of tagLinks) {
                            const text = normOf(a);
                            if (text.includes(norm) || norm.includes(text)) {
                                return { href: a.href, label: a.innerText.trim(), exact: false };
                            }
                        }
                        return null;
                    }''', artist_name)

                    if tag_match and tag_match['exact']:
                        tag_url = tag_match['href']
                        break
                    if tag_match and partial_match is None:
                        partial_match = tag_match

                if not tag_url and partial_match:
                    # e.g. searching "hina" can land on the "Hinata Matsumoto" tag
                    tag_url = partial_match['href']
                    print(f'[Tag] Warning: no exact tag match for "{artist_name}". '
                          f'Falling back to the closest tag: "{partial_match["label"]}".')

                if not tag_url:
                    # Last resort: guess the slug (works only for tags without a numeric ID)
                    tag_url = f'https://buondua.com/tag/{quote_plus(tag_query)}'
                    print(f'[Tag] Could not resolve tag URL from search results, trying direct: {tag_url}')
                else:
                    print(f'[Tag] Resolved tag URL: {tag_url}')

                # A missing tag page returns a 404 whose footer still lists unrelated
                # albums, so scraping it silently produces a full page of wrong results.
                try:
                    response = page.goto(tag_url, wait_until='domcontentloaded')
                except Exception as e:
                    print(f'[Tag] Error: could not open the tag page {tag_url}: {e}', file=sys.stderr)
                    sys.exit(1)

                if response is not None and response.status >= 400:
                    print(f'[Tag] Error: the tag page {tag_url} returned HTTP {response.status}.', file=sys.stderr)
                    print(f'[Tag] "{artist_name}" does not appear to be a valid tag on buondua.com. '
                          f'Try the keyword search instead: python main.py "{artist_name}"', file=sys.stderr)
                    sys.exit(1)
            else:
                # Search mode: navigate to homepage and use search input
                print('[Nav] Opening buondua.com...')
                try:
                    page.goto('https://buondua.com/', wait_until='domcontentloaded')
                except Exception as e:
                    print(f'[Nav] Warning: direct navigation had some errors, continuing: {e}')

                # Locate search input
                print('[Search] Locating search input...')
                search_input_selector = 'input[type="search"], input[name="search"], input[name="q"], input[placeholder*="search" i], input[placeholder*="Search" i], input[placeholder*="tìm" i]'
                search_input = None
                try:
                    page.wait_for_selector(search_input_selector, timeout=6000)
                    search_input = page.query_selector(search_input_selector)
                except Exception:
                    print('[Search] Search input not found on homepage. Attempting direct search query URL.')

                if search_input:
                    search_input.fill(artist_name)
                    print(f'[Search] Filled search input with "{artist_name}". Submitting search...')
                    try:
                        with page.expect_navigation(wait_until='networkidle', timeout=35000):
                            search_input.press('Enter')
                    except Exception:
                        pass
                else:
                    search_url = f'https://buondua.com/?search={quote_plus(artist_name)}'
                    print(f'[Search] Navigating to search URL: {search_url}')
                    try:
                        page.goto(search_url, wait_until='networkidle')
                    except Exception as e:
                        print(f'[Search] Error loading search URL, trying to continue: {e}')

            # 2. Scrape Album Detail Pages (including Pagination)
            albums = []
            page_num = 1
            visited_list_pages = set()

            while page_num <= MAX_LIST_PAGES:
                visited_list_pages.add(page.url)
                print(f'[Scrape] Crawling list page {page_num}...')
                page.wait_for_timeout(3000)

                # Extract album links from the current page
                current_albums = page.evaluate('''() => {
                    const results = [];
                    
                    // "url1 320w, url2 640w" -> largest candidate's bare URL
                    const pickFromSrcset = (value) => {
                        const parts = value.split(',').map(s => s.trim()).filter(Boolean);
                        if (!parts.length) return '';
                        return parts[parts.length - 1].split(/\\s+/)[0];
                    };

                    const getImgSrc = (img) => {
                        if (!img) return '';
                        let src = img.getAttribute('src') ||
                                  img.getAttribute('data-src') ||
                                  img.getAttribute('data-lazy-src') ||
                                  img.getAttribute('data-original') ||
                                  '';
                        if (!src) {
                            src = pickFromSrcset(img.getAttribute('srcset') || img.getAttribute('data-srcset') || '');
                        }
                        if (!src || src.startsWith('data:')) return '';
                        try { src = new URL(src, document.baseURI).href; } catch (e) { return ''; }
                        return src.split('?')[0].split('#')[0];
                    };

                    const mainContent = document.querySelector('.column.is-9, .column.is-8, .column.is-three-quarters, .column.is-two-thirds, .main-content, #main-content') || document.querySelector('main, #content') || document.body;
                    const allGrids = Array.from(mainContent.querySelectorAll('.columns.is-multiline, div.grid, .posts, .articles'));

                    // Exclude grids that are inside a <footer> element or whose parent class contains "footer"
                    const isInsideFooter = (el) => {
                        let node = el;
                        while (node && node !== document.body) {
                            if (node.tagName === 'FOOTER') return true;
                            if (node.className && typeof node.className === 'string' && node.className.includes('footer')) return true;
                            node = node.parentElement;
                        }
                        return false;
                    };
                    const grids = allGrids.filter(g => !isInsideFooter(g));
                    const targetContainers = grids.length > 0 ? grids : [mainContent];

                    targetContainers.forEach(container => {
                        container.querySelectorAll('a').forEach(a => {
                            // The grid filter above drops footer grids, but when *every* grid is
                            // a footer grid (404 pages, 0-result searches) targetContainers falls
                            // back to the whole body — which puts those links right back in.
                            if (isInsideFooter(a)) return;
                            const href = a.href;
                            if (!href) return;
                            try {
                                const url = new URL(href);
                                const path = url.pathname;
                                if (path === '/' || path.startsWith('/tag/') || path.startsWith('/category/') || path.startsWith('/search') || path.includes('contact') || path.includes('privacy')) {
                                    return;
                                }
                                const pathParts = path.split('/').filter(Boolean);
                                if (pathParts.length === 1 && pathParts[0].includes('-') && pathParts[0].length > 5) {
                                    const imgEl = a.querySelector('img') || (a.parentElement ? a.parentElement.querySelector('img') : null);
                                    results.push({ 
                                        title: a.innerText.trim() || pathParts[0], 
                                        href: href,
                                        cover: getImgSrc(imgEl)
                                    });
                                }
                            } catch (err) {}
                        });
                    });

                    // Deduplicate
                    const unique = [];
                    const seen = new Set();
                    for (const item of results) {
                        if (item.href && !seen.has(item.href)) {
                            seen.add(item.href);
                            unique.push(item);
                        }
                    }
                    return unique;
                }''')

                print(f'[Scrape] Found {len(current_albums)} albums on page {page_num}.')
                for alb in current_albums:
                    if not any(a['href'] == alb['href'] for a in albums):
                        albums.append(alb)

                # Check for next page link
                next_link = None
                try:
                    next_link = page.evaluate('''() => {
                        const isNext = (a) => {
                            const text = (a.innerText || '').trim().toLowerCase();
                            return a.getAttribute('rel') === 'next' || text === 'next' ||
                                   text === '»' || text === '>' || text === 'sau' || text.includes('next page');
                        };
                        // Only look inside real pagination widgets; scanning every <a> on the
                        // page picks up unrelated "next" links elsewhere in the layout.
                        const scopes = Array.from(document.querySelectorAll('.pagination, .pagination-list, .navigation, nav'));
                        const containers = scopes.length > 0 ? scopes : [document.body];
                        for (const container of containers) {
                            for (const a of Array.from(container.querySelectorAll('a'))) {
                                // "javascript:;" is used for disabled First/Prev controls
                                if (isNext(a) && a.href && !a.href.startsWith('javascript')) return a.href;
                            }
                        }
                        return null;
                    }''')
                except Exception as e:
                    print(f'[Nav] Warning: could not look for a next page link: {e}')

                # Handle next page transition safely
                if next_link and not next_link.startswith('javascript') and next_link not in visited_list_pages:
                    print(f'[Nav] Moving to next page URL: {next_link}')
                    try:
                        page.goto(next_link, wait_until='networkidle')
                    except Exception as e:
                        print(f'[Nav] Warning moving to next page: {e}')
                    page_num += 1
                else:
                    # Try clicking the next page button in case of javascript pagination
                    clicked = False
                    try:
                        next_button = page.query_selector('.pagination-list a.next, .pagination a.next, a.next-page, a[rel="next"]')
                        if next_button:
                            print('[Nav] Found next button. Attempting click...')
                            current_url = page.url
                            try:
                                with page.expect_navigation(wait_until='networkidle', timeout=10000):
                                    next_button.click()
                                if page.url != current_url:
                                    clicked = True
                                    page_num += 1
                            except Exception:
                                pass
                    except Exception:
                        pass

                    if not clicked:
                        print('[Nav] No next page found or navigation failed. List scraping completed.')
                        break

            print(f'\n[Scrape] Collected a total of {len(albums)} albums to process.')
            if not albums:
                print(f'[Scrape] No albums matched "{artist_name}". Check the spelling, '
                      f'or try the other mode ({"keyword search" if search_by_tag else "--tag"}).')

            # 3. Visit each album and extract download links (MediaFire and TeraBox)
            # The limit counts albums that survive the relevance filter, so "5" always
            # means 5 usable results rather than "5 candidates, however many match".
            processed_albums = []

            for i, album in enumerate(albums):
                if limit is not None and len(processed_albums) >= limit:
                    print(f'\n[Limit] Reached the requested limit of {limit} albums. Stopping.')
                    break

                print(f'\n[Album {i + 1}/{len(albums)}] Processing: "{album["title"]}"')
                print(f'[Album {i + 1}/{len(albums)}] URL: {album["href"]}')
                print(f'[Album {i + 1}/{len(albums)}] Cover URL: {album.get("cover", "")}')

                album_data = {
                    "title": album["title"],
                    "url": album["href"],
                    "cover": album.get("cover", ""),
                    "tags": [],
                    "mediafire": [],
                    "terabox": []
                }

                try:
                    page.goto(album["href"], wait_until='domcontentloaded')
                except Exception as e:
                    print(f'[Album] Warning navigating to details: {e}')
                page.wait_for_timeout(2000)

                # Scan links inside detail page using unambiguous association
                detail_data = page.evaluate('''() => {
                    const dedupe = (list) => list
                        .map(a => a.innerText.trim())
                        .filter((v, i, self) => v && self.indexOf(v) === i);

                    // This album's own tags live in .article-tags. Scanning the whole
                    // document also picks up the "related albums" grid at the bottom
                    // (.item-tags) and any sidebar tag cloud, which pollutes the tag
                    // list and makes the relevance filter match on other models' names.
                    const tagScope = document.querySelector('.article-tags');
                    let tags = tagScope ? dedupe(Array.from(tagScope.querySelectorAll('a[href*="/tag/"]'))) : [];
                    if (tags.length === 0) {
                        // Fallback if the layout changes: take every tag link that is not
                        // inside a related-item card, sidebar or footer.
                        tags = dedupe(Array.from(document.querySelectorAll('a[href*="/tag/"]'))
                            .filter(a => !a.closest('.item-tags, .items-row, .blog, aside, footer, .sidebar')));
                    }

                    const extracted = [];
                    const anchors = Array.from(document.querySelectorAll('a'));
                    anchors.forEach(a => {
                        const href = a.href || '';
                        const text = a.innerText.trim().toLowerCase();
                        
                        // 1. Direct domain check
                        if (href.includes('mediafire.com')) {
                            extracted.push({ href, type: 'MediaFire' });
                            return;
                        }
                        if (
                            href.includes('terabox.com') ||
                            href.includes('teraboxapp.com') ||
                            href.includes('nephobox.com') ||
                            href.includes('dubox.com') ||
                            href.includes('freedidi.com')
                        ) {
                            extracted.push({ href, type: 'TeraBox' });
                            return;
                        }

                        // 2. Anchor text check (most specific)
                        if (text.includes('mediafire') || text.includes('media fire')) {
                            extracted.push({ href, type: 'MediaFire' });
                            return;
                        }
                        if (
                            text.includes('terabox') ||
                            text.includes('tera box') ||
                            text.includes('nephobox') ||
                            text.includes('dubox') ||
                            text.includes('freedidi')
                        ) {
                            extracted.push({ href, type: 'TeraBox' });
                            return;
                        }

                        // 3. Parent container check (fallback only if anchor itself has no identifier text)
                        const parentText = a.parentElement ? a.parentElement.innerText.trim().toLowerCase() : '';
                        const isMediaFireParent = parentText.includes('mediafire') || parentText.includes('media fire');
                        const isTeraBoxParent = parentText.includes('terabox') || parentText.includes('tera box') || parentText.includes('nephobox') || parentText.includes('dubox') || parentText.includes('freedidi');

                        // Only fallback to parent container if it is unambiguous (i.e. only one matches)
                        if (isMediaFireParent && !isTeraBoxParent && href.startsWith('http')) {
                            extracted.push({ href, type: 'MediaFire' });
                        } else if (isTeraBoxParent && !isMediaFireParent && href.startsWith('http')) {
                            extracted.push({ href, type: 'TeraBox' });
                        }
                    });
                    return { tags, links: extracted };
                }''')

                album_data['tags'] = detail_data.get('tags', [])
                print(f"[Album] Tags: {album_data['tags']}")

                found_links = detail_data.get('links', [])
                for link in found_links:
                    if link['type'] == 'MediaFire' and link['href'] not in album_data['mediafire']:
                        album_data['mediafire'].append(link['href'])
                    elif link['type'] == 'TeraBox' and link['href'] not in album_data['terabox']:
                        album_data['terabox'].append(link['href'])

                # Click download/redirect buttons if no links are directly available
                if not album_data['mediafire'] and not album_data['terabox']:
                    click_download_redirectors(context, page, album["href"], album_data)

                print(f"[Album] Extracted MediaFire links: {album_data['mediafire']}")
                print(f"[Album] Extracted TeraBox links:   {album_data['terabox']}")

                # Relevance check: skip for tag mode (tag pages already return exact matches)
                if search_by_tag:
                    processed_albums.append(album_data)
                else:
                    # CJK-aware relevance check
                    # Also check the URL slug — display titles may use CJK while slugs always use romanized names.
                    # Slugs are percent-encoded, so "히나" appears as "%ED%9E%88%EB%82%98";
                    # decode before matching or a CJK term can never match its own slug.
                    slug = unquote(album_data["url"].rstrip('/').split('/')[-1])

                    is_relevant = (matches_artist(artist_name, album_data["title"])
                                   or any(matches_artist(artist_name, tag) for tag in album_data["tags"])
                                   or matches_artist(artist_name, slug))

                    if is_relevant:
                        processed_albums.append(album_data)
                    else:
                        print(f"[Filter] Excluding irrelevant search result: \"{album_data['title']}\"")

            # 4. Output final results
            if output_file:
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(processed_albums, f, indent=2, ensure_ascii=False)
                    print(f'\n[Done] Successfully saved results to: {output_file}')
                except Exception as file_err:
                    print(f'\n[Error] Failed to save results to {output_file}: {file_err}', file=sys.stderr)
            else:
                print('\n=================== SEARCH RESULTS ===================')
                print(json.dumps(processed_albums, indent=2, ensure_ascii=False))
                print('======================================================')

        except Exception as err:
            print(f'[Error] Scraping workflow failed: {err}', file=sys.stderr)
        finally:
            browser.close()
            print('\n[Done] Scraper finished.')

if __name__ == '__main__':
    main()
