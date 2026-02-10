#!/usr/bin/env python3
"""Combined server: Web UI + API proxy + On-demand APK Download"""
from flask import Flask, jsonify, send_from_directory, Response, request, redirect
from flask_cors import CORS
import os
import sys
import json
import requests
import re
import hashlib
import time
import threading
from bs4 import BeautifulSoup
from urllib.parse import quote
from dotenv import load_dotenv

# Load .env file
load_dotenv('/root/VesTool/.env')

# Import Telegram metadata reader
try:
    sys.path.insert(0, '/root/VesTool/bots')
    from telegram_metadata import fetch_apps_from_telegram, sync_telegram_to_local
    TELEGRAM_METADATA_AVAILABLE = True
except ImportError:
    TELEGRAM_METADATA_AVAILABLE = False
    def fetch_apps_from_telegram(): return []
    def sync_telegram_to_local(): pass

# Track ongoing downloads to prevent duplicates
_download_in_progress = {}
_download_lock = threading.Lock()

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

TG_API_BASE = os.environ.get('TG_API_BASE', 'http://localhost:8081').rstrip('/')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
STREAM_SERVER_URL = (os.environ.get('STREAM_SERVER_URL') or os.environ.get('TELEGRAM_STREAM_URL') or '').rstrip('/')


def _parse_telegram_link(link):
    match = re.search(r't\.me/(?:c/)?(\d+)/(\d+)', link)
    if not match:
        return None, None
    channel_digits, message_id = match.groups()
    channel_id = f'-100{channel_digits}' if '/c/' in link else channel_digits
    return channel_id, int(message_id)


def _tg_api_call(method, payload):
    if not TG_BOT_TOKEN:
        return None
    url = f'{TG_API_BASE}/bot{TG_BOT_TOKEN}/{method}'
    try:
        resp = requests.post(url, json=payload, timeout=300)
        if resp.ok:
            data = resp.json()
            if data.get('ok'):
                return data.get('result')
            print(f'TG API error {method}: {data}')
        else:
            print(f'TG API HTTP {method}: {resp.status_code} {resp.text[:200]}')
    except Exception as e:
        print(f'TG API call failed {method}: {e}')
    return None


def _stream_via_stream_server(channel_id, message_id, filename):
    if not STREAM_SERVER_URL:
        return None
    safe_name = quote(filename or 'app.apk')
    stream_url = f'{STREAM_SERVER_URL}/stream/{message_id}?channel={channel_id}&name={safe_name}'
    try:
        upstream = requests.get(stream_url, stream=True, timeout=1800)
        upstream.raise_for_status()
    except Exception as e:
        print(f'Stream server error: {e}')
        return None

    content_type = upstream.headers.get('Content-Type', 'application/vnd.android.package-archive')
    disposition = upstream.headers.get('Content-Disposition', f'attachment; filename="{filename or "app.apk"}"')
    content_length = upstream.headers.get('Content-Length')

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    headers = {
        'Content-Disposition': disposition,
        'Content-Type': content_type,
    }
    if content_length:
        headers['Content-Length'] = content_length
    return Response(generate(), headers=headers, mimetype=content_type)


