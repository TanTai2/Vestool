import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

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
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 403 and 'apkpure.com' in url:
            alt_url = url.replace('apkpure.com/', 'apkpure.com/vn/')
            r = session.get(alt_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except requests.RequestException:
        return None

def _apkpure_list(limit=10):
    base = 'https://apkpure.com'
    url = f'{base}/latest-updates'
    soup = _get_soup(url)
    apps = []
    if not soup:
        return apps
    # Selector chuẩn hơn cho giao diện mới của APKPure
    cards = soup.select('div.category-template li, div.app-list li')
    for c in cards:
        a = c.find('a')
        if not a: 
            continue
        href = a.get('href') or ''
        if not href or '/download' in href: 
            continue
        title = (c.find('dt') or a).text.strip()
        img_tag = c.find('img')
        img = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
        detail = _abs(base, href)
        apps.append({'title': title, 'icon': img, 'detail': detail})
        if len(apps) >= limit: 
            break
    return apps

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
    except:
        return None

def _apkcombo_list(limit=10):
    base = 'https://apkcombo.com'
    url = f'{base}/vi/latest/'
    soup = _get_soup(url)
    apps = []
    if not soup:
    if not cards:
        cards = soup.select('a[href^="/vi/"]')
        return apps
    cards = soup.select('div.list-state li a')
    for a in cards:
        href = a.get('href') or ''
        if not href or '/download/' in href: 
            continue
        title = a.select_one('div.name').text.strip() if a.select_one('div.name') else a.text.strip()
        img_tag = a.find('img')
        img = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
        detail = _abs(base, href)
        apps.append({'title': title, 'icon': img, 'detail': detail})
        if len(apps) >= limit: 

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
    except:
        return None

def fetch_trending(limit=10, source='apkpure'):
    out = []
    items = []
    try:
        items = _apkcombo_list(limit=limit) if source == 'apkcombo' else _apkpure_list(limit=limit)
    except Exception:
        items = []
    if not items and source == 'apkpure':
        try:
            items = _apkcombo_list(limit=limit)
        except Exception:
            items = []
    for it in items:
        apk_url = None
        if source == 'apkcombo':
            apk_url = _apkcombo_direct(it['detail'])
            if not apk_url:
                apk_url = _apkpure_direct(it['detail'])
        else:
            apk_url = _apkpure_direct(it['detail'])
            if not apk_url:
                apk_url = _apkcombo_direct(it['detail'])
        out.append({
            'app_id': it['detail'],
            'title': it['title'],
            'icon': it['icon'],
            'description': '',
            'apk_url': apk_url
        })
    return out
