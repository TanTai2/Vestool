import os
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
import traceback
try:
    from google_play_scraper import app as gp_app, search as gp_search, list as gp_list, collections, categories
except Exception:
    gp_app = None
    gp_search = None
    gp_list = None
    collections = None
    categories = None

# Bộ mặt nạ đầy đủ để APKPure tin đây là người dùng thật
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}

def _abs(base, href):
    return urllib.parse.urljoin(base, href)

def _get_soup(url):
    # Tạo một phiên làm việc để giữ cookie, giúp vượt qua 403
    session = requests.Session()
    try:
        session.headers.update(HEADERS)
    except Exception:
        pass
    tries = int(os.environ.get('VESTOOL_TRIES', '3'))
    backoff = float(os.environ.get('VESTOOL_BACKOFF', '1.5'))
    err = None
    for i in range(tries):
        try:
            r = session.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 403 and 'apkpure.com' in url:
                alt_url = url.replace('apkpure.com/', 'apkpure.com/vn/')
                r = session.get(alt_url, headers=HEADERS, timeout=20)
            if os.environ.get('VESTOOL_DEBUG') == '1':
                print(f'[DEBUG] Fetched URL={url} status={r.status_code} length={len(r.text)}')
                print(r.text[:2000])
            r.raise_for_status()
            return BeautifulSoup(r.text, 'html.parser')
        except requests.RequestException as e:
            err = e
            time.sleep(backoff * (i + 1))
    print(f'[ERROR] _get_soup failed url={url} err={err}')
    return None

def _apkpure_list(limit=10):
    base = 'https://apkpure.com'
    paths = ['/latest-updates', '/vn/latest-updates']
    for path in paths:
        soup = _get_soup(f'{base}{path}')
        apps = []
        if not soup:
            continue
        cards = soup.select('ul.pdt-list-ul li, div.app-list li')
        if not cards:
            cards = soup.select('a.da[href*="/"]')
        for c in cards:
            a = c if getattr(c, 'name', None) == 'a' else c.find('a')
            if not a:
                continue
            href = a.get('href') or ''
            if not href or '/download' in href or href == '/':
                continue
            title_tag = c.find('dt') or c.find('p') or a
            title = (title_tag.text or '').strip() if title_tag else 'Unknown App'
            img_tag = c.find('img')
            img = (img_tag.get('data-src') or img_tag.get('src')) if img_tag else None
            detail = _abs(base, href)
            print(f'app_detail: {detail}')
            apps.append({'title': title, 'icon': img, 'detail': detail})
            if len(apps) >= limit:
                break
        if apps:
            return apps
    return []

def _apkpure_direct(detail_url):
    try:
        soup = _get_soup(detail_url)
        a = soup.select_one('a.da[href*="/download"]') or soup.select_one('a[href*="/download"]')
        if not a: 
            return None
        dl_url = _abs(detail_url, a.get('href'))
        r = requests.get(dl_url, headers=HEADERS, timeout=30)
        s2 = BeautifulSoup(r.text, 'html.parser')
        cand = s2.select_one('a#download_link') or s2.select_one('a[href$=".apk"]')
        return _abs(dl_url, cand.get('href')) if cand else None
    except Exception as e:
        print(f'Crawler _apkpure_direct error: {e}')
        print(traceback.format_exc())
        return None

def _apkcombo_list(limit=10):
    base = 'https://apkcombo.com'
    url = f'{base}/vi/latest/'
    soup = _get_soup(url)
    apps = []
    if not soup:
        return apps
    cards = soup.select('div.list-state li a')
    if not cards:
        cards = soup.select('a[href^="/vi/"]')
    for a in cards:
        href = a.get('href') or ''
        if not href or '/download/' in href: 
            continue
        tnode = a.select_one('div.name')
        title = tnode.text.strip() if tnode else (a.text or '').strip()
        img_tag = a.find('img')
        img = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
        detail = _abs(base, href)
        print(f'app_detail: {detail}')
        apps.append({'title': title, 'icon': img, 'detail': detail})
        if len(apps) >= limit: 
            break
    return apps

def _apkcombo_direct(detail_url):
    try:
        soup = _get_soup(detail_url)
        a = soup.select_one('a[href*="/download/apk"]')
        if not a: 
            return None
        dl_page = _abs(detail_url, a.get('href'))
        r = requests.get(dl_page, headers=HEADERS, timeout=30)
        s2 = BeautifulSoup(r.text, 'html.parser')
        cand = s2.select_one('a[href$=".apk"]')
        return _abs(dl_page, cand.get('href')) if cand else None
    except Exception as e:
        print(f'Crawler _apkcombo_direct error: {e}')
        print(traceback.format_exc())
        return None

def _apkcombo_search_get_detail(title):
    base = 'https://apkcombo.com'
    q = urllib.parse.quote(title)
    url = f'{base}/vi/search/?q={q}'
    soup = _get_soup(url)
    if not soup:
        return None
    a = soup.select_one('a[href^="/vi/"]')
    return _abs(base, a.get('href')) if a and a.get('href') else None

def _uptodown_search_get_detail(app_id=None, title=None):
    base = 'https://en.uptodown.com'
    q = urllib.parse.quote((app_id or title or '').strip())
    if not q:
        return None
    url = f'{base}/android/search?q={q}'
    print(f'Uptodown search URL: {url}')
    soup = _get_soup(url)
    if not soup:
        print('Uptodown search: soup is None')
        return None
    candidates = soup.select('a[href*="/android"]')
    print(f'Uptodown search: candidates={len(candidates)}')
    target = None
    tnorm = (title or '').lower().strip()
    for a in candidates:
        href = a.get('href') or ''
        text = (a.text or '').lower().strip()
        if '/android/download' in href:
            continue
        if tnorm and tnorm in text:
            target = a
            print(f'Uptodown search: matched title text={text} href={href}')
            break
    if not target and candidates:
        target = candidates[0]
        print(f'Uptodown search: fallback first candidate href={target.get("href")}')
    detail = _abs(base, target.get('href')) if target and target.get('href') else None
    print(f'Uptodown search: detail={detail}')
    return detail

