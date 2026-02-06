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
    client = get_client()
    if not client:
        return
    data = []
    for i in items:
        data.append({
            'app_id': i.get('app_id'),
            'title': i.get('title'),
            'icon': i.get('icon'),
            'description': i.get('description'),
            'telegram_link': i.get('telegram_link'),
            'date': datetime.utcnow().isoformat()
        })
    client.table('apps').upsert(data).execute()
