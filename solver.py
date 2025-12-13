# solver.py
from scraper import fetch_quiz_html
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import requests
import json
import pandas as pd
import io
import time

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"error": "Invalid JSON from server", "text": resp.text}

def solve_quiz(email, secret, quiz_url):
    """
    Main entry: fetch quiz page, decide how to answer, submit, and optionally follow next URL.
    UV instruction pages are handled (solver returns UV command as answer payload), and recursion stops for UV.
    """
    print(f"\n=== Solving quiz for: {quiz_url} ===")
    html = fetch_quiz_html(quiz_url)
    text = extract_question_text(html)
    print("\n--- FULL QUESTION RAW TEXT ---")
    print(text)
    print("-----------------------------------------")

    # If URL or page indicates a UV instruction, create UV command and return payload to be posted
    if "project2-uv" in quiz_url or re.search(r"\buv\b.*project2", text, re.I):
        uv_command = handle_uv(text, email)
        # We return the exact payload expected by the server so server.py can jsonify it
        return {
            "email": email,
            "secret": secret,
            "url": quiz_url,
            "answer": uv_command
        }

    # Otherwise, handle typical quiz types
    answer = handle_question(text, quiz_url)

    # find submit url
    submit_url = extract_submit_url(html, quiz_url)
    print("\nSubmit URL:", submit_url)

    payload = {
        "email": email,
        "secret": secret,
        "url": quiz_url,
        "answer": answer
    }

    print("\n--- SENDING ANSWER ---")
    print(json.dumps(payload, indent=2))

    resp = requests.post(submit_url, json=payload, timeout=30)
    print("\n--- SERVER RESPONSE ---")
    print(resp.text)

    resp_json = safe_json(resp)
    print("\nParsed:", resp_json)

    # honor delay if requested
    delay = resp_json.get("delay")
    if isinstance(delay, (int, float)) and delay > 0:
        print(f"[INFO] Server asked for delay: sleeping {delay}s")
        time.sleep(delay)

    # If correct and new URL present, follow (but stop recursion if next is UV)
    if resp_json.get("correct") and resp_json.get("url"):
        nxt = resp_json["url"]
        if "project2-uv" in nxt or re.search(r"/uv\b", nxt):
            print("\n[UV] Next UV instructions page detected, STOP recursion.")
            print("[UV] Your solver must POST the UV command as answer to the PREVIOUS page.")
            return resp_json
        print("\n➡️  NEXT QUIZ:", nxt)
        return solve_quiz(email, secret, nxt)

    return resp_json

# ---------- Utilities ----------

def extract_question_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style"]):
        s.extract()
    return soup.get_text("\n", strip=True)

