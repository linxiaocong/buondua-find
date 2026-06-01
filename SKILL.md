---
name: buondua-find
description: Find all photo albums of a model or artist on buondua.com, and extract their buondua.com URL, tags, cover image, as well as download links for MediaFire and TeraBox.
---
# buondua-find

This skill enables the agent to search for any model or artist on `buondua.com`, gather all her photo albums, and retrieve the download links (MediaFire and TeraBox) for each album.

## Requirements
- Python 3.x installed
- Playwright Python library installed (`pip install -r requirements.txt`)
- Playwright Chromium browser installed (`python -m playwright install chromium`)

## Usage

### 1. Scraping Albums
To use this skill, execute the scraper script from the root of the project:

```bash
python main.py "<artist_name>" [limit] [-o <output_file>]
```

#### Options
- **Output File**: Pass `-o <file>` or `--output <file>` to write the final JSON output directly to a file instead of `stdout`.
- **Headless Mode**: You can disable headless mode by setting the `HEADLESS` environment variable to `false`:

```bash
# Windows (PowerShell)
$env:HEADLESS="false"; python main.py "<artist_name>" [limit]
```

### 2. Downloading Album Covers (Optional)
To download all the cover images found by the scraper, run the generic downloader script:

```bash
python download_covers.py <json_file> [-d <output_dir>]
```

#### Options
- **json_file**: Path to the JSON results from the scraper (e.g. `yeonyu_albums.json`).
- **-d / --dir**: Target directory to download the covers to. If omitted, a folder named `<json_name>_covers` will automatically be created and used.

## Output Format
By default, the skill prints a JSON array of albums to `stdout` (or saves to a file if the output option is used). Each album object contains:
- `title`: The title of the photo album
- `url`: The buondua.com album detail page URL
- `cover`: The URL of the album's cover image / thumbnail (automatically stripped of lazy-loading query parameters/hashes)
- `tags`: An array of tags/keywords associated with the album (extracted from the detail page)
- `mediafire`: An array of extracted MediaFire download links
- `terabox`: An array of extracted TeraBox download links
