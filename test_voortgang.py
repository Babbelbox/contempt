"""Test voortgangsbalk: klik Start, wacht op partijresultaat, check balk."""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time, csv

CSV_DIR = Path(r"C:\Users\nickm\OneDrive\Bureaublad\Contempt\results")
csvs_voor = set(CSV_DIR.glob("*.csv"))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:8501")
    page.wait_for_load_state("networkidle")
    time.sleep(4)

    page.locator("button", has_text="Start partijen").first.click(force=True)
    time.sleep(2)
    print(f"Running: {page.locator('button', has_text='Start partijen').first.is_disabled()}")

    # Wacht op eerste game-resultaat (max 90s)
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(5)
        for p_csv in set(CSV_DIR.glob("*.csv")) - csvs_voor:
            try:
                rows = list(csv.DictReader(open(p_csv, encoding="utf-8")))
                if rows and rows[0].get("result") not in ("", "ERROR", None):
                    print(f"Partij voltooid: {rows[0]}")
                    break
            except Exception:
                pass
        else:
            continue
        break

    page.screenshot(path="/tmp/voortgang.png", full_page=True)

    # Check voortgangsbalk
    progress = page.locator("[data-testid='stProgress'], [role='progressbar']")
    print(f"Progress elementen: {progress.count()}")
    if progress.count() > 0:
        print(f"Progress tekst: {progress.first.inner_text()[:80]}")

    page.locator("button", has_text="Stop").first.click(force=True)
    time.sleep(2)
    browser.close()
    print("Klaar.")
