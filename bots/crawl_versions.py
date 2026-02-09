#!/usr/bin/env python3
"""
Bot 2: Crawl old versions continuously.
Re-reads apps.json each cycle so new apps from Bot 1 are picked up automatically.
Just run: python3 bots/crawl_versions.py
"""
import os, sys, time, hashlib, logging, requests, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- Default config (set env vars to override) ----
_DEFAULTS = {
    'TELEGRAM_BOT_TOKEN': '8560694013:AAG9ajjYkvZnc6FaJMPqaEB6ZcOBTHeq0tA',
    'TELEGRAM_VER_CHANNEL_ID': '-1003864259175',
}
for k, v in _DEFAULTS.items():
    if not os.environ.get(k):
        os.environ[k] = v

from version_crawler import crawl_old_versions, parse_size_mb, resolve_version_download
from json_store import get_all_apps, save_versions, load_versions
from telegram_storage import download_file, upload_apk_to_telegram, HEADERS

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

CYCLE_INTERVAL = int(os.environ.get('CYCLE_INTERVAL', '30'))  # 30s between cycles
APP_DELAY = int(os.environ.get('APP_DELAY', '1'))  # 1 sec between apps


def dl_and_upload(vdict, app_id, app_title='', tmp_dir='tmp', icon_url=''):
    """Download APK for a version, upload to Telegram version channel, return (link, size_mb).
    If icon_url provided, sends icon first then replies with APK (lấy từ apps.json của Bot 1).
    """
    vn = vdict.get('version_name', '')
    if not vdict.get('apk_url') or not vn:
        return None, 0
    direct_url, sess = resolve_version_download(vdict)
    if not direct_url:
        print(f'    Cannot resolve download for v{vn} ({vdict.get("source")})')
        return None, 0
    os.makedirs(tmp_dir, exist_ok=True)
    sid = app_id.replace('.', '_')
    h = hashlib.md5(direct_url.encode()).hexdigest()[:6]
    fname = f'{sid}_v{vn}_{h}.apk'
    lp = os.path.join(tmp_dir, fname)
    ds = sess or requests.Session()
    ds.headers.update(HEADERS)
    got = download_file(direct_url, lp, session=ds)
    if not got:
        print(f'    Download failed v{vn}')
        return None, 0
    fs = os.path.getsize(lp)
    mb = fs / 1024 / 1024

    # Skip upload if file too large (với streaming server có thể tăng limit)
    max_mb = int(os.environ.get('MAX_APK_SIZE_MB', '2000'))  # 2GB max
    if max_mb > 0 and mb > max_mb:
        print(f'    ⚠️ APK too large ({mb:.1f} MB > {max_mb} MB limit), skipping')
        try:
            os.remove(lp)
        except Exception:
            pass
        return None, mb

    # Upload to version channel (TELEGRAM_VER_CHANNEL_ID)
    ver_channel = os.environ.get('TELEGRAM_VER_CHANNEL_ID')
    tg_link, _ = upload_apk_to_telegram(
        lp, app_title=app_title or app_id,
        app_id=app_id, version=vn,
        channel_id=ver_channel,
        icon_url=icon_url  # Lấy icon từ apps.json của Bot 1
    )
    try:
        os.remove(lp)
    except Exception:
        pass
    if tg_link:
        return tg_link, mb
    return None, 0


