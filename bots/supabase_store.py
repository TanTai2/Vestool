import os
from datetime import datetime
from supabase import create_client

def get_client():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        return None
    return create_client(url, key)

def save_items(items):
    if not items:
        print("Không có dữ liệu để lưu")
        return
    client = get_client()
    if not client:
        return
    data = []
    for it in items:
        if it.get('app_id') and it.get('title'):
            data.append({
                'app_id': it['app_id'],
                'title': it['title'],
                'icon': it.get('icon', ''),
                'description': it.get('description', ''),
                'apk_url': it.get('apk_url', ''),
                'telegram_link': it.get('telegram_link', ''),
                'date': datetime.utcnow().isoformat()
            })
    if data:
        return client.table('apps').upsert(data).select('*').execute()
