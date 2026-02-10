#!/usr/bin/env python3
"""
Telegram Metadata Storage
Upload app metadata (icon, info, versions) to Telegram for memory optimization
"""

import os
import json
import time
import hashlib
import requests
import tempfile
from datetime import datetime
from dotenv import load_dotenv

# Load .env
load_dotenv('/root/VesTool/.env')

TG_API_BASE = os.environ.get('TG_API_BASE', 'http://localhost:8081').rstrip('/')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_METADATA_CHANNEL = '-1003811018285'  # Channel để lưu metadata

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36'
}

def tg_api_call(method, params):
    """Call Telegram Bot API."""
    if not TG_BOT_TOKEN:
        return None
    
    url = f'{TG_API_BASE}/bot{TG_BOT_TOKEN}/{method}'
    try:
        resp = requests.post(url, json=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('ok'):
                return data.get('result')
        print(f'❌ TG API error {method}: {resp.text[:200]}')
    except Exception as e:
        print(f'❌ TG API exception {method}: {e}')
    return None

def upload_app_icon(app_id, icon_url):
    """Download and upload app icon to Telegram."""
    if not icon_url or not icon_url.startswith(('http://', 'https://')):
        return None
    
    try:
        # Download icon
        resp = requests.get(icon_url, headers=HEADERS, timeout=30, stream=True)
        if resp.status_code != 200:
            return None
        
        # Save to temp file
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg')
        
        try:
            # Write data to temp file using file descriptor
            with os.fdopen(temp_fd, 'wb') as temp_file:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
            
            # Upload to Telegram using requests directly (not tg_api_call)
            with open(temp_path, 'rb') as f:
                files = {'photo': (f'icon_{app_id}.jpg', f, 'image/jpeg')}
                data = {
                    'chat_id': TG_METADATA_CHANNEL,
                    'caption': f'📱 Icon: {app_id}'
                }
                
                upload_resp = requests.post(
                    f'{TG_API_BASE}/bot{TG_BOT_TOKEN}/sendPhoto',
                    files=files,
                    data=data,
                    timeout=30
                )
                
                if upload_resp.status_code == 200:
                    result = upload_resp.json()
                    if result.get('ok'):
                        # Get file_id for later reference
                        photo = result.get('result', {}).get('photo', [])
                        if photo:
                            largest = max(photo, key=lambda x: x.get('file_size', 0))
                            return largest.get('file_id')
        
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
    except Exception as e:
        print(f'❌ Upload icon error {app_id}: {e}')
    
    return None

def upload_app_metadata(app):
    """Upload complete app metadata to Telegram."""
    app_id = app.get('app_id', 'unknown')
    
    try:
        # Create metadata message
        metadata = {
            'app_id': app_id,
            'title': app.get('title', ''),
            'description': app.get('description', ''),
            'version': app.get('version', ''),
            'size_mb': app.get('apk_size_mb', 0),
            'date': app.get('date', ''),
            'icon_url': app.get('icon', ''),
            'uptodown_url': app.get('uptodown_url', ''),
            'package_name': app.get('package_name', ''),
            'telegram_link': app.get('telegram_link', '')  # Keep existing if any
        }
        
        # Upload icon first
        icon_file_id = None
        if metadata['icon_url']:
            icon_file_id = upload_app_icon(app_id, metadata['icon_url'])
            if icon_file_id:
                metadata['telegram_icon_id'] = icon_file_id
        
        # Create text message with metadata
        text_lines = [
            f"📱 **{metadata['title']}**",
            f"🆔 `{app_id}`",
            f"📦 Version: {metadata['version']}",
            f"📏 Size: {metadata['size_mb']:.1f} MB" if metadata['size_mb'] > 0 else "",
            f"📅 {metadata['date']}",
            "",
            f"📝 {metadata['description'][:500]}..." if len(metadata.get('description', '')) > 500 else metadata.get('description', ''),
            "",
            f"🌐 Uptodown: {metadata['uptodown_url']}",
            "",
            f"💾 JSON: ```json\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n```"
        ]
        
        text = '\n'.join([line for line in text_lines if line])
        
        # Send message
        result = tg_api_call('sendMessage', {
            'chat_id': TG_METADATA_CHANNEL,
            'text': text,
            'parse_mode': 'Markdown'
        })
        
        if result:
            message_id = result.get('message_id')
            metadata_link = f"https://t.me/c/{TG_METADATA_CHANNEL[4:]}/{message_id}"
            print(f"✅ Uploaded {app_id} metadata: {metadata_link}")
            return {
                'message_id': message_id,
                'metadata_link': metadata_link,
                'icon_file_id': icon_file_id
            }
    
    except Exception as e:
        print(f"❌ Upload metadata error {app_id}: {e}")
    
    return None

def batch_upload_apps(apps, start_index=0):
    """Upload multiple apps with progress tracking."""
    print(f'🚀 Uploading {len(apps)} apps to Telegram metadata channel...')
    
    uploaded = 0
    failed = 0
    
    for i, app in enumerate(apps[start_index:], start_index):
        app_id = app.get('app_id', f'app_{i}')
        
        print(f'📤 [{i+1}/{len(apps)}] Uploading {app_id}...')
        
        result = upload_app_metadata(app)
        if result:
            uploaded += 1
            # Update app with telegram metadata links
            app['telegram_metadata_id'] = result['message_id']
            app['telegram_metadata_link'] = result['metadata_link']
            if result['icon_file_id']:
                app['telegram_icon_id'] = result['icon_file_id']
        else:
            failed += 1
            print(f'❌ Failed to upload {app_id}')
        
        # Rate limiting
        time.sleep(1.5)  # 1.5s between uploads
        
        # Progress every 10 apps
        if (i + 1) % 10 == 0:
            elapsed = (i + 1 - start_index) * 1.5
            remaining = (len(apps) - i - 1) * 1.5
            print(f'📊 Progress: {i+1}/{len(apps)} | ✅ {uploaded} | ❌ {failed} | ⏱️ ETA: {remaining/60:.1f}m')
    
    print(f'🏁 Upload completed: ✅ {uploaded} | ❌ {failed}')
    return uploaded, failed

def fetch_apps_from_telegram():
    """Fetch app metadata from Telegram channel (for web API)."""
    try:
        print('📥 Fetching apps from Telegram metadata channel...')
        
        # Get recent messages from the metadata channel
        updates = tg_api_call('getUpdates', {
            'chat_id': TG_METADATA_CHANNEL,
            'limit': 100
        })
        
        if not updates:
            return []
        
        apps = []
        for update in updates.get('result', []):
            message = update.get('message', {})
            text = message.get('text', '')
            
            # Look for JSON metadata in message
            if '```json' in text:
                try:
                    json_start = text.find('```json') + 7
                    json_end = text.find('```', json_start)
                    if json_end > json_start:
                        json_text = text[json_start:json_end].strip()
                        app_data = json.loads(json_text)
                        if app_data.get('app_id'):
                            apps.append(app_data)
                except Exception:
                    continue
        
        print(f'📱 Found {len(apps)} apps from Telegram')
        return apps
        
    except Exception as e:
        print(f'❌ Error fetching from Telegram: {e}')
        return []

def sync_telegram_to_local():
    """Sync Telegram metadata back to local apps.json."""
    try:
        print('🔄 Syncing Telegram metadata to local file...')
        
        # Get apps from Telegram
        telegram_apps = fetch_apps_from_telegram()
        if not telegram_apps:
            print('📭 No apps found in Telegram')
            return
        
        # Load existing local apps
        local_apps = {}
        if os.path.exists(APPS_FILE):
            try:
                with open(APPS_FILE, 'r', encoding='utf-8') as f:
                    local_list = json.load(f)
                    for app in local_list:
                        if app.get('app_id'):
                            local_apps[app['app_id']] = app
            except Exception as e:
                print(f'⚠️ Error reading local apps: {e}')
        
        # Merge Telegram apps with local (Telegram has priority for metadata)
        for tg_app in telegram_apps:
            app_id = tg_app.get('app_id')
            if app_id:
                # Keep local telegram_link, local_apk_url if they exist
                existing = local_apps.get(app_id, {})
                if existing.get('telegram_link'):
                    tg_app['telegram_link'] = existing['telegram_link']
                if existing.get('local_apk_url'):
                    tg_app['local_apk_url'] = existing['local_apk_url']
                
                local_apps[app_id] = tg_app
        
        # Save merged data
        apps_list = sorted(
            local_apps.values(),
            key=lambda x: x.get('date', ''),
            reverse=True
        )
        
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(APPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(apps_list, f, ensure_ascii=False, indent=2)
        
        print(f'✅ Synced {len(apps_list)} apps to {APPS_FILE}')
        return len(apps_list)
        
    except Exception as e:
        print(f'❌ Sync error: {e}')
        return 0

if __name__ == '__main__':
    # Test upload single app
    test_app = {
        'app_id': 'com.test.app',
        'title': 'Test App',
        'description': 'This is a test app for metadata upload',
        'version': '1.0.0',
        'apk_size_mb': 15.5,
        'date': '2026-02-09',
        'icon': 'https://example.com/icon.png',
        'uptodown_url': 'https://test.en.uptodown.com/android'
    }
    
    print('🧪 Testing metadata upload...')
    result = upload_app_metadata(test_app)
    if result:
        print(f'✅ Test successful: {result}')
    else:
        print('❌ Test failed')