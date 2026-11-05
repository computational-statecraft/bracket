"""Fetch Cormorant Garamond and DM Sans from Google Fonts once, so the room never depends on the network for type.
Writes woff2 files and fonts.css into frontend/fonts/. Run from the repo root: uv run python tools/fetch_fonts.py
"""
import re, sys, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "fonts"
CSS_URL = "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=DM+Sans:wght@400;500&display=swap"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read()

css = get(CSS_URL).decode()
out_css = []
for block in re.findall(r"@font-face\s*\{[^}]*\}", css):
    fam = re.search(r"font-family:\s*'([^']+)'", block).group(1)
    wt = re.search(r"font-weight:\s*(\d+)", block).group(1)
    url = re.search(r"url\(([^)]+)\)", block).group(1)
    uni = re.search(r"unicode-range:\s*([^;]+);", block)
    # keep only the latin subset for each family/weight
    if uni and "U+0000-00FF" not in uni.group(1):
        continue
    name = f"{fam.replace(' ', '')}-{wt}.woff2"
    (OUT / name).write_bytes(get(url))
    out_css.append(f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{wt};font-display:swap;src:url('/static/fonts/{name}') format('woff2');}}")
    print("saved", name)
(OUT / "fonts.css").write_text("\n".join(out_css) + "\n", encoding="utf-8")
print("wrote fonts.css with", len(out_css), "faces")
