# scraper.py
import requests
from requests.exceptions import RequestException
import time

def fetch_quiz_html(url, timeout=20):
    """
    Fetch HTML content for the quiz page. Try Playwright (recommended) and fall back to requests.
    """
    # Try Playwright first (gives rendered DOM)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        sync_playwright = None

    if sync_playwright:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.set_default_navigation_timeout(timeout * 1000)
                page.goto(url, wait_until="networkidle")
                # give scripts a short extra time
                time.sleep(0.2)
                content = page.content()
                page.close()
                context.close()
                browser.close()
                return content
        except Exception as e:
            # fallback to requests if playwright fails
            print("Playwright fetch failed, falling back to requests:", e)

    # Fallback with plain requests (may not work for JS-heavy pages)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except RequestException as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")
