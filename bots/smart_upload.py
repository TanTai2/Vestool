#!/usr/bin/env python3
"""
Smart Metadata Upload - Upload all apps metadata + icons to Telegram
Without errors and with progress tracking
"""

import os
import json
import time
import sys
from datetime import datetime

# Load module
sys.path.insert(0, '/root/VesTool/bots')
from telegram_metadata import upload_app_metadata, tg_api_call

DATA_DIR = '/root/VesTool/data'
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')

# Upload settings
BATCH_SIZE = 10  # Process 10 apps at a time
DELAY_BETWEEN_APPS = 2  # 2 seconds between uploads
DELAY_BETWEEN_BATCHES = 10  # 10 seconds between batches

def load_apps():
    """Load apps from JSON file."""
    with open(APPS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_apps(apps):
    """Save apps back to JSON file."""
    with open(APPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)

def get_apps_to_upload(apps):
    """Find apps that haven't been uploaded to Telegram metadata."""
    to_upload = []
    for app in apps:
        # Skip if already has telegram metadata link
        if app.get('telegram_metadata_link'):
            continue
        # Skip if missing essential data
        if not app.get('app_id') or not app.get('title'):
            continue
        to_upload.append(app)
    return to_upload

def upload_batch(batch_apps, batch_num, total_batches):
    """Upload a batch of apps with progress tracking."""
    print(f'📦 Batch {batch_num}/{total_batches} - {len(batch_apps)} apps')
    
    batch_success = 0
    batch_failed = 0
    
    for i, app in enumerate(batch_apps, 1):
        app_id = app.get('app_id')
        title = app.get('title', 'Unknown')
        
        print(f'  📱 [{i}/{len(batch_apps)}] {title[:40]}...')
        
        try:
            # Upload metadata
            result = upload_app_metadata(app)
            
            if result:
                # Update app with telegram links
                app['telegram_metadata_id'] = result['message_id']
                app['telegram_metadata_link'] = result['metadata_link']
                if result.get('icon_file_id'):
                    app['telegram_icon_id'] = result['icon_file_id']
                
                batch_success += 1
                print(f'    ✅ Uploaded: {result["metadata_link"]}')
            else:
                batch_failed += 1
                print(f'    ❌ Failed: {app_id}')
        
        except Exception as e:
            batch_failed += 1
            print(f'    ❌ Exception: {e}')
        
        # Rate limiting between apps
        if i < len(batch_apps):  # Don't sleep after last app in batch
            time.sleep(DELAY_BETWEEN_APPS)
    
    return batch_success, batch_failed

def main():
    """Main upload process."""
    print('🚀 SMART METADATA UPLOAD TO TELEGRAM')
    print('=' * 50)
    
    # Load apps
    print('📋 Loading apps...')
    apps = load_apps()
    print(f'📊 Total apps: {len(apps)}')
    
    # Find apps to upload
    to_upload = get_apps_to_upload(apps)
    print(f'🎯 Apps to upload: {len(to_upload)}')
    
    if not to_upload:
        print('✅ All apps already uploaded!')
        return
    
    # Calculate batches
    total_batches = (len(to_upload) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f'📦 Batches: {total_batches} (size: {BATCH_SIZE})')
    
    # Confirm before starting
    response = input(f'\\n🤔 Upload {len(to_upload)} apps to Telegram? (y/N): ')
    if not response.lower().startswith('y'):
        print('❌ Cancelled')
        return
    
    # Start upload
    print('\\n🎬 Starting upload...')
    start_time = time.time()
    
    total_success = 0
    total_failed = 0
    
    for batch_num in range(1, total_batches + 1):
        start_idx = (batch_num - 1) * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(to_upload))
        batch_apps = to_upload[start_idx:end_idx]
        
        # Upload batch
        batch_success, batch_failed = upload_batch(batch_apps, batch_num, total_batches)
        
        total_success += batch_success
        total_failed += batch_failed
        
        # Progress report
        elapsed = time.time() - start_time
        progress = batch_num / total_batches * 100
        remaining_batches = total_batches - batch_num
        eta = elapsed / batch_num * remaining_batches if batch_num > 0 else 0
        
        print(f'\\n📊 Progress: {progress:.1f}% | ✅ {total_success} | ❌ {total_failed} | ⏱️ ETA: {eta/60:.1f}m\\n')
        
        # Save progress (in case of interruption)
        if batch_success > 0:
            print('💾 Saving progress...')
            save_apps(apps)
        
        # Rest between batches (except last)
        if batch_num < total_batches:
            print(f'⏸️ Resting {DELAY_BETWEEN_BATCHES}s between batches...')
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    # Final save
    save_apps(apps)
    
    # Final report
    elapsed = time.time() - start_time
    print('\\n' + '=' * 50)
    print('🎉 UPLOAD COMPLETED!')
    print(f'✅ Success: {total_success}')
    print(f'❌ Failed: {total_failed}')
    print(f'⏱️ Time: {elapsed/60:.1f} minutes')
    print(f'⚡ Speed: {total_success/(elapsed/60):.1f} apps/min')
    print('=' * 50)

if __name__ == '__main__':
    main()