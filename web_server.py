#!/usr/bin/env python3
"""Combined server: Web UI + API proxy"""
from flask import Flask, jsonify, send_from_directory, Response, request
from flask_cors import CORS
import os
import json
import requests
import re
import hashlib
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder='/root/VesTool/webui/build', static_url_path='')
CORS(app)

DATA_DIR = '/root/VesTool/data'
BUILD_DIR = '/root/VesTool/webui/build'

# Headers giả lập browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# ============ Proxy Download Helpers ============

def resolve_uptodown_url(url):
    """Resolve Uptodown download URL to actual APK link."""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # If it's already a direct download link
        if '/download/' in url and url.endswith(tuple('0123456789')):
            # Go to download page
            r = session.get(url, timeout=30, allow_redirects=True)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Find actual download button
            btn = soup.select_one('button#detail-download-button[data-url]')
            if btn:
                data_url = btn.get('data-url')
                if data_url:
                    return f'https://dw.uptodown.com/dwn/{data_url}', session
            
            # Alternative: direct link
            link = soup.select_one('a[href*="dw.uptodown.com"]')
            if link:
                return link.get('href'), session
        
        return url, session
    except Exception as e:
        print(f'Uptodown resolve error: {e}')
        return url, None

def resolve_apkpure_url(url):
    """Resolve APKPure URL to actual APK link."""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # Go to download page
        if '/download' not in url:
            url = url.rstrip('/') + '/download'
        
        r = session.get(url, timeout=30)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Find download link
        link = soup.select_one('a#download_link[href]') or soup.select_one('a[href$=".apk"]')
        if link:
            href = link.get('href')
            if href.startswith('/'):
                href = 'https://apkpure.com' + href
            return href, session
        
        return url, session
    except Exception as e:
        print(f'APKPure resolve error: {e}')
        return url, None

def resolve_download_url(url):
    """Resolve any APK source URL to direct download link."""
    if 'uptodown.com' in url:
        return resolve_uptodown_url(url)
    elif 'apkpure.com' in url:
        return resolve_apkpure_url(url)
    elif 't.me/' in url:
        # Telegram link - return as-is, need different handling
        return url, None
    else:
        return url, None

# ============ API Routes ============

@app.route('/api/apps')
def get_apps():
    """Serve apps.json"""
    apps_file = os.path.join(DATA_DIR, 'apps.json')
    if not os.path.exists(apps_file):
        return jsonify([])
    with open(apps_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.route('/api/versions/<app_id>')
def get_versions(app_id):
    """Serve version data for an app"""
    safe_id = app_id.replace('.', '_')
    version_file = os.path.join(DATA_DIR, 'versions', f'{safe_id}.json')
    if not os.path.exists(version_file):
        return jsonify([])
    with open(version_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.route('/api/apk/<filename>')
def serve_apk(filename):
    """Serve APK files"""
    apk_dir = os.path.join(DATA_DIR, 'apks')
    filepath = os.path.join(apk_dir, filename)
    if not os.path.exists(filepath):
        return "Not found", 404
    
    def generate():
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                yield chunk
    
    file_size = os.path.getsize(filepath)
    return Response(
        generate(),
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(file_size),
            'Content-Type': 'application/vnd.android.package-archive',
        }
    )

@app.route('/data/<path:path>')
def serve_data(path):
    """Serve data files"""
    return send_from_directory(DATA_DIR, path)


@app.route('/api/proxy-download')
def proxy_download():
    """Proxy download APK từ uptodown/apkpure qua VPS.
    
    Stream trực tiếp - không lưu file - tiết kiệm RAM.
    Usage: /api/proxy-download?url=https://...&name=app.apk
    """
    url = request.args.get('url', '')
    filename = request.args.get('name', 'app.apk')
    
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400
    
    # Nếu là link Telegram, trả về redirect
    if 't.me/' in url:
        return jsonify({'redirect': url, 'type': 'telegram'})
    
    try:
        # Resolve actual download URL
        direct_url, session = resolve_download_url(url)
        if not direct_url:
            return jsonify({'error': 'Cannot resolve download URL'}), 400
        
        if not session:
            session = requests.Session()
            session.headers.update(HEADERS)
        
        print(f'Proxy download: {url[:60]}...')
        print(f'  Direct URL: {direct_url[:80]}...')
        
        # Stream download với GET (không dùng HEAD vì một số server không hỗ trợ)
        def generate():
            try:
                with session.get(direct_url, stream=True, timeout=1800, allow_redirects=True) as r:
                    r.raise_for_status()
                    content_type = r.headers.get('Content-Type', '')
                    # Kiểm tra có phải APK không
                    if 'text/html' in content_type:
                        print(f'  Warning: Got HTML instead of APK')
                        # Có thể là trang captcha hoặc error
                        return
                    
                    total = 0
                    for chunk in r.iter_content(chunk_size=1024*1024):  # 1MB chunks
                        if chunk:
                            total += len(chunk)
                            yield chunk
                    print(f'  Downloaded: {total / 1024 / 1024:.1f} MB')
            except Exception as e:
                print(f'  Stream error: {e}')
        
        # Response headers - không set Content-Length vì không biết trước
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'application/vnd.android.package-archive',
            'Transfer-Encoding': 'chunked',
        }
        
        return Response(
            generate(),
            headers=headers,
            mimetype='application/vnd.android.package-archive'
        )
        
    except Exception as e:
        print(f'Proxy download error: {e}')
        return jsonify({'error': str(e)}), 500


# ============ Web UI Routes ============

@app.route('/')
def serve_index():
    return send_from_directory(BUILD_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    # Try to serve static file
    filepath = os.path.join(BUILD_DIR, path)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return send_from_directory(BUILD_DIR, path)
    # Fallback to index.html for SPA routing
    return send_from_directory(BUILD_DIR, 'index.html')

if __name__ == '__main__':
    print("="*60)
    print("VesTool Combined Server")
    print("="*60)
    print(f"Web UI: http://0.0.0.0:8005")
    print(f"API:    http://0.0.0.0:8005/api/apps")
    print("="*60)
    app.run(host='0.0.0.0', port=8005, debug=False, threaded=True)
