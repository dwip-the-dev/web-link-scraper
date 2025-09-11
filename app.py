import os
from flask import Flask, render_template, request, send_file, redirect, url_for
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
from collections import deque

app = Flask(__name__)

# File to store scraped links for each website
LINKS_FILE = 'scraped_links.json'

def load_scraped_links():
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_scraped_links(links):
    serializable_links = {domain: list(link_set) for domain, link_set in links.items()}
    with open(LINKS_FILE, 'w') as f:
        json.dump(serializable_links, f)

def get_domain(url):
    return urlparse(url).netloc

def crawl_website(start_url, max_links):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    
    domain = get_domain(start_url)
    visited = set()
    queue = deque([start_url])
    all_links = set()
    
    while queue and len(all_links) < max_links:
        url = queue.popleft()
        
        if url in visited:
            continue
            
        try:
            time.sleep(0)  # 1.5-second delay
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
        except:
            continue
            
        soup = BeautifulSoup(response.text, 'html.parser')
        visited.add(url)
        
        for a_tag in soup.find_all('a', href=True):
            if len(all_links) >= max_links:
                break
            href = a_tag['href']
            absolute_url = urljoin(url, href)
            
            # Only follow links from the same domain
            if get_domain(absolute_url) == domain and absolute_url not in all_links:
                all_links.add(absolute_url)
                queue.append(absolute_url)
                
    return sorted(all_links)[:max_links]

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        max_links = int(request.form.get('max_links', 100000))  # Max 100,000 links
        
        if not url:
            return render_template('index.html', error='Please enter a URL')
        
        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = f'http://{url}'
        
        domain = get_domain(url)
        scraped_links = load_scraped_links()
        existing_links = set(scraped_links.get(domain, []))
        
        try:
            # Crawl the entire website
            new_links = crawl_website(url, max_links)
            unique_links = list(set(new_links) - existing_links)
            
            # Save new links
            scraped_links[domain] = existing_links.union(unique_links)
            save_scraped_links(scraped_links)
            
            # Save to output file
            with open('output_links.txt', 'w') as f:
                f.write("\n".join(unique_links))
            
            return redirect(url_for('result', count=len(unique_links), url=url))
        except Exception as e:
            return render_template('index.html', error=f'Error: {str(e)}')
    
    return render_template('index.html')

@app.route('/result')
def result():
    count = request.args.get('count', 0)
    url = request.args.get('url', '')
    return render_template('result.html', count=count, url=url)

@app.route('/download')
def download():
    return send_file('output_links.txt',
                     as_attachment=True,
                     download_name='output_links.txt')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
