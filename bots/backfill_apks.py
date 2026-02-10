#!/usr/bin/env python3
"""Backfill missing APK uploads for apps stored in the JSON data store.

Usage examples:
    python3 bots/backfill_apks.py                # process all missing apps
    python3 bots/backfill_apks.py --limit 25     # only process 25 apps
    python3 bots/backfill_apks.py --sleep 2.0    # wait 2 seconds between apps
"""
import argparse
import os
import sys
import time
import traceback
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_crawler import resolve_apk_url  # type: ignore
from json_store import load_apps, save_items  # type: ignore
from telegram_storage import download_and_upload  # type: ignore

_DEFAULTS = {
    'TELEGRAM_BOT_TOKEN': '8560694013:AAG9ajjYkvZnc6FaJMPqaEB6ZcOBTHeq0tA',
    'TELEGRAM_CHANNEL_ID': '-1003806183533',
    'TELEGRAM_INFO_CHANNEL_ID': '-1003811018285',
}
for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)

MAX_APK_SIZE_MB = int(os.environ.get('MAX_APK_SIZE_MB', '2000'))


def _backfill_single(app: dict) -> Tuple[bool, str]:
    app_id = app.get('app_id')
    if not app_id:
        return False, 'missing app_id'

    icon = (app.get('icon') or '').strip()
    if not icon:
        return False, 'missing icon'
    title = (app.get('title') or app_id).strip()
    description = app.get('description', '')

    try:
        resolved = resolve_apk_url(app_id, title=title, icon=icon)
    except Exception as exc:  # pragma: no cover - network heavy
        return False, f'resolve error: {exc}'

    apk_url = (resolved or {}).get('apk_url') if resolved else None
    uptodown_detail = (resolved or {}).get('uptodown_detail') if resolved else None
    if not apk_url:
        return False, 'no apk url found'

    try:
        tg_link, size_mb, local_link = download_and_upload(
            apk_url,
            app_id=app_id,
            title=title,
            version='latest',
            max_size_mb=MAX_APK_SIZE_MB,
            uptodown_detail=uptodown_detail,
        )
    except Exception as exc:  # pragma: no cover - network heavy
        traceback.print_exc()
        return False, f'upload failed: {exc}'

    public_link = tg_link or local_link
    if not public_link:
        return False, 'upload returned no link'

    updated = {
        'app_id': app_id,
        'title': title,
        'icon': icon,
        'description': description,
        'apk_public_url': tg_link or app.get('apk_public_url', ''),
        'local_apk_url': local_link or app.get('local_apk_url', ''),
        'apk_size_mb': size_mb or app.get('apk_size_mb', 0),
        'telegram_link': public_link,
    }
    save_items([updated])
    return True, ''


def main():
    parser = argparse.ArgumentParser(description='Backfill APK uploads for apps missing Telegram links.')
    parser.add_argument('--limit', type=int, default=0, help='Maximum number of apps to process (0 = all).')
    parser.add_argument('--sleep', type=float, default=float(os.environ.get('BACKFILL_SLEEP', '1.0')),
                        help='Seconds to sleep between apps to avoid rate limits.')
    args = parser.parse_args()

    apps = load_apps()
    missing = [a for a in apps if not (a.get('telegram_link') or a.get('local_apk_url'))]
    missing.sort(key=lambda x: x.get('date', ''), reverse=True)

    total = len(missing)
    limit = args.limit if args.limit and args.limit > 0 else total
    print(f'🔎 Found {total} apps without APK uploads. Processing up to {limit}.')

    processed = 0
    success = 0
    failures = []

    for app in missing:
        if processed >= limit:
            break
        processed += 1
        app_id = app.get('app_id')
        title = app.get('title') or app_id
        print(f'[{processed}/{limit}] Processing {title} ({app_id})...')
        ok, reason = _backfill_single(app)
        if ok:
            success += 1
            print('   ✅ Done')
        else:
            failures.append((app_id, reason))
            print(f'   ❌ {reason}')
        if processed < limit and args.sleep > 0:
            time.sleep(args.sleep)

    print('\n📊 Backfill summary:')
    print(f'  Processed: {processed}')
    print(f'  Success:   {success}')
    print(f'  Failed:    {len(failures)}')
    if failures:
        for app_id, reason in failures[:10]:
            print(f'    - {app_id}: {reason}')
        if len(failures) > 10:
            print('    ... (more failures not shown)')


if __name__ == '__main__':
    main()
