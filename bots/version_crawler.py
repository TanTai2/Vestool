"""
Crawl old versions of apps from APKPure, Uptodown, APKCombo, and APKMirror.
Stores version history in local JSON files.

Uses cloudscraper to bypass Cloudflare protection.
"""
import os
import re
import time
import logging
import requests
import urllib.parse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/121.0.6167.85 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
    'Referer': 'https://www.google.com/',
}

_scraper = None

def _get_scraper():
    global _scraper
    if _scraper is None:
        try:
            import cloudscraper
            _scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
        except ImportError:
            logger.warning('cloudscraper not installed, falling back to requests')
            _scraper = requests.Session()
        _scraper.headers.update(HEADERS)
    return _scraper


def _get_soup(url, retries=3):
    session = _get_scraper()
    for i in range(retries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 403:
                logger.debug(f'_get_soup 403 (retry {i+1}): {url}')
                time.sleep(2 * (i + 1))
                continue
            r.raise_for_status()
            return BeautifulSoup(r.text, 'html.parser')
        except Exception as e:
            logger.debug(f'_get_soup retry {i+1} for {url}: {e}')
            time.sleep(1.5 * (i + 1))
    return None


# ---- APKPure Old Versions ----

def _apkpure_find_app_page(app_id):
    search_url = f'https://apkpure.com/search?q={urllib.parse.quote(app_id)}'
    soup = _get_soup(search_url)
    if not soup:
        return None
    for a in soup.select('a[href]'):
        href = a.get('href', '')
        if app_id in href and '/versions' not in href:
            return urllib.parse.urljoin('https://apkpure.com', href)
    for a in soup.select('a.first-info, a[href*="/"]'):
        href = a.get('href', '')
        if href and href.count('/') >= 2 and not href.startswith('http'):
            return urllib.parse.urljoin('https://apkpure.com', href)
    return None


def crawl_apkpure_versions(app_id, limit=30):
    versions = []
    app_page = _apkpure_find_app_page(app_id)
    if not app_page:
        logger.info(f'APKPure: app page not found for {app_id}')
        return versions

    versions_url = app_page.rstrip('/') + '/versions'
    logger.info(f'APKPure versions URL: {versions_url}')
    soup = _get_soup(versions_url)
    if not soup:
        return versions

    ver_items = soup.select('div.ver-item')
    if not ver_items:
        ver_items = soup.select('a.ver_download_link, li.ver-item')
    if not ver_items:
        ver_items = soup.select('div.version-list a, ul.ver-wrap li')

    seen = set()
    for item in ver_items[:limit * 2]:
        try:
            ver_name = ''
            ver_tag = item.select_one('.ver-item-n')
            if ver_tag:
                ver_name = ver_tag.get_text(strip=True)
            if not ver_name:
                ver_tag = item.select_one('.ver-info-top span, .ver_download_link')
                if ver_tag:
                    ver_name = ver_tag.get_text(strip=True)
            if not ver_name:
                ver_name = item.get_text(strip=True)

            ver_match = re.search(r'(\d+(?:\.\d+)+)', ver_name)
            if ver_match:
                ver_name = ver_match.group(1)
            else:
                continue

            if ver_name in seen:
                continue
            seen.add(ver_name)

            dl_href = item.get('href') or ''
            if not dl_href:
                dl_link = item.select_one('a[href]')
                if dl_link:
                    dl_href = dl_link.get('href', '')
            apk_url = urllib.parse.urljoin('https://apkpure.com', dl_href) if dl_href else app_page

            size_str = ''
            size_tag = item.select_one('.ver-item-s, .fsize, .size')
            if size_tag:
                size_str = size_tag.get_text(strip=True)

            date_str = ''
            date_tag = item.select_one('.update-on, .ver-item-d, .dateyear')
            if date_tag:
                date_str = date_tag.get_text(strip=True)

            versions.append({
                'version_name': ver_name,
                'apk_url': apk_url,
                'size_str': size_str,
                'release_date': date_str,
                'source': 'apkpure',
            })
            if len(versions) >= limit:
                break
        except Exception as e:
            logger.debug(f'APKPure version parse error: {e}')
    logger.info(f'APKPure: found {len(versions)} versions for {app_id}')
    return versions


# ---- Uptodown Old Versions ----

_UPTODOWN_SLUG_MAP = {
    'com.facebook.katana': 'facebook',
    'com.facebook.lite': 'facebook-lite',
    'com.facebook.orca': 'facebook-messenger',
    'com.instagram.android': 'instagram',
    'com.instagram.lite': 'instagram-lite',
    'com.ss.android.ugc.trill': 'tiktok',
    'com.zhiliaoapp.musically': 'tiktok',
    'com.whatsapp': 'whatsapp-messenger',
    'org.telegram.messenger': 'telegram',
    'com.google.android.youtube': 'youtube',
    'com.google.android.gm': 'gmail',
    'com.google.android.apps.maps': 'google-maps',
    'com.zing.zalo': 'zalo',
    'com.shopee.vn': 'shopee',
    'com.lazada.android': 'lazada',
    'com.spotify.music': 'spotify-music',
    'com.twitter.android': 'x-twitter',
    'com.snapchat.android': 'snapchat',
    'com.pinterest': 'pinterest',
    'com.tencent.ig': 'pubg-mobile',
}


def _uptodown_find_slug(app_id, title=None):
    session = _get_scraper()
    slugs = []
    if app_id in _UPTODOWN_SLUG_MAP:
        slugs.append(_UPTODOWN_SLUG_MAP[app_id])
    parts = app_id.lower().split('.')
    for part in parts:
        if part not in ('com', 'org', 'net', 'app', 'android', 'mobile', 'google', 'lite', 'pro'):
            slug = part.replace('_', '-')
            if slug and slug not in slugs:
                slugs.append(slug)
    if title:
        first = re.sub(r'[^a-z0-9]', '', title.lower().split()[0]) if title.strip() else ''
        if first and first not in slugs:
            slugs.insert(1, first)
        slug = re.sub(r'[^a-z0-9\s-]', '', title.lower().strip())
        slug = re.sub(r'\s+', '-', slug)
        if slug and slug not in slugs:
            slugs.append(slug)
    for slug in slugs:
        url = f'https://{slug}.en.uptodown.com/android'
        try:
            r = session.get(url, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                return url
        except Exception:
            pass
    return None


def crawl_uptodown_versions(app_id, title=None, limit=30):
    versions = []
    base_url = _uptodown_find_slug(app_id, title)
    if not base_url:
        logger.info(f'Uptodown: page not found for {app_id}')
        return versions

    # Uptodown uses /versions (not /old!)
    versions_url = base_url.rstrip('/') + '/versions'
    logger.info(f'Uptodown versions URL: {versions_url}')
    soup = _get_soup(versions_url)
    if not soup:
        versions_url = base_url.rstrip('/') + '/old'
        soup = _get_soup(versions_url)
    if not soup:
        return versions

    ver_items = soup.select('div[data-url][data-version-id]')
    if not ver_items:
        ver_items = soup.select('div#versions-items-list div[data-url]')
    if not ver_items:
        ver_items = soup.select('div[data-url]')

    seen = set()
    for item in ver_items[:limit * 2]:
        try:
            ver_name = ''
            ver_tag = item.select_one('span.version, .versionName, .name')
            if ver_tag:
                ver_name = ver_tag.get_text(strip=True)
            if not ver_name:
                ver_name = item.get('data-version', '')

            ver_match = re.search(r'(\d+(?:\.\d+)+)', ver_name)
            if ver_match:
                ver_name = ver_match.group(1)
            elif not ver_name:
                continue

            if ver_name in seen:
                continue
            seen.add(ver_name)

            data_url = item.get('data-url', '')
            version_id = item.get('data-version-id', '')
            apk_url = ''
            if data_url and version_id:
                # Version-specific download page: {base}/download/{version_id}
                apk_url = f'{data_url.rstrip("/")}/download/{version_id}'
            elif data_url:
                apk_url = f'{data_url.rstrip("/")}/download'

            size_str = ''
            size_tag = item.select_one('.size, .file-size')
            if size_tag:
                size_str = size_tag.get_text(strip=True)

            date_str = ''
            date_tag = item.select_one('span.date, .update-date')
            if date_tag:
                date_str = date_tag.get_text(strip=True)

            versions.append({
                'version_name': ver_name,
                'apk_url': apk_url,
                'size_str': size_str,
                'release_date': date_str,
                'source': 'uptodown',
            })
            if len(versions) >= limit:
                break
        except Exception as e:
            logger.debug(f'Uptodown version parse error: {e}')
    logger.info(f'Uptodown: found {len(versions)} versions for {app_id}')
    return versions


# ---- APKCombo Old Versions ----

def crawl_apkcombo_versions(app_id, title=None, limit=30):
    versions = []
    base = 'https://apkcombo.com'
    slug = (title or '').lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    if not slug:
        slug = app_id.split('.')[-1].lower()

    urls_to_try = [
        f'{base}/{slug}/{app_id}/old-versions/',
        f'{base}/vi/{slug}/{app_id}/old-versions/',
    ]

    soup = None
    for url in urls_to_try:
        soup = _get_soup(url)
        if soup:
            break

    if not soup:
        search_url = f'{base}/search/{urllib.parse.quote(app_id)}'
        search_soup = _get_soup(search_url)
        if search_soup:
            for a in search_soup.select('a[href]'):
                href = a.get('href', '')
                if app_id in href and '/old-versions' not in href:
                    app_page = urllib.parse.urljoin(base, href)
                    old_url = app_page.rstrip('/') + '/old-versions/'
                    soup = _get_soup(old_url)
                    if soup:
                        break

    if not soup:
        logger.info(f'APKCombo: page not found for {app_id}')
        return versions

    seen = set()
    for a in soup.select('a[href*="download"]'):
        try:
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if not href or '/download' not in href:
                continue
            ver_match = re.search(r'(\d+(?:\.\d+){2,})', href)
            if not ver_match:
                ver_match = re.search(r'(\d+(?:\.\d+){2,})', text)
            if not ver_match:
                continue
            ver_name = ver_match.group(1)
            if ver_name in seen:
                continue
            seen.add(ver_name)


            apk_url = urllib.parse.urljoin(base, href)
            date_str = ''
            date_match = re.search(r'([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})', text)
            if date_match:
                date_str = date_match.group(1)
            size_str = ''
            size_match = re.search(r'(\d+(?:\.\d+)?\s*[MG]B)', text, re.IGNORECASE)
            if size_match:
                size_str = size_match.group(1)

            versions.append({
                'version_name': ver_name,
                'apk_url': apk_url,
                'size_str': size_str,
                'release_date': date_str,
                'source': 'apkcombo',
            })
            if len(versions) >= limit:
                break
        except Exception as e:
            logger.debug(f'APKCombo version parse error: {e}')

    if not versions:
        for li in soup.select('li'):
            text = li.get_text(strip=True)
            ver_match = re.search(r'(\d+(?:\.\d+){2,})', text)
            if not ver_match:
                continue
            ver_name = ver_match.group(1)
            if ver_name in seen:
                continue
            seen.add(ver_name)
            link = li.select_one('a[href]')
            apk_url = urllib.parse.urljoin(base, link.get('href', '')) if link else ''
            date_str = ''
            date_match = re.search(r'([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})', text)
            if date_match:
                date_str = date_match.group(1)
            versions.append({
                'version_name': ver_name,
                'apk_url': apk_url,
                'size_str': '',
                'release_date': date_str,
                'source': 'apkcombo',
            })
            if len(versions) >= limit:
                break

    logger.info(f'APKCombo: found {len(versions)} versions for {app_id}')
    return versions


# ---- APKMirror Old Versions ----

def crawl_apkmirror_versions(app_id, title=None, limit=30):
    versions = []
    base = 'https://www.apkmirror.com'
    q = urllib.parse.quote((title or app_id).strip())
    search_url = f'{base}/?s={q}'
    soup = _get_soup(search_url)
    if not soup:
        return versions
    app_links = soup.select('a.fontBlack[href*="/apk/"]')
    if not app_links:
        app_links = soup.select('a[href*="/apk/"]')
    if not app_links:
        return versions
    first_href = app_links[0].get('href', '')
    if not first_href:
        return versions

    uploads_url = urllib.parse.urljoin(base, first_href)
    logger.info(f'APKMirror uploads URL: {uploads_url}')
    soup = _get_soup(uploads_url)
    if not soup:
        return versions

    seen = set()
    rows = soup.select('div.listWidget div.appRow, table.table-variants tr')
    for row in rows[:limit * 2]:
        try:
            ver_tag = row.select_one('a.fontBlack, .appRowTitle a')
            if not ver_tag:
                continue
            text = ver_tag.get_text(strip=True)
            ver_match = re.search(r'(\d+(?:\.\d+)+)', text)
            if not ver_match:
                continue
            ver_name = ver_match.group(1)
            if ver_name in seen:
                continue
            seen.add(ver_name)

            detail_href = ver_tag.get('href', '')
            apk_url = urllib.parse.urljoin(base, detail_href) if detail_href else ''
            date_str = ''
            date_tag = row.select_one('.dateyear_utc, .addedDate')
            if date_tag:
                date_str = date_tag.get_text(strip=True)
            versions.append({
                'version_name': ver_name,
                'apk_url': apk_url,
                'size_str': '',
                'release_date': date_str,
                'source': 'apkmirror',
            })
            if len(versions) >= limit:
                break
        except Exception as e:
            logger.debug(f'APKMirror version parse error: {e}')
    logger.info(f'APKMirror: found {len(versions)} versions for {app_id}')
    return versions


# ---- Main: Crawl All Sources ----

def crawl_old_versions(app_id, title=None, limit=30):
    """
    Crawl old versions from multiple sources.
    Merges results, deduplicates by version_name.
    """
    all_versions = []
    seen = set()

    # Uptodown first - it's the most reliable source for actual APK downloads
    sources = [
        ('Uptodown', lambda: crawl_uptodown_versions(app_id, title=title, limit=limit)),
        ('APKPure', lambda: crawl_apkpure_versions(app_id, limit=limit)),
        ('APKCombo', lambda: crawl_apkcombo_versions(app_id, title=title, limit=limit)),
        ('APKMirror', lambda: crawl_apkmirror_versions(app_id, title=title, limit=limit)),
    ]

    for source_name, crawl_fn in sources:
        try:
            results = crawl_fn()
            added = 0
            for v in results:
                key = v['version_name']
                if key not in seen:
                    seen.add(key)
                    all_versions.append(v)
                    added += 1
            if added > 0:
                logger.info(f'{source_name}: added {added} unique versions')
        except Exception as e:
            logger.error(f'{source_name} version crawl error: {e}')

    def ver_sort_key(v):
        try:
            parts = v['version_name'].split('.')
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return (0,)

    all_versions.sort(key=ver_sort_key, reverse=True)
    logger.info(f'Total unique versions for {app_id}: {len(all_versions)}')
    return all_versions[:limit]


def parse_size_mb(size_str):
    if not size_str:
        return 0
    m = re.search(r'([\d.]+)\s*(mb|m|gb|g|kb|k)', size_str.lower())
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit in ('gb', 'g'):
        return val * 1024
    if unit in ('kb', 'k'):
        return val / 1024
    return val


# ---- Resolve actual APK download URL from version page ----

def _resolve_apkpure_download(page_url):
    """Follow APKPure version page to find the actual APK download link."""
    # APKPure heavily blocks automated downloads - skip it
    # We keep APKPure for version metadata only
    return None


def _resolve_uptodown_download(page_url):
    """Visit Uptodown version-specific download page and get actual APK URL.
    page_url format: https://{slug}.en.uptodown.com/android/download/{version_id}
    """
    session = _get_scraper()
    try:
        # The page_url should already be a download page URL
        r = session.get(page_url, timeout=30)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')

        # Method 1: button with data-url (primary method)
        btn = soup.select_one('button#detail-download-button[data-url]')
        if btn:
            data_url = btn.get('data-url')
            if data_url and not data_url.startswith(('http', '/')):
                return f'https://dw.uptodown.com/dwn/{data_url}'

        # Method 2: direct link
        for sel in ['a[href*="dw.uptodown.com"]', 'a[href*=".apk"]',
                     'a.post-download[href]']:
            tag = soup.select_one(sel)
            if tag:
                href = tag.get('href', '')
                if href:
                    return href
    except Exception as e:
        logger.debug(f'Uptodown resolve error: {e}')
    return None


def _resolve_apkcombo_download(page_url):
    """Follow APKCombo download page to find the actual APK link."""
    soup = _get_soup(page_url)
    if not soup:
        return None
    for sel in ['a[href*=".apk"]', 'a.variant[href]', 'a[href*="download"]']:
        tag = soup.select_one(sel)
        if tag:
            href = tag.get('href', '')
            if href:
                return urllib.parse.urljoin('https://apkcombo.com', href)
    return None


def resolve_version_download(version_dict):
    """
    Given a version dict from crawling, try to resolve the actual
    downloadable APK URL (not just a page link).
    Returns (direct_url, session_or_None) or (None, None).
    """
    source = version_dict.get('source', '')
    page_url = version_dict.get('apk_url', '')

    if not page_url:
        return None, None

    try:
        if source == 'apkpure':
            url = _resolve_apkpure_download(page_url)
            return url, None
        elif source == 'uptodown':
            url = _resolve_uptodown_download(page_url)
            return url, None
        elif source == 'apkcombo':
            url = _resolve_apkcombo_download(page_url)
            return url, None
        elif source == 'apkmirror':
            # APKMirror is hard to resolve automatically (multiple variants)
            return None, None
        else:
            return None, None
    except Exception as e:
        logger.debug(f'resolve_version_download error: {e}')
        return None, None
