import os
import sys
import json
import time
import traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- Default config (set env vars to override) ----
_DEFAULTS = {
    'TELEGRAM_BOT_TOKEN': '8560694013:AAG9ajjYkvZnc6FaJMPqaEB6ZcOBTHeq0tA',
    'TELEGRAM_CHANNEL_ID': '-1003806183533',
    'TELEGRAM_INFO_CHANNEL_ID': '-1003811018285',
}
for k, v in _DEFAULTS.items():
    if not os.environ.get(k):
        os.environ[k] = v

from bot_crawler import fetch_trending, get_apps, resolve_apk_url
from telegram_storage import download_and_upload, send_text, send_app_info_to_channel2, check_secrets
from json_store import save_items, check_connection, get_all_apps
try:
    from google_play_scraper import app as gp_app, search as gp_search
except Exception:
    gp_app = None
    gp_search = None

# Track apps that failed to download APK - persist to file
BLACKLIST_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'apk_blacklist.json')
MAX_FAIL_COUNT = 3  # Skip app after 3 failed attempts

def load_blacklist():
    """Load blacklist from file"""
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'rb') as f:
                raw = f.read()
            text = raw.decode('utf-8', errors='replace').replace('\ufffd', '')
            return json.loads(text)
    except Exception:
        pass
    return {}

def save_blacklist(blacklist):
    """Save blacklist to file"""
    try:
        os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(blacklist, f, indent=2)
    except Exception as e:
        print(f"  ⚠️ Không thể lưu blacklist: {e}")

