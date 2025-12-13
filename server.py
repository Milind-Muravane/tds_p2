# server.py
from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from solver import solve_quiz
import traceback

load_dotenv()  # loads .env from project root

app = Flask(__name__)
SECRET = os.getenv("TDS_SECRET")

@app.post("/")
def handle():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    if SECRET is None:
        return jsonify({"error": "Server misconfigured: no secret"}), 500

    if data.get("secret") != SECRET:
        return jsonify({"error": "Forbidden"}), 403

    email = data.get("email")
    url = data.get("url")
    if not email or not url:
        return jsonify({"error": "Missing fields (email/url)"}), 400

    try:
        result = solve_quiz(email, SECRET, url)
        # solver returns JSON-like dict
        return jsonify(result), 200
    except Exception as e:
        tb = traceback.format_exc()
        print("ERROR in solve_quiz:", tb)
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
