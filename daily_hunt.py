import os
import json
from bot_crawler import fetch_trending
from telegram_storage import download_and_upload, send_text, check_secrets
from supabase_store import save_items, check_connection
import traceback
try:
    from google_play_scraper import app as gp_app
except Exception:
    gp_app = None

def main():
    print('=== BẮT ĐẦU DAILY HUNT ===')
    print(f' TELEGRAM_BOT_TOKEN present: {bool(os.environ.get("TELEGRAM_BOT_TOKEN"))}')
    print(f' TELEGRAM_CHANNEL_ID present: {bool(os.environ.get("TELEGRAM_CHANNEL_ID"))}')
    print(f' SUPABASE_URL present: {bool(os.environ.get("SUPABASE_URL"))}')
    print(f' SUPABASE_KEY present: {bool(os.environ.get("SUPABASE_KEY"))}')
    check_secrets()
    check_connection()
    ids_raw = os.environ.get('APP_IDS', '')
    ids = [x.strip() for x in ids_raw.split(',') if x.strip()]
    print(f'App IDs trước khi cào: {ids}')
    print('>>> Cào từ Google Play (nguồn chính)...')
    items = fetch_trending(limit=10, source='gplay')
    print(f'Nhận từ GPlay: {len(items)} item')
    print(json.dumps(items[:3], ensure_ascii=False, indent=2))
    print('>>> Cào từ APKPure (fallback)...')
    alt = fetch_trending(limit=10, source='apkpure')
    print(f'Nhận từ APKPure: {len(alt)} item')
    by_title = {}
    for x in alt:
        key = (x.get('title') or '').strip().lower()
        by_title[key] = x
    mapping = {}
    raw = os.environ.get('APK_URLS_JSON')
    if raw:
        try:
            mapping = json.loads(raw)
        except Exception as e:
            print(f'APK_URLS_JSON parse error: {e}')
            print(traceback.format_exc())
            mapping = {}
    for i in items:
        print(f'Xử lý app: {i.get("title")}')
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
            except Exception as e:
                print(f'Upload error: {e}')
                print(traceback.format_exc())
                link = None
        i['telegram_link'] = link
    print(f'>>> Chuẩn bị lưu {len(items)} item lên Supabase')
    if items:
        print(json.dumps(items[:2], ensure_ascii=False, indent=2))
    else:
        print('Danh sách items đang rỗng, thử cào cứng com.facebook.katana bằng Google Play Scraper')
        if gp_app:
            try:
                gp = gp_app('com.facebook.katana', lang='vi', country='vn')
                fb_item = {
                    'app_id': 'com.facebook.katana',
                    'title': gp.get('title') or 'Facebook',
                    'icon': gp.get('icon') or '',
                    'description': gp.get('description') or '',
                    'apk_url': ''
                }
                print('FB item:', json.dumps(fb_item, ensure_ascii=False, indent=2))
                save_items([fb_item])
                print('>>> Đã thử lưu com.facebook.katana lên Supabase (test kết nối)')
            except Exception as e:
                print(f'Google Play Scraper lỗi: {e}')
        else:
            print('Google Play Scraper chưa sẵn sàng để import')
    save_items(items)
    success = len([x for x in items if x.get('telegram_link')])
    fail = len(items) - success
    msg = f'Đại ca ơi! Đã quét xong {len(items)} app. Thành công: {success} app, Thất bại: {fail} app. Link web: localhost:3000'
    send_text(msg)

if __name__ == '__main__':
    main()