def add_to_blacklist(app_id):
    """Add app to blacklist with timestamp"""
    blacklist = load_blacklist()
    blacklist[app_id] = {
        'count': blacklist.get(app_id, {}).get('count', 0) + 1,
        'last_fail': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    save_blacklist(blacklist)
    return blacklist[app_id]['count']

def is_blacklisted(app_id):
    """Check if app is blacklisted"""
    blacklist = load_blacklist()
    return blacklist.get(app_id, {}).get('count', 0) >= MAX_FAIL_COUNT

def reset_blacklist_for(app_id):
    """Remove app from blacklist (when APK found)"""
    blacklist = load_blacklist()
    if app_id in blacklist:
        del blacklist[app_id]
        save_blacklist(blacklist)

# Search queries để rotate - mỗi cycle dùng 1 nhóm query khác nhau
SEARCH_QUERY_GROUPS = [
    # Group 0: Social & Communication
    ['social media app', 'messaging app', 'video call app', 'dating app', 'chat app'],
    # Group 1: Entertainment & Media  
    ['video streaming', 'music player', 'podcast app', 'movie app', 'anime app'],
    # Group 2: Productivity & Tools
    ['productivity app', 'office app', 'file manager', 'calculator', 'calendar app'],
    # Group 3: Photo & Video
    ['photo editor', 'video editor', 'camera app', 'filter app', 'collage maker'],
    # Group 4: Shopping & Finance
    ['shopping app vietnam', 'online shopping', 'banking app', 'payment app', 'food delivery'],
    # Group 5: Games - Action & Adventure
    ['action game android', 'adventure game', 'battle royale', 'fps game mobile', 'rpg game'],
    # Group 6: Games - Casual & Puzzle
    ['puzzle game', 'casual game', 'racing game', 'simulation game', 'strategy game'],
    # Group 7: Travel & Transport
    ['travel app', 'map navigation', 'taxi app', 'hotel booking', 'flight booking'],
    # Group 8: Health & Fitness
    ['fitness app', 'health tracker', 'meditation app', 'workout app', 'running app'],
    # Group 9: Education & Learning
    ['learning app', 'language learning', 'education app', 'dictionary app', 'reading app'],
    # Group 10: News & Weather
    ['news app', 'weather app', 'newspaper', 'rss reader', 'magazine app'],
    # Group 11: Vietnam popular
    ['Zalo', 'Shopee', 'Lazada', 'VietComBank', 'Grab Vietnam'],
    # Group 12: Utilities
    ['vpn app', 'browser app', 'keyboard app', 'launcher android', 'wallpaper app'],
    # Group 13: Music & Audio
    ['spotify music', 'nhạc Việt', 'karaoke app', 'radio app', 'ringtone app'],
    # Group 14: Business
    ['business app', 'crm app', 'project management', 'document scanner', 'email app'],
]

# Tăng tốc: 15s between cycles, 1s delay between apps
CYCLE_INTERVAL = int(os.environ.get('CYCLE_INTERVAL', '15'))  # 15s between cycles
APP_DELAY = int(os.environ.get('APP_DELAY', '1'))  # 1 sec between apps
# Với streaming server, có thể upload file lớn mà không lo OOM
MAX_APK_SIZE_MB = int(os.environ.get('MAX_APK_SIZE_MB', '2000'))  # 2GB max (telegram limit)

# Track cycle number để rotate qua các nguồn khác nhau
_cycle_count = 0


def fetch_from_gplay_search(queries, limit=30):
    """Fetch apps from Google Play using search queries."""
    if not gp_search:
        return []
    items = []
    seen_ids = set()
    for q in queries:
        if len(items) >= limit:
            break
        try:
            results = gp_search(q, lang='vi', country='vn')
            for r in results:
                app_id = r.get('appId', '')
                if not app_id or app_id in seen_ids:
                    continue
                seen_ids.add(app_id)
                icon = (r.get('icon') or '').strip()
                items.append({
                    'app_id': app_id,
                    'title': r.get('title', app_id),
                    'icon': icon,
                    'description': r.get('description', ''),
                })
                if len(items) >= limit:
                    break
        except Exception as e:
            print(f'  GPlay search error for "{q}": {e}')
    return items


def run_once():
    """Run one crawl cycle. Returns number of apps processed."""
    global _cycle_count
    _cycle_count += 1
    existing = get_all_apps()
    existing_ids = {a['app_id'] for a in existing}
    existing_data = {a['app_id']: a for a in existing}  # Full data lookup
    existing_ch2 = {a['app_id']: a.get('channel2_link', '') for a in existing}
    print(f'\n{"="*60}')
    posted_count = sum(1 for v in existing_ch2.values() if v)
    print(f'[Cycle #{_cycle_count}] DB: {len(existing_ids)} apps ({posted_count} với icon)')
    print(f'{"="*60}')

    # Rotate qua các nhóm search query mỗi chu kỳ để tìm app MỚI
    items = []
    source_name = 'trending'
    
    if _cycle_count > 1 and gp_search:
        # Sau cycle đầu tiên, rotate qua các nhóm search query
        group_idx = (_cycle_count - 2) % len(SEARCH_QUERY_GROUPS)
        queries = SEARCH_QUERY_GROUPS[group_idx]
        source_name = f'search/{queries[0]}'
        
        print(f'  📂 Nguồn: {source_name} (group {group_idx+1}/{len(SEARCH_QUERY_GROUPS)})')
        items = fetch_from_gplay_search(queries, limit=50)
    
    # Fallback hoặc cycle đầu: dùng trending
    if not items:
        items = fetch_trending(limit=30, source='gplay')
        source_name = 'trending'
        print(f'  📂 Nguồn: {source_name}')
    
    # Lọc bỏ apps đã có đủ dữ liệu hoặc đã fail quá nhiều lần
    skip_count = 0
    skip_fail_count = 0
    new_items = []
    for i in items:
        app_id = i.get('app_id', '')
        existing_app = existing_data.get(app_id, {})
        has_icon = (existing_app.get('icon') or '').startswith('http')
        has_channel2 = bool(existing_app.get('channel2_link'))
        has_local_apk = bool(existing_app.get('local_apk_url'))
        
        # Skip apps that already have icon + local APK (channel2 is optional)
        if has_icon and has_local_apk:
            skip_count += 1
            continue
        
        # Skip apps that have failed too many times (can't find APK) - persisted blacklist
        if is_blacklisted(app_id) and not has_local_apk:
            skip_fail_count += 1
            continue
            
        new_items.append(i)
    
    if skip_fail_count > 0:
        print(f'  ⚠️ Bỏ qua {skip_fail_count} apps trong blacklist (không tìm được APK)')
    
    print(f'  📊 Tìm thấy: {len(items)} | Đã cache: {skip_count} | Cần xử lý: {len(new_items)}')
    
    if not new_items:
        print('  ✅ Không có app mới cần xử lý')
        return 0

    # Chỉ xử lý items chưa cached
    items = new_items

    mapping = {}
    raw = os.environ.get('APK_URLS_JSON')
    if raw:
        try:
            mapping = json.loads(raw)
        except Exception:
            mapping = {}

    # Filter: bỏ app không có icon (sẽ thử fetch từ gp_app bên dưới)
    # Chỉ bỏ app đã thử fetch icon mà vẫn không có
    no_icon_items = [i for i in items if not (i.get('icon') or '').strip().startswith('http')]
    has_icon_items = [i for i in items if (i.get('icon') or '').strip().startswith('http')]
    # Thử fetch icon cho app thiếu icon
    if gp_app and no_icon_items:
        for i in no_icon_items:
            try:
                info = gp_app(i.get('app_id', ''), lang='vi', country='vn')
                icon = (info.get('icon') or '').strip()
                if icon and icon.startswith('http'):
                    i['icon'] = icon
                    i['title'] = info.get('title') or i.get('title')
                    i['description'] = info.get('description') or i.get('description', '')
                    has_icon_items.append(i)
                    print(f'  🔍 Fetched icon: {i.get("title")}')
            except Exception:
                pass  # Skip apps that can't get icon
    items = has_icon_items

    new_count = 0
    for idx, i in enumerate(items):
        app_id = i.get('app_id', '')
        existing_app = existing_data.get(app_id, {})
        has_icon = (existing_app.get('icon') or '').startswith('http')
        has_local_apk = bool(existing_app.get('local_apk_url'))
        has_channel2 = bool(existing_app.get('channel2_link'))
        
        # Use existing data if available
        if has_icon:
            i['icon'] = existing_app['icon']
            i['title'] = existing_app.get('title') or i.get('title')
            i['description'] = existing_app.get('description') or i.get('description')
        elif gp_app:
            # Only fetch from Google Play if we don't have icon
            try:
                info = gp_app(app_id, lang='vi', country='vn')
                i['title'] = info.get('title') or i.get('title') or app_id
                icon = (info.get('icon') or '').strip()
                if icon and icon.startswith('http'):
                    i['icon'] = icon
                i['description'] = info.get('description') or i.get('description') or ''
                print(f'  🔍 [{idx+1}/{len(items)}] {i.get("title", app_id)}')
            except Exception as e:
                print(f"  ❌ GPlay error {app_id}: {e}")

        # Find APK URL - skip if already have local APK
        if has_local_apk:
            # Use existing APK data
            i['local_apk_url'] = existing_app.get('local_apk_url')
            i['apk_size_mb'] = existing_app.get('apk_size_mb', 0)
            i['telegram_link'] = existing_app.get('telegram_link', '')
            i['apk_public_url'] = existing_app.get('apk_public_url', '')
            print(f'  ✅ Using cached APK: {i.get("local_apk_url")}')
            # Remove from blacklist since we have APK
            reset_blacklist_for(app_id)
        else:
            apk_url = i.get('apk_url')
            uptodown_detail = i.get('uptodown_detail')  # from fetch_trending

            # If no apk_url yet, resolve from Uptodown/Aptoide
            if not apk_url:
                apk_url = mapping.get(app_id)
            if not apk_url:
                print(f'  🔎 Resolving APK URL for {app_id}...')
                try:
                    resolved = resolve_apk_url(app_id, title=i.get('title'), icon=i.get('icon'))
                    if resolved:
                        apk_url = resolved.get('apk_url')
                        uptodown_detail = resolved.get('uptodown_detail') or uptodown_detail
                        if apk_url:
                            print(f'  ✅ Found APK URL: {apk_url[:80]}...')
                        else:
                            print(f'  ⚠️ No APK URL found for {app_id}')
                except Exception as e:
                    print(f'  ❌ Resolve APK error {app_id}: {e}')

            # Download & upload to Telegram
            upload_success = False
            url_resolved = apk_url is not None  # Track if we even found a URL
            if apk_url:
                try:
                    pub_url, size_mb, local_path = download_and_upload(
                        apk_url, app_id=app_id,
                        title=i.get('title', ''), version='latest',
                        max_size_mb=MAX_APK_SIZE_MB,
                        uptodown_detail=uptodown_detail
                    )
                    if pub_url:
                        i['apk_public_url'] = pub_url
                        i['apk_size_mb'] = size_mb
                        upload_success = True
                    if local_path:
                        i['local_apk_url'] = local_path  # Direct download URL
                        upload_success = True
                except Exception as e:
                    print(f"  Upload error {app_id}: {e}")
            
            # Track failures - only blacklist if we actually tried to resolve URL
            if upload_success:
                reset_blacklist_for(app_id)
            elif url_resolved or apk_url:
                # Only blacklist if we tried and failed (not if we just couldn't find URL)
                fail_count = add_to_blacklist(app_id)
                if fail_count >= MAX_FAIL_COUNT:
                    print(f'  ⛔ {app_id}: thêm vào blacklist ({fail_count} lần thất bại)')
            else:
                # No URL found at all - still count as failure but with lower weight
                fail_count = add_to_blacklist(app_id)
                if fail_count >= MAX_FAIL_COUNT:
                    print(f'  ⏭️ {app_id}: tạm bỏ qua (không tìm được APK URL)')

            i['telegram_link'] = i.get('apk_public_url') or i.get('local_apk_url') or ''

        # Save immediately after each app (incremental)
        save_items([i])

        # Post to info channel (for new apps OR apps never posted to channel 2)
        if has_channel2:
            # Already posted, just copy the link
            i['channel2_link'] = existing_app.get('channel2_link')
        else:
            if app_id not in existing_ids:
                new_count += 1
            try:
                link, _ = send_app_info_to_channel2(i)
                if link:
                    i['channel2_link'] = link
                    save_items([i])  # persist channel2 link
                    print(f'  📢 Posted to Channel 2: {i.get("title", app_id)}')
                else:
                    print(f'  ⚠️ Channel 2 post failed for {app_id} (no link returned)')
            except Exception as e:
                print(f"  Channel 2 error {app_id}: {e}")

        # Delay between apps
        if idx < len(items) - 1:
            time.sleep(APP_DELAY)

    found = len(items)
    success = len([x for x in items if x.get('telegram_link') or x.get('local_apk_url')])
    print(f'\n📊 Chu kỳ xong: {found} app, {success} upload OK, {new_count} app mới')
    send_text(f'🤖 Bot 1 done: {found} app, {success} uploaded, {new_count} new')
    return found


def main():
    print('='*60)
    print('  VesTool Bot 1 — Continuous App Crawler')
    print('='*60)
    print(f'  TELEGRAM_BOT_TOKEN: {"✅" if os.environ.get("TELEGRAM_BOT_TOKEN") else "❌"}')
    print(f'  TELEGRAM_CHANNEL_ID: {"✅" if os.environ.get("TELEGRAM_CHANNEL_ID") else "❌"}')
    print(f'  TELEGRAM_INFO_CHANNEL_ID: {"✅" if os.environ.get("TELEGRAM_INFO_CHANNEL_ID") else "❌"}')
    print(f'  Cycle interval: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60} min)')
    print(f'  App delay: {APP_DELAY}s')
    check_secrets()
    check_connection()

    cycle = 0
    while True:
        cycle += 1
        print(f'\n🔄 === CYCLE {cycle} === {time.strftime("%Y-%m-%d %H:%M:%S")}')
        try:
            run_once()
        except Exception as e:
            print(f'❌ Cycle {cycle} error: {e}')
            traceback.print_exc()

        print(f'\n💤 Chờ {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60} phút) trước chu kỳ tiếp...')
        time.sleep(CYCLE_INTERVAL)


if __name__ == '__main__':
    main()
