"""
JSON-based data store — replaces Supabase.
Data lives in /root/VesTool/data/:
  apps.json                          ← all apps
  versions/{app_id}.json             ← versions per app
"""
import os
import json
import threading
from datetime import datetime

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'))
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')
VERSIONS_DIR = os.path.join(DATA_DIR, 'versions')

_lock = threading.Lock()


def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(VERSIONS_DIR, exist_ok=True)


def _read_json(path):
    if not os.path.exists(path):
        return []
    try:
        # Read as bytes first to handle encoding issues
        with open(path, 'rb') as f:
            raw = f.read()
        # Try strict UTF-8 first
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            # Fallback: replace bad bytes and re-write clean file
            print(f'⚠️ Fixing encoding in {path}')
            text = raw.decode('utf-8', errors='replace')
            text = text.replace('\ufffd', '')
        data = json.loads(text)
        return data
    except json.JSONDecodeError as e:
        print(f'⚠️ _read_json JSON error {path}: {e}')
        # Try to recover by reading as bytes with lenient encoding
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            text = raw.decode('utf-8', errors='ignore')
            data = json.loads(text)
            # Re-write clean version
            _write_json(path, data)
            print(f'✅ Recovered {len(data)} records from {path}')
            return data
        except Exception:
            pass
        return []
    except (IOError, ValueError, OSError) as e:
        print(f'⚠️ _read_json error {path}: {e}')
        return []


def _write_json(path, data):
    _ensure_dirs()
    # Clean all string values before writing
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    if isinstance(v, str):
                        # Remove any non-UTF8 replacement chars
                        item[k] = v.replace('\ufffd', '')
    tmp = path + '.tmp'
    # ensure_ascii=True prevents any encoding issues
    json_str = json.dumps(data, ensure_ascii=True, indent=2)
    # Verify roundtrip
    json.loads(json_str)
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(json_str)
    os.replace(tmp, path)


# ==================== APPS ====================

def load_apps():
    """Load all apps from apps.json."""
    return _read_json(APPS_FILE)


def save_items(items):
    """Save/upsert app items to apps.json. Skips apps without icons."""
    if not items:
        print("Không có dữ liệu để lưu")
        return

    skipped = 0
    valid = []
    for it in items:
        app_id = (it.get('app_id') or '').strip()
        title = (it.get('title') or '').strip()
        icon = (it.get('icon') or '').strip()
        if not icon or not icon.startswith('http'):
            skipped += 1
            print(f'⏭️ Skip (no icon): {title or app_id}')
            continue
        if app_id and title:
            valid.append({
                'app_id': app_id,
                'title': title,
                'icon': icon,
                'description': it.get('description') or '',
                'apk_url': it.get('apk_public_url') or it.get('apk_url') or '',
                'apk_size_mb': it.get('apk_size_mb') or 0,
                'telegram_link': it.get('telegram_link') or '',
                'local_apk_url': it.get('local_apk_url') or '',  # Direct download URL
                'channel2_link': it.get('channel2_link') or '',  # Info channel post link
                'date': it.get('date') or datetime.utcnow().isoformat(),
            })

    if skipped > 0:
        print(f'⚠️ Bỏ qua {skipped} app không có icon')

    if not valid:
        return

    with _lock:
        existing = load_apps()
        by_id = {a['app_id']: a for a in existing}
        for item in valid:
            app_id = item['app_id']
            if app_id in by_id:
                # Merge: preserve existing non-empty values for key fields
                old = by_id[app_id]
                # Keep existing values if new value is empty
                for key in ['local_apk_url', 'channel2_link', 'telegram_link', 'apk_url']:
                    if not item.get(key) and old.get(key):
                        item[key] = old[key]
                # Keep existing apk_size_mb if new is 0
                if not item.get('apk_size_mb') and old.get('apk_size_mb'):
                    item['apk_size_mb'] = old['apk_size_mb']
            by_id[app_id] = item
        all_apps = sorted(by_id.values(), key=lambda x: x.get('date', ''), reverse=True)
        _write_json(APPS_FILE, all_apps)

    print(f'✅ Lưu {len(valid)} app ({len(all_apps)} tổng)')


def get_all_apps():
    """Get all apps as list of dicts (for crawlers)."""
    return load_apps()


def get_app(app_id):
    """Get a single app by app_id."""
    for a in load_apps():
        if a.get('app_id') == app_id:
            return a
    return None


# ==================== VERSIONS ====================

def _versions_path(app_id):
    safe = app_id.replace('.', '_').replace('/', '_')
    return os.path.join(VERSIONS_DIR, f'{safe}.json')


def load_versions(app_id):
    """Load versions for an app."""
    return _read_json(_versions_path(app_id))


def save_versions(app_id, versions):
    """Save/upsert versions for an app."""
    if not versions or not app_id:
        return

    data = []
    for v in versions:
        ver_name = (v.get('version_name') or '').strip()
        if not ver_name:
            continue
        size_mb = v.get('apk_size_mb') or 0
        if not size_mb and v.get('size_str'):
            import re
            m = re.search(r'([\d.]+)\s*(mb|m|gb|g|kb|k)', (v.get('size_str') or '').lower())
            if m:
                val = float(m.group(1))
                unit = m.group(2)
                if unit in ('gb', 'g'):
                    size_mb = val * 1024
                elif unit in ('kb', 'k'):
                    size_mb = val / 1024
                else:
                    size_mb = val
        data.append({
            'version_name': ver_name,
            'apk_url': v.get('apk_url', ''),
            'telegram_link': v.get('telegram_link', ''),
            'apk_size_mb': round(size_mb, 1) if size_mb else 0,
            'release_date': v.get('release_date', ''),
            'source': v.get('source', ''),
        })

    with _lock:
        existing = load_versions(app_id)
        by_ver = {v['version_name']: v for v in existing}
        for d in data:
            vn = d['version_name']
            # Merge: preserve existing telegram_link if new data lacks it
            if vn in by_ver:
                old = by_ver[vn]
                if not d.get('telegram_link') and old.get('telegram_link'):
                    d['telegram_link'] = old['telegram_link']
                if not d.get('apk_size_mb') and old.get('apk_size_mb'):
                    d['apk_size_mb'] = old['apk_size_mb']
            by_ver[vn] = d
        all_ver = sorted(by_ver.values(),
                         key=lambda x: [int(p) for p in x['version_name'].split('.') if p.isdigit()],
                         reverse=True)
        _write_json(_versions_path(app_id), all_ver)

    print(f'💾 Lưu {len(data)} versions cho {app_id} ({len(all_ver)} tổng)')


# ==================== CONNECTION CHECK ====================

def check_connection():
    """Check JSON store is accessible."""
    _ensure_dirs()
    print(f'JSON Store: {DATA_DIR} ✅')
    apps = load_apps()
    print(f'  Apps: {len(apps)}')
    return True
