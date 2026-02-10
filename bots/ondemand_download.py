#!/usr/bin/env python3
"""
On-Demand APK Download Service

Flow:
1. User requests APK download
2. Check if APK already in Telegram (telegram_link exists)
3. If YES: Stream directly from Telegram via VPS
4. If NO: Download from source → Upload to Telegram → Update JSON → Stream to user

Tất cả đều qua VPS, user không bao giờ thấy Telegram link trực tiếp.
"""

import os
import json
import time
import hashlib
import tempfile
import requests
import threading
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load .env file
load_dotenv('/root/VesTool/.env')

# ============ CONFIG ============
DATA_DIR = '/root/VesTool/data'
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')
TMP_DIR = '/tmp/vestool_downloads'

TG_API_BASE = os.environ.get('TG_API_BASE', 'http://localhost:8081').rstrip('/')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Lock for updating apps.json
_apps_lock = threading.Lock()

# In-memory cache của apps
_apps_cache = None
_apps_cache_time = 0
CACHE_TTL = 60  # Refresh cache mỗi 60s


def get_apps_data():
    """Load apps data with caching."""
    global _apps_cache, _apps_cache_time
    
    now = time.time()
    if _apps_cache and (now - _apps_cache_time) < CACHE_TTL:
        return _apps_cache
    
    if not os.path.exists(APPS_FILE):
        return {}
    
    try:
        with open(APPS_FILE, 'r', encoding='utf-8') as f:
            apps_list = json.load(f)
        
        _apps_cache = {app['app_id']: app for app in apps_list}
        _apps_cache_time = now
        return _apps_cache
    except Exception as e:
        print(f'Error loading apps: {e}')
        return {}


