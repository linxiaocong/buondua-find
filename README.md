# Buondua Album & Download Link Scraper (OpenClaw Skill)

`buondua-find` is a self-contained, high-performance custom **OpenClaw skill** written in **Python** utilizing **Playwright**. It is designed to automatically find all photo albums of a specified model or artist on `buondua.com` and extract their corresponding **MediaFire** and **TeraBox** download links.

---

## 🌟 Features

* **Python & Playwright Sync API:** Powered by the robust synchronous Playwright framework to navigate, interact with dynamic elements, and parse content.
* **Automatic Cover Extraction & Stamp Stripping:** Extracts the cover image/thumbnail URL for each album and automatically strips any lazy-loading query parameters or hashes (e.g., `?e5a62e...`) to return clean, permanent image links.
* **Intelligent Redirection Resolver:** Many download links on the target site are wrapped in shortener services (such as `ouo.io`). The scraper maps these redirect links to their corresponding download targets (MediaFire or TeraBox) by analyzing structural context and anchor text metadata.
* **Unambiguous Multi-Tiered Link Classification:** Prevents classification errors on albums where MediaFire and TeraBox links share the same parent container (e.g. `<div>MediaFire | TeraBox</div>`). It evaluates individual anchor properties (`href`, `innerText`) before falling back on parent containers only when completely unambiguous.
* **Custom Limit Parameter:** Accepts a limit as a direct command-line argument to quickly check or scrape a subset of albums.
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

Run the script from the root directory, passing the artist name as an argument.

### Get All Albums
To crawl and retrieve all albums for a model without an upper limit:

```bash
python main.py "<artist_name>"
```

### Get Albums with a Limit
To crawl and retrieve only the first `N` albums (highly useful for quick testing or checking recent uploads):

```bash
python main.py "<artist_name>" <limit>
```

#### Examples:
```bash
# Fetch the 5 most recent albums of yeonyu
python main.py "yeonyu" 5
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
