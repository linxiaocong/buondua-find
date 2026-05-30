---
name: buondua-find
description: Find all photo albums of a model or artist on buondua.com, and extract their buondua.com URL as well as download links for MediaFire and TeraBox.
---
# buondua-find

This skill enables the agent to search for any model or artist on `buondua.com`, gather all her photo albums, and retrieve the download links (MediaFire and TeraBox) for each album.

## Requirements
- Python 3.x installed
- Playwright Python library installed (`pip install -r requirements.txt`)
- Playwright Chromium browser installed (`python -m playwright install chromium`)

## Usage
To use this skill, execute the scraper script from the root of the project:

```bash
python main.py "<artist_name>" [limit]
```

### Options
You can disable headless mode by setting the `HEADLESS` environment variable to `false`:

```bash
$env:HEADLESS="false"; python main.py "<artist_name>" [limit]
```

## Output Format
The skill prints a JSON array of albums to `stdout`. Each album object contains:
- `title`: The title of the photo album
- `url`: The buondua.com album detail page URL
- `mediafire`: An array of extracted MediaFire download links
- `terabox`: An array of extracted TeraBox download links