def _uptodown_direct(detail_url):
    try:
        print(f'Uptodown direct: detail_url={detail_url}')
        soup = _get_soup(detail_url)
        if not soup:
            print('Uptodown direct: soup is None')
            return None
        a = soup.select_one('a[href*="/android/download"]')
        if not a:
            print('Uptodown direct: download anchor not found')
            return None
        link = _abs(detail_url, a.get('href'))
        try:
            resp = requests.get(link, timeout=15, allow_redirects=True)
            if resp.status_code == 404:
                print(f'Uptodown 404: {link}')
                return None
            else:
                print(f'Uptodown direct: probe status={resp.status_code} url={link}')
        except Exception:
            pass
        return link
    except Exception as e:
        print(f'Crawler _uptodown_direct error: {e}')
        print(traceback.format_exc())
        return None

def _gplay_list(limit=10):
    items = []
    ids_raw = os.environ.get('APP_IDS', '')
    ids = [x.strip() for x in ids_raw.split(',') if x.strip()]
    if gp_app and ids:
        for app_id in ids[:limit]:
            try:
                info = gp_app(app_id, lang='vi', country='vn')
                items.append({
                    'title': info.get('title') or app_id,
                    'icon': info.get('icon') or '',
                    'detail': app_id
                })
            except Exception as e:
                print(f'GPlay app error {app_id}: {e}')
        return items
    # Auto trending without manual IDs
    if gp_list and collections and categories:
        try:
            print('GPlay list: TOP_FREE APPLICATION')
            res = gp_list(collections.TOP_FREE, categories.APPLICATION, lang='vi', country='vn', num=limit)
            for r in res:
                app_id = r.get('appId')
                if not app_id:
                    continue
                items.append({
                    'title': r.get('title') or app_id,
                    'icon': r.get('icon') or '',
                    'detail': app_id
                })
            if len(items) < limit:
                need = limit - len(items)
                print('GPlay list: TOP_FREE GAME')
                res2 = gp_list(collections.TOP_FREE, categories.GAME, lang='vi', country='vn', num=need)
                for r in res2:
                    app_id = r.get('appId')
                    if not app_id:
                        continue
                    items.append({
                        'title': r.get('title') or app_id,
                        'icon': r.get('icon') or '',
                        'detail': app_id
                    })
        except Exception as e:
            print(f'GPlay list error: {e}')
    # Fallback search queries to fill to limit
    if len(items) < limit and gp_search:
        queries = ['Facebook', 'TikTok', 'Instagram', 'YouTube', 'Zalo', 'Shopee', 'Lazada', 'Messenger', 'PUBG Mobile', 'Lien Quan']
        for q in queries:
            if len(items) >= limit:
                break
            try:
                remain = limit - len(items)
                results = gp_search(q, lang='vi', country='vn')
                for r in results:
                    app_id = r.get('appId')
                    if not app_id:
                        continue
                    # avoid duplicates
                    if any(x['detail'] == app_id for x in items):
                        continue
                    items.append({
                        'title': r.get('title') or app_id,
                        'icon': r.get('icon') or '',
                        'detail': app_id
                    })
                    if len(items) >= limit:
                        break
            except Exception as e:
                print(f'GPlay search fallback error for "{q}": {e}')
    return items

def fetch_trending(limit=20, source='gplay'):
    out = []
    items = []
    try:
        if source == 'apkcombo':
            items = _apkcombo_list(limit=limit)
        elif source == 'apkpure':
            items = _apkpure_list(limit=limit)
        else:
            items = _gplay_list(limit=limit)
    except Exception as e:
        print(f'Crawler fetch_trending list error: {e}')
        print(traceback.format_exc())
        items = []
    if not items and source != 'apkcombo':
        try:
            items = _apkcombo_list(limit=limit)
        except Exception as e:
            print(f'Crawler fetch_trending fallback error: {e}')
            print(traceback.format_exc())
            items = []
    for it in items:
        apk_url = None
        if source == 'apkcombo':
            apk_url = _apkcombo_direct(it['detail'])
            if not apk_url:
                apk_url = _apkpure_direct(it['detail'])
        elif source == 'apkpure':
            apk_url = _apkpure_direct(it['detail'])
            if not apk_url:
                apk_url = _apkcombo_direct(it['detail'])
                if not apk_url:
                    det = _apkcombo_search_get_detail(it['title'])
                    if det:
                        apk_url = _apkcombo_direct(det)
        else:
            det = _uptodown_search_get_detail(app_id=it['detail'], title=it['title'])
            if det:
                apk_url = _uptodown_direct(det)
            else:
                print(f'Uptodown: no detail found for app_id={it["detail"]} title={it["title"]}')
            if not apk_url:
                det2 = _apkcombo_search_get_detail(it['title'])
                if det2:
                    print(f'APKCombo fallback: detail={det2}')
                    apk_url = _apkcombo_direct(det2)
                else:
                    print(f'APKCombo: no detail for title={it["title"]}')
        print(f'app_detail: {it["detail"]}')
        out.append({
            'app_id': it['detail'],
            'title': it['title'],
            'icon': it['icon'],
            'description': '',
            'apk_url': apk_url
        })
    return out

def get_apps(limit=10, source='apkpure'):
    return fetch_trending(limit=limit, source=source)
