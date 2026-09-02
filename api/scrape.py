import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, request, jsonify
from app import scrape_engine

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
@app.route("/api/scrape", methods=["GET", "POST"])
def handler():
    if request.method == "GET":
        return jsonify({"message": "Use POST with {'url': 'https://example.com'} to scrape links."})

    data = request.get_json(silent=True) or request.form.to_dict()
    if not data:
        return jsonify({"success": False, "error": "No payload provided."}), 400

    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "URL parameter is required."}), 400

    try:
        max_links = min(int(data.get("max_links", 100)), 1000)
    except (ValueError, TypeError):
        max_links = 100

    mode = data.get("mode", "crawl")
    same_domain_only = str(data.get("same_domain_only", "true")).lower() in ("true", "1", "yes", "on")

    try:
        result = scrape_engine(
            start_url=url,
            max_links=max_links,
            mode=mode,
            same_domain_only=same_domain_only,
            timeout_seconds=8.5,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
