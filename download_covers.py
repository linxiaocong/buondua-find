import sys
import os
import json
import time
import urllib.request
import re
import argparse

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding crashes on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def sanitize_filename(filename):
    # Remove invalid characters for windows/linux filenames
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def main():
    parser = argparse.ArgumentParser(
        description="Generic Cover Image Downloader for buondua-find (OpenClaw Skill). "
                    "Downloads all cover/thumbnail images from a scraped album JSON file."
    )
    parser.add_argument(
        "json_file",
        help="Path to the scraped JSON file (e.g., results.json or yeonyu_albums.json)"
    )
    parser.add_argument(
        "-d", "--dir",
        help="Target directory to save the downloaded covers. If not provided, it will be automatically "
             "named after the input JSON filename (e.g., '<json_name>_covers')"
    )
    
    args = parser.parse_args()

    json_path = args.json_file
    if not os.path.exists(json_path):
        print(f"Error: Scraped JSON file '{json_path}' not found.", file=sys.stderr)
        sys.exit(1)

    # Determine default download directory if not specified
    if args.dir:
        download_dir = args.dir
    else:
        # e.g., "yeonyu_albums.json" -> "yeonyu_albums_covers"
        base_name = os.path.splitext(os.path.basename(json_path))[0]
        download_dir = f"{base_name}_covers"

    # Create download directory
    os.makedirs(download_dir, exist_ok=True)
    print(f"[Init] Saving cover images to directory: {download_dir}")

    # Load JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            albums = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON file '{json_path}': {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"[Init] Loaded {len(albums)} albums from '{json_path}'")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://buondua.com/'
    }

    success_count = 0
    for idx, album in enumerate(albums, 1):
        title = album.get('title', f'Album_{idx}')
        cover_url = album.get('cover')
        
        if not cover_url:
            print(f"[Skip {idx}/{len(albums)}] No cover URL for: {title}")
            continue

        # Generate a clean filename: Title - original_filename.ext
        url_filename = cover_url.split('/')[-1]
        ext = os.path.splitext(url_filename)[1] or '.jpg'
        
        clean_title = sanitize_filename(title)
        filename = f"{idx:02d} - {clean_title}{ext}"
        filepath = os.path.join(download_dir, filename)

        print(f"[Download {idx}/{len(albums)}] Downloading cover...")
        try:
            print(f"  Title: {title}")
            print(f"  URL:   {cover_url}")
            print(f"  To:    {filepath}")
        except Exception:
            # Fallback for old terminals if reconfiguration somehow fails
            print(f"  Title: {title.encode('ascii', 'replace').decode('ascii')}")
            print(f"  URL:   {cover_url}")
            print(f"  To:    {filepath.encode('ascii', 'replace').decode('ascii')}")

        try:
            req = urllib.request.Request(cover_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                with open(filepath, 'wb') as out_file:
                    out_file.write(response.read())
            print("  [Success] Download complete.")
            success_count += 1
        except Exception as e:
            print(f"  [Failed] Error downloading: {e}")
            
        # Polite delay to prevent hammering the server
        time.sleep(1.5)

    print(f"\n[Done] Successfully downloaded {success_count}/{len(albums)} cover images to '{download_dir}'.")

if __name__ == '__main__':
    main()
