# Buondua Album & Download Link Scraper (OpenClaw Skill)

`buondua-find` is a self-contained, high-performance custom **OpenClaw skill** written in **Python** utilizing **Playwright**. It is designed to automatically find all photo albums of a specified model or artist on `buondua.com` — by **keyword search** or by **tag** — extract their corresponding **MediaFire** and **TeraBox** download links, and retrieve the album **tags** and **cover images**.

---

## 🌟 Features

* **Keyword Search & Tag Search:** Search by model/artist name (full-text search) or browse by exact tag (`--tag` / `-t`) for precise, pre-curated results.
* **Python & Playwright Sync API:** Powered by the robust synchronous Playwright framework to navigate, interact with dynamic elements, and parse content.
* **Automatic Cover Extraction & Stamp Stripping:** Extracts the cover image/thumbnail URL for each album and automatically strips any lazy-loading query parameters or hashes (e.g., `?e5a62e...`) to return clean, permanent image links.
* **Tag Extraction & Enhanced Logging:** Automatically extracts all related tags and keywords for each album from the detail page, and logs both the album tags and the cover image URL to the terminal during execution.
* **Intelligent Redirection Resolver:** Many download links on the target site are wrapped in shortener services (such as `ouo.io`). The scraper maps these redirect links to their corresponding download targets (MediaFire or TeraBox) by analyzing structural context and anchor text metadata.
* **Unambiguous Multi-Tiered Link Classification:** Prevents classification errors on albums where MediaFire and TeraBox links share the same parent container (e.g. `<div>MediaFire | TeraBox</div>`). It evaluates individual anchor properties (`href`, `innerText`) before falling back on parent containers only when completely unambiguous.
* **CJK-Aware Relevance Filter:** In keyword search mode, irrelevant results are automatically excluded using a CJK-aware text normalizer that matches the search term against album titles, tags, and URL slugs. Latin search terms match on whole word boundaries, so `hina` no longer matches `Qiuzi_china` or `Hinata Matsumoto`; CJK terms keep substring matching, since those scripts have no word separators. Percent-encoded slugs are decoded before matching.
* **Cover Image Downloader Utility:** Includes a generic, standalone utility (`download_covers.py`) to easily download all cover images in sequence-prefixed, sanitized formats.
* **Custom Limit Parameter:** Accepts a limit as a direct command-line argument to quickly check or scrape a subset of albums. The limit counts albums that pass the relevance filter, so `5` always yields 5 usable results rather than 5 candidates of which some get filtered out.
* **Robust Pagination:** Detects and parses pagination naturally. Safe guards are implemented to detect `javascript:;` pagination and bypass infinite redirect loops.
* **JSON Structured Output:** Prints the final results to `stdout` in an easily digestible, standard JSON format.

---

## 📂 Directory Structure

The repository structure is clean and flat under the root directory:

```text
c:\Users\charl\Desktop\buondua-find\
├── README.md                           # Skill introduction and documentation (this file)
├── SKILL.md                            # OpenClaw custom skill manifest
├── main.py                             # Core Python scraper logic
├── download_covers.py                  # Standalone script to download album covers
└── requirements.txt                    # Python dependencies (Playwright)
```

---

## 🚀 Installation & Requirements

### 1. Requirements
* **Python 3.7+**
* **OpenClaw** agent framework

### 2. Setup Dependencies
From the root of the project, run:

```bash
# Install Python packages
pip install -r requirements.txt

# Download and register Playwright Chromium binaries
python -m playwright install chromium
```

---

## 💻 Usage

### 1. Scraping Albums
Run the script from the root directory, passing the artist name as an argument.

#### Keyword Search (default)
Search by artist/model name using the site's full-text search:

```bash
python main.py "<artist_name>" [limit] [-o <output_file>]
```

#### Tag Search
Browse by exact tag — navigates directly to the tag page for precise, pre-curated results:

```bash
python main.py --tag "<tag_name>" [limit] [-o <output_file>]
python main.py -t "<tag_name>" [limit] [-o <output_file>]
```

> **Tip:** Tag search skips the relevance filter since tag pages already return exact matches. Use this when keyword search returns too many irrelevant results, or when you know the exact tag name.

> **How tag resolution works:** Tags carry numeric IDs (`/tag/yuuri-rukawa-12592`), which cannot be guessed from the name, so the scraper searches the name, opens the top results, and reads the real tag link off the first album whose tag matches exactly. Multi-word tags work (`--tag "Yuuri Rukawa"`). If nothing matches exactly the closest tag is used with a `[Tag] Warning:`, and if the tag page returns an error the run stops with a non-zero exit code rather than scraping unrelated albums.

#### Save Results to a File
To save the JSON array directly to a file (instead of printing it to stdout):

```bash
python main.py "<artist_name>" [limit] -o <output_file>
```

##### Examples:
```bash
# Keyword search: fetch the 5 most recent albums of yeonyu
python main.py "yeonyu" 5

# Tag search: fetch all albums tagged "yeha"
python main.py --tag "yeha"

# Tag search with limit and file output
python main.py -t "yeha" 10 -o results.json

# Keyword search with file output
python main.py "yeonyu" 5 -o results.json
```

---

### 2. Downloading Album Covers (Optional)
Once you have generated a JSON results file using `main.py`, you can download all listed cover/thumbnail images using `download_covers.py`:

```bash
python download_covers.py <json_file> [-d <output_dir>]
```

#### Options
- **json_file**: Path to the JSON results from the scraper (e.g. `results.json`).
- **-d / --dir**: Target directory to download the covers to. If omitted, a folder named `<json_name>_covers` will automatically be created and used.

##### Examples:
```bash
# Download covers from results.json into the default folder 'results_covers'
python download_covers.py results.json

# Download covers from results.json into a specific folder 'my_covers'
python download_covers.py results.json -d my_covers
```

---

## 📋 JSON Output Format

The scraper will return a clean JSON array representing each crawled album:

```json
[
  {
    "title": "ag-674-yeonyu-yeon-yu-148-photos-6-videos-ac163970f88e474f688ed3ecbd99709c-54758",
    "url": "https://buondua.com/ag-674-yeonyu-yeon-yu-148-photos-6-videos-ac163970f88e474f688ed3ecbd99709c-54758",
    "cover": "https://buondua.com/media/albums/ag-674-yeonyu-yeon-yu.jpg",
    "tags": [
      "yeonyu",
      "Korean",
      "Gravure"
    ],
    "mediafire": [
      "https://ouo.io/tfk361"
    ],
    "terabox": [
      "https://ouo.io/ZafWKi7"
    ]
  }
]
```

---

## ⚙️ Advanced Configuration

### Run in Headful (Visible Browser) Mode
By default, Playwright will run silently in `headless` mode. To view the browser actions in real-time (useful for debugging or if the site presents custom security verification):

**Windows (PowerShell):**
```powershell
$env:HEADLESS="false"; python main.py "yeonyu" 2
```

**Linux/macOS:**
```bash
HEADLESS=false python main.py "yeonyu" 2
```