def process_one_app(aid, title, limit, dl_limit, skip_dl, icon_url=''):
    """Process a single app: crawl versions, download APKs, save.
    icon_url: lấy từ apps.json để gửi kèm icon khi upload APK.
    """
    print(f'\n  📱 {title} ({aid})')
    try:
        # Check existing versions to skip already-downloaded ones
        existing = load_versions(aid)
        existing_with_tg = {v['version_name'] for v in existing if v.get('telegram_link', '').startswith('https://t.me/') or v.get('apk_url', '').startswith('https://t.me/')}

        versions = crawl_old_versions(aid, title=title, limit=limit)
        if not versions:
            print('    No versions found')
            return 0, 0

        print(f'    Found {len(versions)} versions ({len(existing_with_tg)} already on Telegram)')

        uploaded = 0
        if not skip_dl:
            for vi, v in enumerate(versions):
                if uploaded >= dl_limit:
                    break
                vn = v.get('version_name', '')
                # Skip if already uploaded to Telegram
                if vn in existing_with_tg:
                    continue
                print(f'    [{vi+1}] Resolving v{vn} ({v.get("source")})...')
                pub, mb = dl_and_upload(v, aid, app_title=title, icon_url=icon_url)
                if pub:
                    v['telegram_link'] = pub
                    if mb > 0:
                        v['apk_size_mb'] = round(mb, 1)
                    uploaded += 1
                time.sleep(2)
            if uploaded > 0:
                print(f'    ✅ Uploaded {uploaded} APKs to Telegram')

        for v in versions:
            if v.get('size_str') and not v.get('apk_size_mb'):
                v['apk_size_mb'] = parse_size_mb(v['size_str'])
        save_versions(aid, versions)
        return len(versions), uploaded
    except Exception as e:
        print(f'    ❌ Error: {e}')
        traceback.print_exc()
        return 0, 0


def run_once(limit, dl_limit, app_filter, skip_dl):
    """Run one cycle. Re-reads apps.json to pick up new apps from Bot 1."""
    all_apps = get_all_apps()  # Always fresh read
    if app_filter:
        all_apps = [a for a in all_apps if a.get('app_id') == app_filter]
    apps = [a for a in all_apps if a.get('app_id')]

    if not apps:
        print('  No apps in database yet. Waiting for Bot 1...')
        return 0, 0

    print(f'\n{"="*60}')
    print(f'  Bot 2 cycle: {len(apps)} apps, ver_limit={limit}, dl_limit={dl_limit}')
    print(f'  Upload: {"SKIP" if skip_dl else "Telegram channel"}')
    print(f'{"="*60}')

    total_ver, total_dl = 0, 0
    for i, app in enumerate(apps):
        aid = app.get('app_id', '')
        title = app.get('title', aid)
        icon_url = app.get('icon', '')  # Lấy icon từ apps.json (Bot 1 đã crawl)
        print(f'\n[{i+1}/{len(apps)}]', end='')
        ver, dl = process_one_app(aid, title, limit, dl_limit, skip_dl, icon_url=icon_url)
        total_ver += ver
        total_dl += dl

        if i < len(apps) - 1:
            time.sleep(APP_DELAY)

    print(f'\n📊 Cycle done: {total_ver} versions, {total_dl} APKs uploaded')
    return total_ver, total_dl


def main():
    if not os.environ.get('TELEGRAM_BOT_TOKEN') or not os.environ.get('TELEGRAM_VER_CHANNEL_ID'):
        print("Error: Set TELEGRAM_BOT_TOKEN and TELEGRAM_VER_CHANNEL_ID")
        sys.exit(1)

    limit = int(os.environ.get('VERSION_LIMIT', '20'))
    dl_limit = int(os.environ.get('DOWNLOAD_LIMIT', '5'))
    app_filter = os.environ.get('APP_FILTER', '').strip()
    skip_dl = os.environ.get('SKIP_DOWNLOAD', '').strip() == '1'

    print('='*60)
    print('  VesTool Bot 2 — Continuous Version Crawler')
    print('='*60)
    print(f'  TELEGRAM_BOT_TOKEN: ✅')
    print(f'  TELEGRAM_VER_CHANNEL_ID: {os.environ.get("TELEGRAM_VER_CHANNEL_ID")}')
    print(f'  Cycle interval: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60} min)')
    print(f'  App delay: {APP_DELAY}s')
    print(f'  Version limit: {limit} | Download limit: {dl_limit}')
    if app_filter:
        print(f'  Filter: {app_filter}')

    cycle = 0
    while True:
        cycle += 1
        print(f'\n🔄 === CYCLE {cycle} === {time.strftime("%Y-%m-%d %H:%M:%S")}')
        try:
            run_once(limit, dl_limit, app_filter, skip_dl)
        except Exception as e:
            print(f'❌ Cycle {cycle} error: {e}')
            traceback.print_exc()

        print(f'\n💤 Chờ {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60} phút) trước chu kỳ tiếp...')
        time.sleep(CYCLE_INTERVAL)


if __name__ == '__main__':
    main()
