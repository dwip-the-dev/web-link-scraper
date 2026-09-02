import os
import re
import time
from urllib.parse import urljoin, urlparse
from collections import deque
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, send_file, Response, redirect, url_for
import io
import csv
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

# Realistic headers to avoid simple bot blocks
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MEDIA_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".mp4", ".webm", ".mp3", ".wav", ".zip", ".tar", ".gz", ".rar",
    ".docx", ".xlsx", ".pptx", ".csv", ".json", ".xml", ".txt"
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def get_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def get_base_domain(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) > 2:
        return ".".join(parts[-2:])
    return domain


def categorize_link(link_url: str, base_url: str, base_domain: str) -> str:
    if not link_url:
        return "other"
    
    parsed = urlparse(link_url)
    scheme = parsed.scheme.lower()
    
    if scheme in ("mailto", "tel", "sms", "javascript"):
        return "special"
        
    if not scheme and link_url.startswith("#"):
        return "anchor"
        
    link_domain = parsed.netloc.lower()
    
    # Check if media file
    path = parsed.path.lower()
    for ext in MEDIA_EXTENSIONS:
        if path.endswith(ext):
            return "media"
            
    if not link_domain or link_domain == base_domain:
        return "internal"
        
    # Check if subdomain
    if link_domain.endswith(f".{base_domain}") or (
        get_base_domain(link_domain) == get_base_domain(base_domain)
    ):
        return "subdomain"
        
    return "external"


def extract_links_from_html(html_content: str, current_url: str, base_domain: str) -> list:
    soup = BeautifulSoup(html_content, "html.parser")
    found_links = []
    
    # Extract standard <a> tags
    for tag in soup.find_all(["a", "link", "area"], href=True):
        raw_href = tag.get("href", "").strip()
        if not raw_href:
            continue
            
        # Get anchor/title text
        text = tag.get_text(separator=" ", strip=True)
        if not text:
            text = tag.get("title") or tag.get("aria-label") or ""
            if not text:
                img = tag.find("img")
                if img:
                    text = img.get("alt", "Image Link")
        
        # Clean text
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            text = "(No text)"
            
        # Handle javascript/mailto/tel directly
        if raw_href.startswith(("mailto:", "tel:", "sms:", "javascript:")):
            category = "special"
            found_links.append({
                "url": raw_href,
                "text": text,
                "type": category,
                "protocol": raw_href.split(":", 1)[0],
                "domain": "",
                "source_page": current_url,
            })
            continue

        # Handle in-page anchor
        if raw_href.startswith("#"):
            found_links.append({
                "url": urljoin(current_url, raw_href),
                "text": text,
                "type": "anchor",
                "protocol": urlparse(current_url).scheme,
                "domain": base_domain,
                "source_page": current_url,
            })
            continue

        absolute_url = urljoin(current_url, raw_href)
        parsed_target = urlparse(absolute_url)
        
        if parsed_target.scheme not in ("http", "https"):
            continue

        # Standardize URL (strip fragment for uniqueness or keep as is)
        target_domain = parsed_target.netloc.lower()
        category = categorize_link(absolute_url, current_url, base_domain)

        found_links.append({
            "url": absolute_url,
            "text": text,
            "type": category,
            "protocol": parsed_target.scheme,
            "domain": target_domain,
            "source_page": current_url,
        })

    return found_links


