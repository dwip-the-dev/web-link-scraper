import io
import csv
import json
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

@app.route("/", methods=["POST"])
@app.route("/api/export", methods=["POST"])
def handler():
    try:
        data = request.get_json(silent=True) or {}
        links = data.get("links", [])
        format_type = data.get("format", "txt").lower()
        filename = data.get("filename", "scraped_links")

        if format_type == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["url", "text", "type", "protocol", "domain", "source_page"])
            writer.writeheader()
            for link in links:
                writer.writerow({
                    "url": link.get("url", ""),
                    "text": link.get("text", ""),
                    "type": link.get("type", ""),
                    "protocol": link.get("protocol", ""),
                    "domain": link.get("domain", ""),
                    "source_page": link.get("source_page", ""),
                })
            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}.csv"}
            )

        elif format_type == "json":
            return Response(
                json.dumps(links, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}.json"}
            )

        else:  # txt
            urls = [link.get("url", "") for link in links if link.get("url")]
            content = "\n".join(urls)
            return Response(
                content,
                mimetype="text/plain",
                headers={"Content-Disposition": f"attachment; filename={filename}.txt"}
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(debug=True)
