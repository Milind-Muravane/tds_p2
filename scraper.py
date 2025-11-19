from playwright.sync_api import sync_playwright

def fetch_quiz_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        # Wait for dynamic JS to execute
        page.wait_for_timeout(1500)
        html = page.content()
        browser.close()
        return html
