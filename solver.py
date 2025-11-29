from scraper import fetch_quiz_html
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import requests
import json
import pandas as pd
import io


def solve_quiz(email, secret, quiz_url):
    print(f"\n=== Solving quiz for: {quiz_url} ===")

    html = fetch_quiz_html(quiz_url)
    text = extract_question_text(html)

    print("\n--- FULL QUESTION RAW TEXT ---")
    print(text)
    print("-----------------------------------------")

    # --- SPECIAL CASE: UV PAGE ---
    if "project2-uv" in quiz_url:
        answer = handle_uv(text, email)
        # For UV questions, the submit URL is NOT on the UV page.
        # The submit URL is the previous quiz page, ALREADY KNOWN.
        submit_url = "https://tds-llm-analysis.s-anand.net/submit"

        print("\n[UV] Returning UV command as answer.")
        return {
            "email": email,
            "secret": secret,
            "url": quiz_url,
            "answer": answer
        }

    # Normal question
    answer = handle_question(text, quiz_url)

    # Extract submit URL
    submit_url = extract_submit_url(html, quiz_url)
    print("\nSubmit URL:", submit_url)

    # Payload
    payload = {
        "email": email,
        "secret": secret,
        "url": quiz_url,
        "answer": answer
    }

    print("\n--- SENDING ANSWER ---")
    print(json.dumps(payload, indent=2))

    resp = requests.post(submit_url, json=payload, timeout=25)
    print("\n--- SERVER RESPONSE ---")
    print(resp.text)

    try:
        resp_json = resp.json()
    except:
        return {"error": "Invalid JSON from server"}

    print("\nParsed:", resp_json)

    # If next quiz exists AND it's not a UV page → continue
    if resp_json.get("correct") and resp_json.get("url"):
        nxt = resp_json["url"]

        # DO NOT recurse into UV pages
        if "project2-uv" in nxt:
            print("\n[UV] Next UV instructions page detected, STOP recursion.")
            print("[UV] Your solver must POST the UV command as answer to the PREVIOUS page.")
            return resp_json

        print("\n➡️  NEXT QUIZ:", nxt)
        return solve_quiz(email, secret, nxt)

    return resp_json


# ----------------------------------------------------------
# EXTRACT TEXT
# ----------------------------------------------------------

def extract_question_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


# ----------------------------------------------------------
# SUBMIT URL EXTRACTOR
# ----------------------------------------------------------

def extract_submit_url(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    parts = text.split()

    for i, t in enumerate(parts):

        if t.startswith("https://") and t.endswith("/submit"):
            return t

        if t.startswith("https://") and i + 1 < len(parts) and parts[i+1] == "/submit":
            return t + "/submit"

        if t == "/submit":
            return urljoin(base_url, "/submit")

    raise ValueError("Submit URL not found")


# ----------------------------------------------------------
# MAIN QUESTION HANDLER
# ----------------------------------------------------------

def handle_question(text, quiz_url):

    # --- SCRAPE QUIZ ---
    if "/demo-scrape-data" in text or "Scrape" in text:
        return handle_scrape(text, quiz_url)

    # --- AUDIO QUIZ ---
    html = fetch_quiz_html(quiz_url)
    soup = BeautifulSoup(html, "html.parser")
    audio_tag = soup.find("audio")

    if audio_tag:
        src = audio_tag.get("src")
        if src:
            return handle_audio(quiz_url, src)

    # --- CSV QUIZ ---
    if "CSV" in text:
        return handle_csv(text, quiz_url)

    # --- DEFAULT ---
    print("\n[FALLBACK] Returning 123")
    return 123


# ----------------------------------------------------------
# UV HANDLER (VERY IMPORTANT)
# ----------------------------------------------------------

def handle_uv(text, email):
    print("\n====== UV QUESTION DETECTED ======")

    # They want a command like:
    # uv http get https://.../project2/uv.json?email=you -H "Accept: application/json"

    m = re.search(r"(https://[^\s]+/uv\.json\?email=[^\s]+)", text)
    if not m:
        print("[UV] Could not find uv.json URL")
        return "ERROR_NO_UV_URL"

    uv_url = m.group(1)

    command = f'uv http get "{uv_url}" -H "Accept: application/json"'
    print("\n[UV] Final UV command:", command)

    return command


# ----------------------------------------------------------
# SCRAPE HANDLER
# ----------------------------------------------------------

def handle_scrape(text, quiz_url):
    m = re.search(r"(/[\w\-]+\.?\w*\?[^ \n]+)", text)
    if not m:
        return None

    rel = m.group(1)
    full_url = urljoin(quiz_url, rel)

    print("[SCRAPE] Fetching:", full_url)

    html = fetch_quiz_html(full_url)
    soup = BeautifulSoup(html, "html.parser")

    nums = re.findall(r"\b\d+\b", soup.get_text(" ", strip=True))

    if not nums:
        return None

    code = max(nums, key=len)  # longest number
    print("[SCRAPE] Extracted code:", code)
    return code


# ----------------------------------------------------------
# AUDIO HANDLER
# ----------------------------------------------------------

def handle_audio(quiz_url, audio_href):
    print("\n[AUDIO] Handling audio quiz")

    full_url = urljoin(quiz_url, audio_href)
    print("[AUDIO] Downloading:", full_url)

    data = requests.get(full_url, timeout=30).content

    fname = "quiz_audio.wav"
    with open(fname, "wb") as f:
        f.write(data)

    print("[AUDIO] Saved:", fname)
    print("[AUDIO] Listen and enter number:")

    heard = input("Enter number from audio: ").strip()

    try:
        return int(heard)
    except:
        return heard


# ----------------------------------------------------------
# CSV HANDLER
# ----------------------------------------------------------

def handle_csv(text, quiz_url):
    print("\n[CSV] CSV detected")

    html = fetch_quiz_html(quiz_url)
    soup = BeautifulSoup(html, "html.parser")

    link = soup.find("a", href=lambda x: x and x.endswith(".csv"))
    if not link:
        print("[CSV] No CSV link found")
        return 0

    csv_url = urljoin(quiz_url, link["href"])
    print("[CSV] Downloading:", csv_url)

    resp = requests.get(csv_url, timeout=25)
    df = pd.read_csv(io.StringIO(resp.text))

    col = df.select_dtypes(include=["number"]).columns[0]

    # find cutoff
    m = re.search(r"Cutoff[:\s]+(\d+)", text)
    cutoff = int(m.group(1)) if m else None

    if cutoff:
        ans = df[df[col] < cutoff][col].sum()
        print(f"[CSV] FINAL ANSWER = sum(values < cutoff={cutoff}) = {ans}")
        return float(ans)

    return float(df[col].sum())