def update_app_data(app_id, updates):
    """Update app data in apps.json."""
    global _apps_cache, _apps_cache_time
    
    with _apps_lock:
        try:
            # Load current data
            apps_list = []
            if os.path.exists(APPS_FILE):
                with open(APPS_FILE, 'r', encoding='utf-8') as f:
                    apps_list = json.load(f)
            
            # Find and update app
            found = False
            for app in apps_list:
                if app.get('app_id') == app_id:
                    app.update(updates)
                    app['date'] = datetime.now().isoformat()
                    found = True
                    break
            
            if not found:
                # Add new app
                new_app = {'app_id': app_id, **updates, 'date': datetime.now().isoformat()}
                apps_list.insert(0, new_app)
            
            # Save
            with open(APPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(apps_list, f, ensure_ascii=False, indent=2)
            
            # Invalidate cache
            _apps_cache = None
            _apps_cache_time = 0
            
            return True
        except Exception as e:
            print(f'Error updating app data: {e}')
            return False


# ============ UPTODOWN HELPERS ============

def resolve_uptodown_download_url(uptodown_url):
    """Get actual APK download URL from Uptodown page."""
    session = requests.Session()
    session.headers.update(HEADERS)
    
    try:
        # Go to download page
        download_page = uptodown_url.rstrip('/') + '/download' if '/download' not in uptodown_url else uptodown_url
        
        resp = session.get(download_page, timeout=30)
        if resp.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find download button with data-url
        btn = soup.select_one('button#detail-download-button[data-url]')
        if btn:
            data_url = btn.get('data-url')
            if data_url and not data_url.startswith(('http', '/')):
                apk_url = f'https://dw.uptodown.com/dwn/{data_url}'
                return apk_url, session
        
        # Alternative: find direct link
        link = soup.select_one('a[href*="dw.uptodown.com"]')
        if link:
            return link.get('href'), session
        
        return None, session
    except Exception as e:
        print(f'Error resolving Uptodown URL: {e}')
        return None, None


def download_apk_file(url, app_id, session=None):
    """Download APK file to temp directory."""
    os.makedirs(TMP_DIR, exist_ok=True)
    
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
    
    safe_name = app_id.replace('.', '_')
    hash_suffix = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f'{safe_name}_{hash_suffix}.apk'
    filepath = os.path.join(TMP_DIR, filename)
    
    try:
        print(f'📥 Downloading: {url[:80]}...')
        resp = session.get(url, stream=True, timeout=300, allow_redirects=True)
        resp.raise_for_status()
        
        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print(f'⚠️ Got HTML instead of APK')
            return None
        
        total_size = 0
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
        
        if total_size < 10000:  # < 10KB
            print(f'⚠️ File too small: {total_size} bytes')
            os.remove(filepath)
            return None
        
        print(f'✅ Downloaded: {total_size / 1024 / 1024:.1f} MB')
        return filepath
    except Exception as e:
        print(f'❌ Download error: {e}')
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        return None


# ============ TELEGRAM HELPERS ============

def _tg_api_call(method, **kwargs):
    """Call Telegram Bot API."""
    if not TG_BOT_TOKEN:
        return None
    
    url = f'{TG_API_BASE}/bot{TG_BOT_TOKEN}/{method}'
    
    try:
        if 'json' in kwargs:
            resp = requests.post(url, json=kwargs['json'], timeout=300)
        elif 'data' in kwargs or 'files' in kwargs:
            resp = requests.post(url, data=kwargs.get('data'), files=kwargs.get('files'), timeout=1800)
        else:
            resp = requests.post(url, timeout=300)
        
        if resp.ok:
            result = resp.json()
            if result.get('ok'):
                return result.get('result')
            print(f'TG API error: {result}')
        else:
            print(f'TG API HTTP {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        print(f'TG API call error: {e}')
    
    return None


def _tg_message_link(chat_id, message_id):
    """Build Telegram message link."""
    cid = str(chat_id)
    if cid.startswith('-100'):
        return f'https://t.me/c/{cid[4:]}/{message_id}'
    return f'https://t.me/c/{cid.lstrip("-")}/{message_id}'


def upload_to_telegram(filepath, app_title='', app_id=''):
    """Upload APK to Telegram channel."""
    if not TG_BOT_TOKEN or not TG_CHANNEL_ID:
        print('⚠️ Missing Telegram credentials')
        return None, 0
    
    file_size = os.path.getsize(filepath)
    size_mb = file_size / 1024 / 1024
    filename = os.path.basename(filepath)
    
    caption = f'📦 <b>{app_title}</b>\n'
    if app_id:
        caption += f'📱 <code>{app_id}</code>\n'
    caption += f'💾 {size_mb:.1f} MB'
    
    print(f'📤 Uploading to Telegram: {filename} ({size_mb:.1f} MB)...')
    
    try:
        with open(filepath, 'rb') as f:
            result = _tg_api_call(
                'sendDocument',
                data={
                    'chat_id': TG_CHANNEL_ID,
                    'caption': caption[:1024],
                    'parse_mode': 'HTML',
                },
                files={
                    'document': (filename, f, 'application/vnd.android.package-archive')
                }
            )
        
        if result:
            msg_id = result.get('message_id')
            link = _tg_message_link(TG_CHANNEL_ID, msg_id)
            print(f'✅ Uploaded: {link}')
            return link, size_mb
        
        print('❌ Upload failed')
        return None, size_mb
    except Exception as e:
        print(f'❌ Upload error: {e}')
        return None, size_mb


# ============ MAIN ON-DEMAND FUNCTION ============

def get_apk_for_download(app_id):
    """
    Get APK ready for download.
    Returns: {
        'status': 'ready' | 'downloading' | 'error',
        'telegram_link': str or None,
        'size_mb': float,
        'error': str or None
    }
    
    If APK is already in Telegram, returns link immediately.
    If not, downloads from source, uploads to Telegram, then returns link.
    """
    apps = get_apps_data()
    app = apps.get(app_id)
    
    if not app:
        return {
            'status': 'error',
            'error': f'App not found: {app_id}',
            'telegram_link': None,
            'size_mb': 0,
        }
    
    # Check if already have Telegram link
    tg_link = app.get('telegram_link') or app.get('local_apk_url')
    if tg_link and 't.me' in tg_link:
        print(f'✅ Using cached Telegram link for {app_id}')
        return {
            'status': 'ready',
            'telegram_link': tg_link,
            'size_mb': app.get('apk_size_mb', 0),
            'error': None,
        }
    
    # Need to download and upload
    print(f'🔄 On-demand download for {app_id}...')
    
    # Get source URL
    uptodown_url = app.get('uptodown_url') or app.get('uptodown_download')
    if not uptodown_url:
        return {
            'status': 'error',
            'error': 'No source URL available',
            'telegram_link': None,
            'size_mb': 0,
        }
    
    # Step 1: Resolve actual download URL
    apk_url, session = resolve_uptodown_download_url(uptodown_url)
    if not apk_url:
        return {
            'status': 'error',
            'error': 'Cannot resolve download URL',
            'telegram_link': None,
            'size_mb': 0,
        }
    
    # Step 2: Download APK
    filepath = download_apk_file(apk_url, app_id, session)
    if not filepath:
        return {
            'status': 'error',
            'error': 'Download failed',
            'telegram_link': None,
            'size_mb': 0,
        }
    
    try:
        # Step 3: Upload to Telegram
        tg_link, size_mb = upload_to_telegram(
            filepath,
            app_title=app.get('title', app_id),
            app_id=app_id
        )
        
        if tg_link:
            # Step 4: Update apps.json with new Telegram link
            update_app_data(app_id, {
                'telegram_link': tg_link,
                'local_apk_url': tg_link,
                'apk_size_mb': size_mb,
            })
            
            return {
                'status': 'ready',
                'telegram_link': tg_link,
                'size_mb': size_mb,
                'error': None,
            }
        else:
            return {
                'status': 'error',
                'error': 'Upload to Telegram failed',
                'telegram_link': None,
                'size_mb': size_mb,
            }
    finally:
        # Cleanup temp file
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass


def check_telegram_config():
    """Check if Telegram config is valid."""
    issues = []
    if not TG_BOT_TOKEN:
        issues.append('TELEGRAM_BOT_TOKEN not set')
    if not TG_CHANNEL_ID:
        issues.append('TELEGRAM_CHANNEL_ID not set')
    if not TG_API_BASE:
        issues.append('TG_API_BASE not set')
    return issues


if __name__ == '__main__':
    # Test
    issues = check_telegram_config()
    if issues:
        print('⚠️ Config issues:')
        for issue in issues:
            print(f'  - {issue}')
    else:
        print('✅ Telegram config OK')
    
    # Test with an app_id
    import sys
    if len(sys.argv) > 1:
        app_id = sys.argv[1]
        result = get_apk_for_download(app_id)
        print(json.dumps(result, indent=2))
