import os
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.85 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Referer': 'https://www.google.com/'
}

def _abs(base, href):
    return urllib.parse.urljoin(base, href)

def _get_soup(url):
    session = requests.Session()
    try:
        session.headers.update(HEADERS)
    except Exception:
        pass
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def _apkcombo_search_get_detail(query):
    base = 'https://apkcombo.com'
    q = urllib.parse.quote((query or '').strip())
    if not q:
        return None
    url = f'{base}/vi/search/?q={q}'
    soup = _get_soup(url)
    if not soup:
        return None
    a = soup.select_one('a[href^="/vi/"]')
    return _abs(base, a.get('href')) if a and a.get('href') else None

def _apkcombo_direct(detail_url):
    soup = _get_soup(detail_url)
    a = soup.select_one('a[href*="/download/apk"]')
    if not a:
        return None
    dl_page = _abs(detail_url, a.get('href'))
    r = requests.get(dl_page, headers=HEADERS, timeout=30)
    s2 = BeautifulSoup(r.text, 'html.parser')
    cand = s2.select_one('a[href$=".apk"]')
    return _abs(dl_page, cand.get('href')) if cand else None

def _supabase_client():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

def save_items(items):
    if not items:
        return False
    client = _supabase_client()
    if not client:
        return False
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
    if not data:
        return False
    try:
        client.table('apps').upsert(data, on_conflict='app_id').execute()
        return True
    except Exception:
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
            return True
        except Exception:
            return False

def build_items_from_ids(limit=10):
    ids_raw = os.environ.get('APP_IDS', '')
    ids = [x.strip() for x in ids_raw.split(',') if x.strip()]
    if not ids:
        ids = ['com.facebook.katana','com.instagram.android','com.ss.android.ugc.trill','com.whatsapp','org.telegram.messenger']
    items = []
    for app_id in ids[:limit]:
        title = app_id
        detail = _apkcombo_search_get_detail(app_id)
        apk_url = _apkcombo_direct(detail) if detail else None
        items.append({
            'app_id': app_id,
            'title': title,
            'icon': '',
            'description': '',
            'apk_url': apk_url,
            'telegram_link': ''
        })
    return items

def main():
    items = build_items_from_ids(limit=int(os.environ.get('LIMIT', '10')))
    saved = save_items(items)
    found = len(items)
    with_apk = len([x for x in items if x.get('apk_url')])
    print(f'Tong: {found}, co APK: {with_apk}, luu Supabase: {saved}')

if __name__ == '__main__':
    main()
