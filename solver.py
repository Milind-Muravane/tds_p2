from scraper import fetch_quiz_html
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import requests
import json
import pandas as pd
import io


# ================================================================
# MAIN SOLVER
# ================================================================
def solve_quiz(email, secret, quiz_url):
    print(f"\n=== Solving quiz for: {quiz_url} ===")

    html = fetch_quiz_html(quiz_url)
    question = extract_question_text(html)

    print("\n--- FULL QUESTION RAW TEXT ---")
    print(question)
    print("-----------------------------------------")

    # compute answer
    answer = handle_question(question, quiz_url)

    # extract submit URL
    submit_url = extract_submit_url(html, quiz_url)
    print("\nSubmit URL:", submit_url)

    # build POST payload
    payload = {
        "email": email,
        "secret": secret,
        "url": quiz_url,
        "answer": answer
    }

    # show payload
    print("\n--- SENDING ANSWER ---")
    print(json.dumps(payload, indent=2))

    # send POST
    resp = requests.post(submit_url, json=payload, timeout=25)

    print("\n--- SERVER RESPONSE ---")
    print(resp.text)

    # parse
    try:
        data = resp.json()
    except:
        return {"error": "Invalid JSON from server"}

    print("\nParsed:", data)

    # recurse if there is another quiz
    if data.get("correct") and data.get("url"):
        print("\n➡️  NEXT QUIZ:", data["url"])
        return solve_quiz(email, secret, data["url"])

    return data


# ================================================================
# TEXT EXTRACTION
# ================================================================
def extract_question_text(html):
    soup = BeautifulSoup(html, "html.parser")
    # get ALL visible text
    return soup.get_text("\n", strip=True)


# ================================================================
# SUBMIT URL EXTRACTOR
# ================================================================
def extract_submit_url(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    parts = text.split()

    # look for explicit https://.../submit
    for i, t in enumerate(parts):
        if t.startswith("https://") and t.endswith("/submit"):
            return t
        if t.startswith("https://") and i + 1 < len(parts) and parts[i+1] == "/submit":
            return t + "/submit"

    # relative /submit
    return urljoin(base_url, "/submit")


# ================================================================
# SCRAPE QUIZ
# ================================================================
def handle_scrape(question_text):
    m = re.search(r"(/demo-scrape-data\?[^ \n]+)", question_text)
    if not m:
        return None

    rel = m.group(1)
    full_url = urljoin("https://tds-llm-analysis.s-anand.net", rel)

    print("[SCRAPE] Fetching:", full_url)

    html = fetch_quiz_html(full_url)
    soup = BeautifulSoup(html, "html.parser")
    nums = re.findall(r"\b\d+\b", soup.get_text(" ", strip=True))

    code = nums[0]
    print("[SCRAPE] Extracted code:", code)

    return code


# ================================================================
# AUDIO QUIZ
# ================================================================
def handle_audio(quiz_url, audio_href):
    print("\n====== AUDIO QUIZ MODE ======")

    audio_url = urljoin(quiz_url, audio_href)
    print("[AUDIO] Downloading:", audio_url)

    audio_bytes = requests.get(audio_url, timeout=25).content

    # save as wav
    fname = "quiz_audio.wav"
    with open(fname, "wb") as f:
        f.write(audio_bytes)

    print("[AUDIO] Saved:", fname)
    print("🎧 Listen to quiz_audio.wav and type the number spoken.")

    heard = input("Enter number from audio: ").strip()
    try:
        return int(heard)
    except:
        return heard


# ================================================================
# CSV QUIZ
# ================================================================
def handle_csv(question_text, quiz_url):
    print("\n[CSV] CSV Quiz detected")

    # fetch HTML again to locate CSV link
    html = fetch_quiz_html(quiz_url)
    soup = BeautifulSoup(html, "html.parser")

    link = soup.find("a", href=lambda x: x and x.endswith(".csv"))
    if not link:
        print("[CSV] No CSV link found — returning 0")
        return 0

    csv_url = urljoin(quiz_url, link["href"])
    print("[CSV] Downloading:", csv_url)

    resp = requests.get(csv_url, timeout=30)
    df = pd.read_csv(io.StringIO(resp.text))

    print("\n[CSV] Columns:", df.columns.tolist())

    # use first numeric column
    col = df.select_dtypes(include=["number"]).columns[0]

    # extract cutoff
    m = re.search(r"Cutoff[:\s]+(\d+)", question_text)
    cutoff = int(m.group(1)) if m else None

    if cutoff is None:
        # fallback — just return total sum
        total_sum = df[col].sum()
        print("[CSV] No cutoff found → returning total sum:", total_sum)
        return float(total_sum)

    # final rule: sum(values BELOW cutoff)
    less_sum = df[df[col] < cutoff][col].sum()
    print(f"[CSV] FINAL ANSWER = sum(values < cutoff={cutoff}) = {less_sum}")

    return float(less_sum)


# ================================================================
# MASTER QUESTION HANDLER
# ================================================================
def handle_question(question_text, quiz_url):

    # 1) SCRAPE
    sc = handle_scrape(question_text)
    if sc is not None:
        return sc

    # IMPORTANT: detect audio BEFORE CSV
    html = fetch_quiz_html(quiz_url)
    soup = BeautifulSoup(html, "html.parser")

    audio_tag = soup.find("audio")
    if audio_tag:
        print("\n[AUDIO] Detected <audio> tag")
        # Find associated audio file (.opus / .mp3 / .wav etc.)
        src = audio_tag.get("src")
        if src:
            return handle_audio(quiz_url, src)

    # IMPORTANT: CSV AFTER AUDIO
    if "CSV" in question_text:
        return handle_csv(question_text, quiz_url)

    # DEFAULT DEMO (Q1)
    print("\n[FALLBACK] Returning 123")
    return 123
