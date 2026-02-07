import os
from datetime import datetime
from supabase import create_client

def get_client():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        print(f'Supabase client init error: {e}')
        return None

def save_items(items):
    if not items:
        print("Không có dữ liệu để lưu")
        return
    client = get_client()
    if not client:
        return
    data = []
    for it in items:
        app_id = (it.get('app_id') or '').strip()
        title = (it.get('title') or '').strip()
        if app_id and title:
            data.append({
                'app_id': app_id,
                'title': title,
                'icon': it.get('icon') or '',
                'description': it.get('description') or '',
                'apk_url': it.get('apk_url') or '',
                'telegram_link': it.get('telegram_link') or '',
                'date': datetime.utcnow().isoformat()
            })
    if data:
        try:
            # Nếu trùng app_id, thực hiện UPDATE thay vì báo lỗi duplicate
            return client.table('apps').upsert(data, on_conflict='app_id').execute()
        except Exception as e:
            print(f'Supabase upsert error: {e}')
            msg = str(e)
            if ('duplicate key' in msg.lower()) or ('23505' in msg) or ('apps_app_id_key' in msg):
                try:
                    for row in data:
                        client.table('apps').update({
                            'title': row['title'],
                            'icon': row['icon'],
                            'description': row['description'],
                            'apk_url': row['apk_url'],
                            'telegram_link': row['telegram_link'],
                            'date': row['date'],
                        }).eq('app_id', row['app_id']).execute()
                    print('Supabase: duplicate handled by UPDATE')
                except Exception as e2:
                    print(f'Supabase manual update error: {e2}')
            if 'PGRST205' in msg or 'Could not find the table' in msg:
                print('Gợi ý: Tạo bảng apps trong Supabase theo schema bots/schema.sql')
            return None

def check_connection():
    client = get_client()
    if not client:
        print('Supabase: missing URL or KEY')
        return False
    try:
        client.table('apps').select('*').limit(1).execute()
        print('Supabase: connection OK')
        return True
    except Exception as e:
        print(f'Supabase: connection error {e}')
        return False
