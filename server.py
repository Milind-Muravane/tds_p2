from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from solver import solve_quiz

load_dotenv()  # loads .env

app = Flask(__name__)
SECRET = os.getenv("TDS_SECRET")

@app.post("/")
def handle():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    if data.get("secret") != SECRET:
        return jsonify({"error": "Forbidden"}), 403

    quiz_url = data.get("url")
    email = data.get("email")

    result = solve_quiz(email, SECRET, quiz_url)
    return jsonify(result), 200

if __name__ == "__main__":
    app.run(port=8000)


