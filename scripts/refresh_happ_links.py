#!/usr/bin/env python3
"""
Regenerates happ://crypt5/... deep links inside an HTML file.

How it works:
- The script scans the given HTML file for every `data-sub="<raw-url>"`
  attribute. That raw URL is treated as the source of truth.
- For each unique raw URL, it calls the official Happ encryption API
  (https://crypto.happ.su/api-v2.php) to get a fresh happ://crypt5/... link.
- It then rewrites the matching `href="..."` (the one immediately followed
  by that same data-sub attribute) to the new encrypted link.
- Run this on a schedule (see .github/workflows/refresh-happ-links.yml) so
  the links never go stale.

Usage:
    python3 refresh_happ_links.py path/to/page.html
"""

import json
import re
import sys
import urllib.request
import urllib.error

API_URL = "https://crypto.happ.su/api-v2.php"
HAPP_LINK_RE = re.compile(r'happ://crypt[0-9]?/[^\s"\'\\]+')


def encrypt(raw_url: str) -> str:
    payload = json.dumps({"url": raw_url}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Request to {API_URL} failed for {raw_url}: {e}") from e

    match = HAPP_LINK_RE.search(text)
    if not match:
        raise RuntimeError(
            f"No happ:// link found in API response for {raw_url}. "
            f"Raw response (truncated): {text[:300]!r}"
        )
    return match.group(0)


def replace_href_for(html: str, raw_url: str, new_link: str) -> tuple[str, int]:
    # Matches: href="ANYTHING" ... data-sub="raw_url"
    # and rewrites only the href value, leaving data-sub untouched.
    pattern = re.compile(
        r'href="[^"]*"(\s+data-sub="' + re.escape(raw_url) + r'")'
    )
    new_link_escaped = new_link.replace("\\", "\\\\")
    new_html, count = pattern.subn(f'href="{new_link_escaped}"\\1', html)
    return new_html, count


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: refresh_happ_links.py <path-to-html-file>", file=sys.stderr)
        return 1

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    raw_urls = sorted(set(re.findall(r'data-sub="([^"]+)"', html)))
    if not raw_urls:
        print("No data-sub attributes found — nothing to do.")
        return 0

    errors = []
    for raw_url in raw_urls:
        try:
            new_link = encrypt(raw_url)
        except RuntimeError as e:
            print(f"[FAIL] {raw_url}: {e}", file=sys.stderr)
            errors.append(raw_url)
            continue

        html, count = replace_href_for(html, raw_url, new_link)
        if count == 0:
            print(f"[WARN] Got a new link for {raw_url} but found no href to update.")
        else:
            print(f"[OK] {raw_url} -> {new_link} ({count} occurrence(s) updated)")

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    if errors:
        print(f"\n{len(errors)} URL(s) failed to encrypt — their old links were left in place.", file=sys.stderr)
        # Don't fail the whole workflow over one bad URL; the old (still
        # possibly valid) link stays in the file rather than breaking it.
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
