import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE = "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/Handbook"
INDEX_URL = f"{BASE}/Default.aspx?id=1840&tv=F&lang=en"
OUTPUT_DIR = Path(__file__).parent / "minor_html"


def fetch(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def sanitise_filename(name):
    keep = []
    for ch in name:
        if ch.isalnum() or ch in " -_(),.":
            keep.append(ch)
        else:
            keep.append("_")
    name = "".join(keep).strip().replace(" ", "_")
    while "__" in name:
        name = name.replace("__", "_")
    return name.rstrip("_-.,") or "Unknown"


def extract():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: parse index page ──
    print("Fetching index page...")
    soup = fetch(INDEX_URL)

    minors = []
    for a in soup.select("a[href*='Default.aspx?id=']"):
        href = a.get("href", "")
        m = re.search(r"id=(\d+)", href)
        if not m:
            continue
        minor_id = m.group(1)
        if minor_id == "0" or minor_id == "1840":  # skip navigation/index links
            continue
        name = a.get_text(" ", strip=True)
        minors.append((minor_id, name))

    print(f"Found {len(minors)} handbook minors")
    saved = 0

    for minor_id, name in minors:
        safe_name = sanitise_filename(name)
        print(f"\n  [{minor_id}] {name}")

        # ── Step 2: get document.aspx link (2025-26) ──
        try:
            minor_soup = fetch(f"{BASE}/Default.aspx?id={minor_id}&tv=F&lang=en")
        except Exception as e:
            print(f"    ERROR fetching minor page: {e}")
            continue

        doc_link = None
        for a in minor_soup.select("a[href*='document.aspx?id=']"):
            if "2025-26" in a.get_text():
                doc_link = a.get("href", "")
                break
        if not doc_link:
            for a in minor_soup.select("a[href*='document.aspx?id=']"):
                doc_link = a.get("href", "")
                break
        if not doc_link:
            print("    No document link found — skipping")
            continue

        # ── Step 3: find iframe src in document page ──
        if doc_link.startswith("/"):
            doc_url = f"https://rgsntl.rgs.cuhk.edu.hk{doc_link}"
        else:
            doc_url = f"{BASE}/{doc_link}"
        try:
            doc_soup = fetch(doc_url)
        except Exception as e:
            print(f"    ERROR fetching document page: {e}")
            continue

        iframe = doc_soup.find("iframe")
        if not iframe:
            print("    No iframe found — skipping")
            continue

        view_src = iframe.get("src", "")
        if view_src.startswith("/"):
            view_url = f"https://rgsntl.rgs.cuhk.edu.hk{view_src}"
        else:
            view_url = f"{BASE}/{view_src}"

        # ── Step 4: fetch view_document content ──
        try:
            view_soup = fetch(view_url)
        except Exception as e:
            print(f"    ERROR fetching view document: {e}")
            continue

        # Extract the WordSection1 div content
        content_div = view_soup.find("div", class_="WordSection1")
        if not content_div:
            print("    No WordSection1 div found — skipping")
            continue

        html_content = str(content_div)

        # ── Step 5: save ──
        filepath = OUTPUT_DIR / f"HB_{safe_name}.html"
        filepath.write_text(html_content, encoding="utf-8")
        print(f"    -> Saved: HB_{safe_name}.html")
        saved += 1

    print(f"\nDone. Saved {saved}/{len(minors)} handbook minors.")


if __name__ == "__main__":
    extract()