def scrape_engine(
    start_url: str,
    max_links: int = 100,
    mode: str = "crawl",  # 'single' or 'crawl'
    same_domain_only: bool = True,
    timeout_seconds: float = 8.0,
) -> dict:
    start_time = time.time()
    normalized_url = normalize_url(start_url)
    base_domain = get_domain(normalized_url)
    
    if not base_domain:
        raise ValueError("Invalid target URL provided.")

    visited_pages = set()
    queue = deque([normalized_url])
    discovered_urls = set()
    all_links_list = []
    
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    
    pages_crawled_count = 0

    while queue and len(all_links_list) < max_links:
        # Prevent serverless function timeout
        if (time.time() - start_time) >= timeout_seconds:
            break
            
        current_page_url = queue.popleft()
        if current_page_url in visited_pages:
            continue
            
        try:
            response = session.get(current_page_url, timeout=4, allow_redirects=True)
            visited_pages.add(current_page_url)
            pages_crawled_count += 1
            
            # Verify it is HTML content
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                continue

            extracted = extract_links_from_html(response.text, current_page_url, base_domain)
            
            for item in extracted:
                u = item["url"]
                if u not in discovered_urls:
                    discovered_urls.add(u)
                    all_links_list.append(item)
                    
                    if len(all_links_list) >= max_links:
                        break

                    # Enqueue for deeper crawl if mode == 'crawl'
                    if mode == "crawl":
                        item_type = item["type"]
                        # Only follow HTTP(S) HTML pages within same domain/subdomain
                        if item_type in ("internal", "subdomain") if same_domain_only else item_type in ("internal", "subdomain", "external"):
                            parsed_u = urlparse(u)
                            path_lower = parsed_u.path.lower()
                            is_media = any(path_lower.endswith(ext) for ext in MEDIA_EXTENSIONS)
                            if not is_media and u not in visited_pages and u not in queue:
                                queue.append(u)
                                
        except Exception:
            visited_pages.add(current_page_url)
            continue
            
        if mode == "single":
            break

    duration = round(time.time() - start_time, 2)
    
    # Calculate statistics
    type_counts = {"internal": 0, "external": 0, "subdomain": 0, "media": 0, "special": 0, "anchor": 0}
    unique_domains = set()
    
    for item in all_links_list:
        t = item.get("type", "other")
        type_counts[t] = type_counts.get(t, 0) + 1
        if item.get("domain"):
            unique_domains.add(item["domain"])

    return {
        "success": True,
        "target_url": normalized_url,
        "domain": base_domain,
        "stats": {
            "total": len(all_links_list),
            "internal": type_counts.get("internal", 0),
            "external": type_counts.get("external", 0),
            "subdomain": type_counts.get("subdomain", 0),
            "media": type_counts.get("media", 0),
            "special": type_counts.get("special", 0),
            "anchor": type_counts.get("anchor", 0),
            "unique_domains": len(unique_domains),
            "pages_crawled": pages_crawled_count,
            "duration_seconds": duration,
        },
        "links": all_links_list,
    }


# ==========================================
# WSGI Middleware for Vercel Rewrites
# ==========================================
class VercelPrefixMiddleware:
    """Handles Vercel Serverless Function rewrites where PATH_INFO may include /api/index"""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith("/api/index.py"):
            environ["PATH_INFO"] = path[len("/api/index.py"):] or "/"
        elif path.startswith("/api/index"):
            environ["PATH_INFO"] = path[len("/api/index"):] or "/"
        elif path == "/api":
            environ["PATH_INFO"] = "/"
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPrefixMiddleware(app.wsgi_app)


# ==========================================
# Routes & Unified Handler
# ==========================================

def handle_export():
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


@app.route("/", methods=["GET", "POST"])
@app.route("/<path:subpath>", methods=["GET", "POST"])
def unified_handler(subpath=""):
    path = (subpath or "").lower().strip("/")
    
    # 1. Health check
    if path.endswith("health"):
        return jsonify({
            "status": "healthy",
            "service": "web-link-scraper",
            "runtime": "vercel-python",
            "version": "2.0.0"
        })

    # 2. Export endpoint
    if path.endswith("export"):
        return handle_export()

    # 3. Scrape API endpoint (JSON request or /scrape path)
    json_data = request.get_json(silent=True)
    if json_data or path.endswith("scrape"):
        if request.method == "GET":
            return jsonify({"message": "Use POST with {'url': 'https://example.com'} to scrape links."})

        data = json_data or request.form.to_dict()
        url = (data.get("url") or "").strip()
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

    # 4. Standard HTML Form POST (Fallback for no-JS)
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        max_links = int(request.form.get("max_links", 100))
        mode = request.form.get("mode", "crawl")
        same_domain = request.form.get("same_domain") in ("on", "true")

        if not url:
            return render_template("index.html", error="Please enter a valid website URL.")

        try:
            results = scrape_engine(
                start_url=url,
                max_links=min(max_links, 500),
                mode=mode,
                same_domain_only=same_domain,
            )
            return render_template("index.html", initial_data=results)
        except Exception as e:
            return render_template("index.html", error=f"Scraping error: {str(e)}")

    # 5. Default: Render UI
    return render_template("index.html")



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


