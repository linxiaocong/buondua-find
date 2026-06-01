import sys
import json
import time
from playwright.sync_api import sync_playwright

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding crashes on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import re

def normalize_text(text):
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', '', text).lower()

def main():
    args = sys.argv[1:]
    
    # Extract --output or -o option
    output_file = None
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_file = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
    elif "-o" in args:
        idx = args.index("-o")
        if idx + 1 < len(args):
            output_file = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    if not args:
        print("Error: Please provide an artist/model name as an argument.", file=sys.stderr)
        print("Usage: python main.py \"<artist_name>\" [limit] [-o <output_file>]", file=sys.stderr)
        sys.exit(1)

    # If the last argument is a number, treat it as the limit
    limit = None
    if len(args) > 1 and args[-1].isdigit():
        limit = int(args[-1])
        artist_name = " ".join(args[:-1]).strip()
    else:
        artist_name = " ".join(args).strip()

    print(f'[Init] Searching for albums of: "{artist_name}" on buondua.com...')
    if limit is not None:
        print(f'[Init] Processing is limited to the first {limit} albums.')
    if output_file:
        print(f'[Init] Output JSON results will be written to: {output_file}')

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            # 1. Navigate to buondua.com homepage
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
                search_url = f'https://buondua.com/?search={artist_name}'
                print(f'[Search] Navigating to search URL: {search_url}')
                try:
                    page.goto(search_url, wait_until='networkidle')
                except Exception as e:
                    print(f'[Search] Error loading search URL, trying to continue: {e}')

            # 2. Scrape Album Detail Pages (including Pagination)
            albums = []
            page_num = 1
            max_pages = 5

            while page_num <= max_pages:
                print(f'[Scrape] Crawling list page {page_num}...')
                page.wait_for_timeout(3000)

                # Extract album links from the current page
                current_albums = page.evaluate('''() => {
                    const results = [];
                    
                    const getImgSrc = (img) => {
                        if (!img) return '';
                        const src = img.src || 
                                    img.getAttribute('data-src') || 
                                    img.getAttribute('data-lazy-src') || 
                                    img.getAttribute('data-original') || 
                                    img.getAttribute('srcset') || 
                                    '';
                        return src ? src.split('?')[0] : '';
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
                        const paginationLinks = Array.from(document.querySelectorAll('.pagination-list a, .pagination a, .navigation a, a'));
                        const next = paginationLinks.find(a => {
                            const text = a.innerText.trim().toLowerCase();
                            return text === 'next' || text === '»' || text.includes('next page') || text === 'sau' || a.getAttribute('rel') === 'next';
                        });
                        return next ? next.href : null;
                    }''')
                except Exception:
                    pass

                # Handle next page transition safely
                if next_link and not next_link.startswith('javascript') and next_link != page.url:
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
            albums_to_process = albums[:limit] if limit is not None else albums
            if limit is not None and len(albums) > limit:
                print(f'[Scrape] Truncating to first {limit} albums for processing.')

            # 3. Visit each album and extract download links (MediaFire and TeraBox)
            processed_albums = []

            for i, album in enumerate(albums_to_process):
                print(f'\n[Album {i + 1}/{len(albums_to_process)}] Processing: "{album["title"]}"')
                print(f'[Album {i + 1}/{len(albums_to_process)}] URL: {album["href"]}')
                print(f'[Album {i + 1}/{len(albums_to_process)}] Cover URL: {album.get("cover", "")}')

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
                    const tags = Array.from(document.querySelectorAll('a[href*="/tag/"]'))
                        .map(a => a.innerText.trim())
                        .filter((v, i, self) => v && self.indexOf(v) === i);

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
                    buttons_to_click = page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('a, button, input[type="button"]'));
                        return buttons
                            .map((btn, index) => {
                                const text = btn.innerText.trim().toLowerCase();
                                const href = btn.getAttribute('href') || '';
                                const isDownload = text.includes('download') || text.includes('tải') || text.includes('下载') || text.includes('link') || text.includes('drive') || text.includes('click here');
                                const isExternal = href.includes('redirect') || href.includes('link') || href.includes('go.buondua.com') || href.includes('download') || href.includes('external');
                                return { index, text, href, shouldClick: isDownload || isExternal };
                            })
                            .filter(b => b.shouldClick);
                    }''')

                    if buttons_to_click:
                        print(f"[Album] Found {len(buttons_to_click)} potential download redirectors. Clicking them...")
                        for btn_info in buttons_to_click:
                            try:
                                btns = page.query_selector_all('a, button, input[type="button"]')
                                if btn_info['index'] < len(btns):
                                    target_btn = btns[btn_info['index']]
                                    
                                    # Set up listener for potential new tab
                                    with context.expect_page(timeout=6000) as page_info:
                                        target_btn.click()
                                    
                                    new_page = page_info.value
                                    if new_page:
                                        print(f"[Album] Opened new tab: {new_page.url}")
                                        new_page.wait_for_load_state('domcontentloaded')
                                        new_page.wait_for_timeout(3000)

                                        tab_url = new_page.url
                                        if 'mediafire.com' in tab_url:
                                            if tab_url not in album_data['mediafire']:
                                                album_data['mediafire'].append(tab_url)
                                        elif any(d in tab_url for d in ['terabox', 'teraboxapp', 'nephobox', 'dubox']):
                                            if tab_url not in album_data['terabox']:
                                                album_data['terabox'].append(tab_url)
                                        else:
                                            sub_links = new_page.evaluate('''() => {
                                                const list = [];
                                                Array.from(document.querySelectorAll('a')).forEach(a => {
                                                    const href = a.href || '';
                                                    if (href.includes('mediafire.com')) list.push({ href, type: 'MediaFire' });
                                                    else if (href.includes('terabox.com') || href.includes('teraboxapp.com') || href.includes('nephobox.com') || href.includes('dubox.com') || href.includes('freedidi.com')) {
                                                        list.push({ href, type: 'TeraBox' });
                                                    }
                                                });
                                                return list;
                                            }''')
                                            for sub in sub_links:
                                                if sub['type'] == 'MediaFire' and sub['href'] not in album_data['mediafire']:
                                                    album_data['mediafire'].append(sub['href'])
                                                elif sub['type'] == 'TeraBox' and sub['href'] not in album_data['terabox']:
                                                    album_data['terabox'].append(sub['href'])
                                        new_page.close()
                                    else:
                                        current_url = page.url
                                        if 'mediafire.com' in current_url or any(d in current_url for d in ['terabox', 'teraboxapp', 'nephobox', 'dubox']):
                                            dtype = 'mediafire' if 'mediafire' in current_url else 'terabox'
                                            if current_url not in album_data[dtype]:
                                                album_data[dtype].append(current_url)
                                            try:
                                                page.go_back(wait_until='domcontentloaded')
                                            except Exception:
                                                pass
                            except Exception:
                                pass

                print(f"[Album] Extracted MediaFire links: {album_data['mediafire']}")
                print(f"[Album] Extracted TeraBox links:   {album_data['terabox']}")

                # CJK-aware relevance check
                # Also check the URL slug — display titles may use CJK while slugs always use romanized names
                norm_artist = normalize_text(artist_name)
                norm_title = normalize_text(album_data["title"])
                norm_tags = [normalize_text(tag) for tag in album_data["tags"]]
                norm_slug = normalize_text(album_data["url"].split('/')[-1])

                is_relevant = (norm_artist in norm_title) or any(norm_artist in tag for tag in norm_tags) or (norm_artist in norm_slug)

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
                print(json.dumps(processed_albums, indent=2))
                print('======================================================')

        except Exception as err:
            print(f'[Error] Scraping workflow failed: {err}', file=sys.stderr)
        finally:
            browser.close()
            print('\n[Done] Scraper finished.')

if __name__ == '__main__':
    main()
