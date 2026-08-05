import re
import argparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

parser = argparse.ArgumentParser()
parser.add_argument("--year", default="2025_26", help="Admission year (e.g. 2025_26)")
args = parser.parse_args()
YEAR = args.year

BASE = "https://rgsntl.rgs.cuhk.edu.hk/aqs_prd_applx/Public/Handbook"
INDEX_URL = f"{BASE}/Default.aspx?id=1840&tv=F&lang=en"
OUTPUT_DIR = Path(__file__).parent / "minor_html" / YEAR


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
    # Collect both Default.aspx and document.aspx links from the index
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = re.search(r"id=(\d+)", href)
        if not m:
            continue
        minor_id = m.group(1)
        if minor_id == "0" or minor_id == "1840":  # skip navigation/index links
            continue
        name = a.get_text(" ", strip=True)
        pages = ("Default.aspx", "document.aspx")
        doc_type = next((t for t in pages if t in href), None)
        minors.append((minor_id, name, doc_type))

    print(f"Found {len(minors)} handbook minors from index page id=1840")

    # Detect handbook year from the index page breadcrumb
    handbook_year = None
    year_m = re.search(r"Undergraduate Student Handbook (\d{4}-\d{2})", soup.get_text())
    if year_m:
        handbook_year = year_m.group(1)
        print(f"Handbook year: {handbook_year}")
    else:
        print("WARNING: Could not detect handbook year")

    saved = 0
    year_display = YEAR.replace("_", "-")

    for minor_id, name, doc_type in minors:
        safe_name = sanitise_filename(name)

        if doc_type == "document.aspx":
            if handbook_year and handbook_year != year_display:
                print(f"\n  {name} — skipped (handbook is {handbook_year}, requested {year_display})")
                continue
            doc_link = f"/aqs_prd_applx/Public/Handbook/document.aspx?id={minor_id}&tv=F&lang=en"
            doc_id = minor_id
        else:
            try:
                minor_soup = fetch(f"{BASE}/Default.aspx?id={minor_id}&tv=F&lang=en")
            except Exception as e:
                print(f"\n  {name} — ERROR: {e}")
                continue

            doc_link = None
            doc_id = None
            for a in minor_soup.select("a[href*='document.aspx?id=']"):
                if year_display in a.get_text():
                    doc_link = a.get("href", "")
                    doc_id = re.search(r"id=(\d+)", doc_link).group(1) if doc_link else None
                    break
            if not doc_link:
                for a in minor_soup.select("a[href*='document.aspx?id=']"):
                    doc_link = a.get("href", "")
                    doc_id = re.search(r"id=(\d+)", doc_link).group(1) if doc_link else None
                    break
            if not doc_link:
                print(f"\n  {name} [{minor_id}] — no document link found")
                continue

        print(f"\n  [{doc_id}] {name}")

        # ── Step 3: find iframe src in document page ──
        if doc_link.startswith("/"):
            doc_url = f"https://rgsntl.rgs.cuhk.edu.hk{doc_link}"
        elif doc_link.startswith("http"):
            doc_url = doc_link
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
