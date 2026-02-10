#!/usr/bin/env python3
"""
Update icons for existing apps - Fix invalid icon URLs
"""

import asyncio
import json
import os
import sys
import re
import time

sys.path.insert(0, '/root/VesTool/bots')
from uptodown_crawler import UptodownCrawler, normalize_icon_url

DATA_DIR = '/root/VesTool/data'
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')
BATCH_SIZE = 100

def is_valid_icon(icon_url):
    """Check if icon URL is valid (not SVG sprite placeholder)."""
    if not icon_url:
        return False
    if 'img.utdstc.com/icon' in icon_url:
        return True
    if icon_url.endswith('.svg') or '#icon' in icon_url:
        return False
    return False

async def update_icons():
    """Update icons for apps with invalid icon URLs."""
    
    # Load existing apps
    with open(APPS_FILE, 'r', encoding='utf-8') as f:
        apps = json.load(f)
    
    print(f'📋 Total apps: {len(apps)}')
    
    # Find apps with invalid icons
    invalid_apps = []
    for app in apps:
        icon = app.get('icon', '')
        if not is_valid_icon(icon):
            if app.get('uptodown_url'):  # Only if we can re-scrape
                invalid_apps.append(app)
    
    print(f'🔍 Apps with invalid icons: {len(invalid_apps)}')
    
    if not invalid_apps:
        print('✅ All icons are valid!')
        return
    
    # Ask how many to update
    limit = input(f'\\n🤔 How many apps to update? (default: 100, max: {len(invalid_apps)}): ').strip()
    try:
        limit = int(limit) if limit else 100
        limit = min(limit, len(invalid_apps))
    except:
        limit = 100
    
    print(f'\\n🎯 Will update icons for {limit} apps')
    
    # Initialize crawler
    crawler = UptodownCrawler()
    await crawler.init_session()
    
    updated_count = 0
    failed_count = 0
    start_time = time.time()
    
    try:
        for i, app in enumerate(invalid_apps[:limit], 1):
            uptodown_url = app.get('uptodown_url', '')
            title = app.get('title', 'Unknown')[:30]
            
            print(f'📱 [{i}/{limit}] {title}...')
            
            try:
                # Re-scrape just for icon
                updated_app = await crawler.scrape_app_detail(uptodown_url)
                
                if updated_app and is_valid_icon(updated_app.get('icon', '')):
                    app['icon'] = updated_app['icon']
                    updated_count += 1
                    print(f'  ✅ Updated icon')
                else:
                    failed_count += 1
                    print(f'  ⏭️ No valid icon found')
                    
            except Exception as e:
                failed_count += 1
                print(f'  ❌ Error: {e}')
            
            # Rate limiting
            await asyncio.sleep(0.3)
            
            # Progress every 20 apps
            if i % 20 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed
                eta = (limit - i) / rate if rate > 0 else 0
                print(f'\\n📊 Progress: {i}/{limit} | ✅ {updated_count} | ❌ {failed_count} | ⏱️ ETA: {eta:.0f}s\\n')
                
                # Save progress
                with open(APPS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(apps, f, ensure_ascii=False, indent=2)
                print('💾 Saved progress')
    
    finally:
        await crawler.close_session()
    
    # Final save
    with open(APPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)
    
    # Report
    elapsed = time.time() - start_time
    print('\\n' + '=' * 50)
    print('🎉 ICON UPDATE COMPLETED!')
    print(f'✅ Updated: {updated_count}')
    print(f'❌ Failed: {failed_count}')
    print(f'⏱️ Time: {elapsed:.1f}s')
    print(f'⚡ Speed: {updated_count/(elapsed/60):.1f} icons/min')
    print('=' * 50)

if __name__ == '__main__':
    asyncio.run(update_icons())