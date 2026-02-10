#!/usr/bin/env python3
"""Quick test upload 100 apps"""

import os
import json
import time
import sys

sys.path.insert(0, '/root/VesTool/bots')
from telegram_metadata import upload_app_metadata

APPS_FILE = '/root/VesTool/data/apps.json'
UPLOAD_LIMIT = 100  # Chỉ upload 100 apps đầu

def main():
    print('🎯 UPLOAD 100 APPS ĐẦU TIÊN')
    print('=' * 40)
    
    # Load apps
    with open(APPS_FILE, 'r', encoding='utf-8') as f:
        apps = json.load(f)
    
    print(f'📊 Total apps: {len(apps)}')
    print(f'🎯 Will upload: {UPLOAD_LIMIT} apps')
    
    response = input(f'\\n🤔 Upload {UPLOAD_LIMIT} apps? (y/N): ')
    if not response.lower().startswith('y'):
        print('❌ Cancelled')
        return
    
    # Upload first 100 apps
    success = 0
    failed = 0
    start_time = time.time()
    
    for i, app in enumerate(apps[:UPLOAD_LIMIT], 1):
        title = app.get('title', 'Unknown')[:30]
        print(f'📱 [{i}/{UPLOAD_LIMIT}] {title}...')
        
        try:
            result = upload_app_metadata(app)
            if result:
                # Update app with metadata link
                app['telegram_metadata_link'] = result['metadata_link']
                success += 1
                print(f'  ✅ OK')
            else:
                failed += 1
                print(f'  ❌ Failed')
        except Exception as e:
            failed += 1
            print(f'  ❌ Error: {e}')
        
        # Rate limiting
        time.sleep(1.5)
        
        # Progress every 10 apps
        if i % 10 == 0:
            elapsed = time.time() - start_time
            eta = (UPLOAD_LIMIT - i) * 1.5
            print(f'\\n📊 Progress: {i}/{UPLOAD_LIMIT} | ✅ {success} | ❌ {failed} | ⏱️ ETA: {eta/60:.1f}m\\n')
    
    # Save updated apps
    with open(APPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)
    
    # Final report
    elapsed = time.time() - start_time
    print('\\n' + '=' * 40)
    print('🎉 COMPLETED!')
    print(f'✅ Success: {success}')
    print(f'❌ Failed: {failed}')
    print(f'⏱️ Time: {elapsed/60:.1f} minutes')
    print(f'⚡ Speed: {success/(elapsed/60):.1f} apps/min')

if __name__ == '__main__':
    main()