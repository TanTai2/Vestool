#!/usr/bin/env python3
"""
Update descriptions for existing apps without re-crawling everything
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Import crawler
sys.path.insert(0, '/root/VesTool/bots')
from uptodown_crawler import UptodownCrawler

DATA_DIR = '/root/VesTool/data'
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')
BATCH_SIZE = 50

async def update_descriptions():
    """Update descriptions for apps with short/generic descriptions."""
    
    # Load existing apps
    with open(APPS_FILE, 'r', encoding='utf-8') as f:
        apps = json.load(f)
    
    print(f'📋 Loaded {len(apps)} apps')
    
    # Find apps with poor descriptions
    poor_desc_apps = []
    for app in apps[:200]:  # Only check first 200 to be conservative
        desc = app.get('description', '')
        if (len(desc) < 50 or 
            'Manage your account anytime, anywhere' in desc or
            desc.count(' ') < 5):  # Too short or generic
            poor_desc_apps.append(app)
    
    print(f'🔍 Found {len(poor_desc_apps)} apps with poor descriptions')
    
    if not poor_desc_apps:
        print('✅ All descriptions look good!')
        return
    
    # Initialize crawler
    crawler = UptodownCrawler()
    await crawler.init_session()
    
    updated_count = 0
    
    try:
        for i, app in enumerate(poor_desc_apps[:BATCH_SIZE]):  # Limit to 50 apps
            uptodown_url = app.get('uptodown_url', '')
            if not uptodown_url:
                continue
                
            print(f'📱 [{i+1}/{min(len(poor_desc_apps), BATCH_SIZE)}] Updating: {app.get("title", "Unknown")}')
            
            # Re-scrape just this app
            updated_app = await crawler.scrape_app_detail(uptodown_url)
            if updated_app and updated_app.get('description'):
                new_desc = updated_app['description']
                old_desc = app.get('description', '')
                
                # Only update if significantly better
                if len(new_desc) > len(old_desc) + 10:
                    app['description'] = new_desc
                    updated_count += 1
                    print(f'  ✅ Updated ({len(old_desc)} → {len(new_desc)} chars)')
                else:
                    print(f'  ⏭️  No improvement')
            else:
                print(f'  ❌ Failed to fetch')
            
            # Rate limiting
            await asyncio.sleep(0.5)
            
    finally:
        await crawler.close_session()
    
    # Save updated apps
    if updated_count > 0:
        with open(APPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(apps, f, ensure_ascii=False, indent=2)
        print(f'💾 Updated {updated_count} descriptions in {APPS_FILE}')
    else:
        print('📝 No descriptions were updated')

if __name__ == '__main__':
    asyncio.run(update_descriptions())