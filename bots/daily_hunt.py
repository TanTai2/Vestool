import os
import json
from bot_crawler import fetch_trending, get_apps
from telegram_storage import download_and_upload, send_text, check_secrets
from supabase_store import save_items, check_connection
try:
    from google_play_scraper import app as gp_app
except Exception:
    gp_app = None

def main():
    print('Env check:')
    print(f' TELEGRAM_BOT_TOKEN present: {bool(os.environ.get("TELEGRAM_BOT_TOKEN"))}')
    print(f' TELEGRAM_CHANNEL_ID present: {bool(os.environ.get("TELEGRAM_CHANNEL_ID"))}')
    print(f' SUPABASE_URL present: {bool(os.environ.get("SUPABASE_URL"))}')
    print(f' SUPABASE_KEY present: {bool(os.environ.get("SUPABASE_KEY"))}')
    check_secrets()
    check_connection()
    ids_raw = os.environ.get('APP_IDS', '')
    ids = [x.strip() for x in ids_raw.split(',') if x.strip()]
    print(f'App IDs trước khi cào: {ids}')
    if not ids:
        default_ids = ['com.facebook.katana','com.instagram.android','com.ss.android.ugc.trill','com.whatsapp','org.telegram.messenger']
        os.environ['APP_IDS'] = ','.join(default_ids)
        print(f'APP_IDS rỗng, dùng mặc định: {default_ids}')
    items = fetch_trending(limit=20, source='gplay')
    alt = fetch_trending(limit=20, source='apkpure')
    print(f'GPlay lấy được: {len(items)} app')
    print(f'APKPure lấy được: {len(alt)} app')
    by_title = {}
    for x in alt:
        key = (x.get('title') or '').strip().lower()
        by_title[key] = x
    mapping = {}
    raw = os.environ.get('APK_URLS_JSON')
    if raw:
        try:
            mapping = json.loads(raw)
        except Exception:
            mapping = {}
    for i in items:
        # Bổ sung mô tả/icon từ Google Play cho chắc chắn
        if gp_app:
            try:
                info = gp_app(i['app_id'], lang='vi', country='vn')
                i['title'] = info.get('title') or i.get('title') or i['app_id']
                i['icon'] = info.get('icon') or i.get('icon') or ''
                i['description'] = info.get('description') or i.get('description') or ''
            except Exception as e:
                print(f'GPlay enrich error {i.get(\"app_id\")}: {e}')
        link = None
        apk_url = i.get('apk_url')
        if not apk_url:
            k = (i.get('title') or '').strip().lower()
            alt_item = by_title.get(k)
            if alt_item:
                apk_url = alt_item.get('apk_url')
        if not apk_url:
            apk_url = mapping.get(i['app_id'])
        if apk_url:
            try:
                link = download_and_upload(apk_url)
            except Exception:
                link = None
        i['telegram_link'] = link
    if not items and gp_app:
        try:
            gp = gp_app('com.facebook.katana', lang='vi', country='vn')
            fb_item = {
                'app_id': 'com.facebook.katana',
                'title': gp.get('title') or 'Facebook',
                'icon': gp.get('icon') or '',
                'description': gp.get('description') or '',
                'apk_url': ''
            }
            save_items([fb_item])
            print('>>> Đã thử lưu com.facebook.katana lên Supabase (test kết nối)')
        except Exception as e:
            print(f'Google Play Scraper lỗi: {e}')
    save_items(items)
    found = len(items)
    with_apk = len([x for x in items if x.get('apk_url')])
    success = len([x for x in items if x.get('telegram_link')])
    fail_upload = len([x for x in items if x.get('apk_url') and not x.get('telegram_link')])
    missing_apk = len([x for x in items if not x.get('apk_url')])
    print(f'Tổng: {found}, có APK: {with_apk}, upload thành công: {success}, thiếu APK: {missing_apk}, lỗi upload: {fail_upload}')
    msg = f'Đại ca ơi! Đã quét xong {found} app. Thành công: {success} app, Thất bại: {fail_upload} app, Thiếu APK: {missing_apk}. Link web: localhost:3000'
    send_text(msg)

if __name__ == '__main__':
    main()