def _stream_via_bot_api(channel_id, message_id, filename):
    if not TG_BOT_TOKEN:
        return None

    forwarded = _tg_api_call('forwardMessage', {
        'chat_id': channel_id,
        'from_chat_id': channel_id,
        'message_id': message_id,
    })
    if not forwarded:
        return None

    new_msg_id = forwarded.get('message_id')
    document = forwarded.get('document') or {}
    if not document.get('file_id'):
        if new_msg_id:
            _tg_api_call('deleteMessage', {'chat_id': channel_id, 'message_id': new_msg_id})
        return None

    file_id = document['file_id']
    file_name = document.get('file_name') or filename or 'download.apk'
    file_size = document.get('file_size')

    file_info = _tg_api_call('getFile', {'file_id': file_id})
    if new_msg_id:
        _tg_api_call('deleteMessage', {'chat_id': channel_id, 'message_id': new_msg_id})
    if not file_info or not file_info.get('file_path'):
        return None

    file_path = file_info['file_path']
    file_url = f'{TG_API_BASE}/file/bot{TG_BOT_TOKEN}/{file_path}'
    try:
        upstream = requests.get(file_url, stream=True, timeout=1800)
        upstream.raise_for_status()
    except Exception as e:
        print(f'Telegram file stream error: {e}')
        return None

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    headers = {
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Type': 'application/vnd.android.package-archive',
    }
    if file_size:
        headers['Content-Length'] = str(file_size)
    return Response(generate(), headers=headers, mimetype='application/vnd.android.package-archive')

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
    """Serve apps data - with Telegram fallback and real-time sync"""
    apps_file = os.path.join(DATA_DIR, 'apps.json')
    
    # Try local file first
    if os.path.exists(apps_file):
        try:
            with open(apps_file, 'r', encoding='utf-8') as f:
                local_apps = json.load(f)
                
            # If file is recent (< 1 hour), use it
            file_age = time.time() - os.path.getmtime(apps_file)
            if file_age < 3600:  # 1 hour
                return jsonify(local_apps)
                
        except Exception as e:
            print(f'Error reading local apps: {e}')
    
    # If local file missing/old, try Telegram sync
    if TELEGRAM_METADATA_AVAILABLE:
        try:
            print('🔄 Syncing apps from Telegram metadata...')
            sync_telegram_to_local()
            
            # Try reading again after sync
            if os.path.exists(apps_file):
                with open(apps_file, 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
        except Exception as e:
            print(f'Telegram sync error: {e}')
    
    # Fallback: empty list
    return jsonify([])

@app.route('/api/apps/sync')
def sync_apps():
    """Manual sync trigger from Telegram metadata"""
    if not TELEGRAM_METADATA_AVAILABLE:
        return jsonify({'error': 'Telegram metadata not available'}), 503
    
    try:
        sync_telegram_to_local()
        return jsonify({'status': 'success', 'message': 'Synced from Telegram'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/versions/<app_id>')
def get_versions(app_id):
    """Serve version data for an app"""
    safe_id = app_id.replace('.', '_')
    version_file = os.path.join(DATA_DIR, 'versions', f'{safe_id}.json')
    if not os.path.exists(version_file):
        return jsonify([])
    with open(version_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Handle both old format (array) and new format (object with versions key)
        if isinstance(data, list):
            return jsonify(data)
        elif isinstance(data, dict) and 'versions' in data:
            return jsonify(data['versions'])
        else:
            return jsonify([])

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


@app.route('/api/download')
def download_from_telegram():
    """Directly stream Telegram files so users don't leave the site."""
    link = request.args.get('link', '')
    filename = request.args.get('name', 'app.apk')
    use_stream = request.args.get('stream', '1') != '0'

    if not link:
        return jsonify({'error': 'Missing link parameter'}), 400

    if 't.me' not in link:
        return redirect(link)

    channel_id, message_id = _parse_telegram_link(link)
    if not channel_id or not message_id:
        return redirect(link)

    response = None
    if use_stream:
        response = _stream_via_stream_server(channel_id, message_id, filename)
    if not response:
        response = _stream_via_bot_api(channel_id, message_id, filename)
    if response:
        return response

    # Fallback: send user to Telegram if we couldn't stream
    print(f'⚠️ Falling back to Telegram link for message {message_id}')
    return redirect(link)


@app.route('/api/get-apk/<app_id>')
def get_apk_smart(app_id):
    """
    Smart APK download endpoint.
    
    Flow:
    1. Check if APK exists in Telegram cache
    2. If YES: Stream from Telegram
    3. If NO: Download from source → Upload to Telegram → Stream to user
    
    User always gets direct download - never sees Telegram.
    """
    if not ONDEMAND_AVAILABLE:
        return jsonify({'error': 'On-demand download not available'}), 503
    
    # Check if download already in progress for this app
    with _download_lock:
        if app_id in _download_in_progress:
            return jsonify({
                'status': 'downloading',
                'message': 'APK đang được tải, vui lòng đợi...',
                'retry_after': 10
            }), 202
        _download_in_progress[app_id] = True
    
    try:
        # Get APK (from cache or download on-demand)
        result = get_apk_for_download(app_id)
        
        if result['status'] == 'error':
            return jsonify(result), 400
        
        tg_link = result.get('telegram_link')
        if not tg_link:
            return jsonify({'error': 'No download available'}), 404
        
        # Parse and stream from Telegram
        channel_id, message_id = _parse_telegram_link(tg_link)
        if not channel_id or not message_id:
            return jsonify({'error': 'Invalid Telegram link'}), 500
        
        # Build filename
        safe_name = app_id.replace('.', '_') + '.apk'
        
        # Try streaming
        response = _stream_via_stream_server(channel_id, message_id, safe_name)
        if not response:
            response = _stream_via_bot_api(channel_id, message_id, safe_name)
        
        if response:
            return response
        
        # Last resort: redirect to Telegram (shouldn't happen normally)
        return redirect(tg_link)
        
    finally:
        with _download_lock:
            _download_in_progress.pop(app_id, None)


@app.route('/api/download-status/<app_id>')
def download_status(app_id):
    """Check if APK is ready for download."""
    apps_file = os.path.join(DATA_DIR, 'apps.json')
    if not os.path.exists(apps_file):
        return jsonify({'status': 'not_found'})
    
    with open(apps_file, 'r', encoding='utf-8') as f:
        apps = json.load(f)
    
    for app in apps:
        if app.get('app_id') == app_id:
            tg_link = app.get('telegram_link') or app.get('local_apk_url')
            if tg_link and 't.me' in tg_link:
                return jsonify({
                    'status': 'ready',
                    'has_apk': True,
                    'size_mb': app.get('apk_size_mb', 0)
                })
            else:
                return jsonify({
                    'status': 'pending',
                    'has_apk': False,
                    'uptodown_url': app.get('uptodown_url', '')
                })
    
    return jsonify({'status': 'not_found'})


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