def extract_submit_url(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # 1) full https://.../submit
    m = re.search(r"https?://[^\s\"']+/submit\b", text)
    if m:
        return m.group(0)

    # 2) host token + '/submit'
    tokens = text.split()
    for i, t in enumerate(tokens):
        if t.startswith("https://") or t.startswith("http://"):
            if i+1 < len(tokens) and tokens[i+1].strip().startswith("/submit"):
                return tokens[i].rstrip() + "/submit"

    # 3) literal '/submit' -> join origin of base_url
    if "/submit" in text and base_url:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin + "/submit"

    # 4) anchors or forms
    a = soup.find("a", href=lambda x: x and "/submit" in x)
    if a and a.get("href"):
        return urljoin(base_url, a["href"])
    form = soup.find("form", action=lambda x: x and "/submit" in x)
    if form and form.get("action"):
        return urljoin(base_url, form["action"])

    # 5) spans with class origin (some pages set origin via JS)
    origin_spans = soup.find_all("span", class_="origin")
    if origin_spans and base_url:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin + "/submit"

    raise ValueError("Submit URL not found")

# ---------- Handlers ----------

def handle_question(text, quiz_url):
    # SCRAPE detection
    if "Scrape" in text or "/demo-scrape-data" in text or re.search(r"/demo-scrape-data\?[^ \n]+", text):
        return handle_scrape(text, quiz_url)

    # CSV detection
    if "CSV" in text:
        return handle_csv(text, quiz_url)

    # AUDIO detection via <audio> tag (we fetch page to check)
    html = fetch_quiz_html(quiz_url)
    soup = BeautifulSoup(html, "html.parser")
    audio_tag = soup.find("audio")
    if audio_tag is not None:
        src = audio_tag.get("src")
        if src:
            return handle_audio(quiz_url, src)

    # fallback numeric answer
    print("\n[FALLBACK] Returning 123")
    return 123

def handle_uv(text, email):
    """
    Build UV command string. Prefer explicit uv.json URL in text; otherwise construct it.
    Returns a single-line command string exactly as required.
    """
    print("\n====== UV QUESTION DETECTED ======")
    m = re.search(r"(https?://[^\s\"']+/project2/uv\.json\?email=[^\s\"']+)", text)
    if m:
        uv_url = m.group(1)
    else:
        m2 = re.search(r"https?://[^\s\"']+", text)
        if m2:
            base = m2.group(0).rstrip("/")
            uv_url = f"{base}/project2/uv.json?email={email}"
        else:
            uv_url = f"https://tds-llm-analysis.s-anand.net/project2/uv.json?email={email}"

    cmd = f'uv http get "{uv_url}" -H "Accept: application/json"'
    print("[UV] Command string:", cmd)
    return cmd

def handle_scrape(text, quiz_url):
    m = re.search(r"(/demo-scrape-data\?[^ \n\"']+)", text)
    if not m:
        m = re.search(r"(/[a-zA-Z0-9_\-./]+\?[^ \n\"']+)", text)
        if not m:
            return None
    rel = m.group(1)
    full = urljoin(quiz_url, rel)
    print("[SCRAPE] Fetching:", full)
    html = fetch_quiz_html(full)
    soup = BeautifulSoup(html, "html.parser")
    nums = re.findall(r"\b\d+\b", soup.get_text(" ", strip=True))
    if not nums:
        return None
    text2 = soup.get_text(" ", strip=True)
    ctx = re.search(r"(?:code|secret|secret code|verification)\D{0,30}(\d{2,})", text2, re.I)
    if ctx:
        code = ctx.group(1)
    else:
        code = max(nums, key=len)
    print("[SCRAPE] Extracted code:", code)
    return code

def handle_audio(quiz_url, audio_href):
    print("\n[AUDIO] Detected audio tag")
    full_url = urljoin(quiz_url, audio_href)
    print("[AUDIO] Downloading:", full_url)
    resp = requests.get(full_url, timeout=30)
    resp.raise_for_status()
    fname = "quiz_audio.wav"
    with open(fname, "wb") as f:
        f.write(resp.content)
    print(f"[AUDIO] Saved local file: {fname}")
    print("[AUDIO] Please play the file and enter the number that is spoken (manual step).")
    heard = input("Enter number from audio: ").strip()
    try:
        return int(heard)
    except:
        return heard

def handle_csv(text, quiz_url):
    print("\n[CSV] CSV quiz detected")
    html = fetch_quiz_html(quiz_url)
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("a", href=lambda x: x and x.lower().endswith(".csv"))
    if not link:
        print("[CSV] No CSV link found")
        return 0
    csv_url = urljoin(quiz_url, link["href"])
    print("[CSV] Downloading CSV:", csv_url)
    resp = requests.get(csv_url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    nums = df.select_dtypes(include=["number"]).columns.tolist()
    if not nums:
        col = df.columns[0]
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    else:
        col = nums[0]
    m = re.search(r"Cutoff[:\s]+(\d+)", text)
    cutoff = int(m.group(1)) if m else None
    if cutoff is not None:
        less_sum = df[df[col] < cutoff][col].sum()
        print(f"[CSV] FINAL ANSWER = sum(values < cutoff={cutoff}) = {less_sum}")
        return float(less_sum)
    total = df[col].sum()
    print(f"[CSV] FINAL ANSWER = total sum = {total}")
    return float(total)
