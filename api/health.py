from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def handler():
    return jsonify({
        "status": "healthy",
        "service": "web-link-scraper",
        "runtime": "vercel-python",
        "version": "2.0.0"
    })

if __name__ == "__main__":
    app.run(debug=True)
