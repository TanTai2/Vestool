import os
import json
from bot_crawler import fetch_trending
from telegram_storage import download_and_upload, send_text
from supabase_store import save_items

def main():
    items = fetch_trending(limit=10, source='apkpure')
    alt = fetch_trending(limit=10, source='apkcombo')
    print(f'APKPure lấy được: {len(items)} app')
    print(f'APKCombo lấy được: {len(alt)} app')
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
