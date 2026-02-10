#!/usr/bin/env python3
"""
Uptodown Trending Crawler - Cào 10000 app trending nhất
Chỉ cào metadata (icon, title, description, versions) - KHÔNG tải APK
APK sẽ được tải on-demand khi user request

Tối ưu tốc độ với:
- Async HTTP requests (aiohttp)
- Concurrent workers
- Connection pooling
- Rate limiting thông minh
"""

import asyncio
import aiohttp
import json
import os
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import hashlib

# Import Telegram metadata uploader
try:
    from telegram_metadata import batch_upload_apps, upload_app_metadata
    TELEGRAM_UPLOAD_AVAILABLE = True
except ImportError:
    TELEGRAM_UPLOAD_AVAILABLE = False
    print('⚠️ Telegram metadata upload not available')

# ============ CONFIG ============
MAX_APPS = 30000  # Số app tối đa cào
CONCURRENT_WORKERS = 50  # Số worker đồng thời
BATCH_SIZE = 100  # Số app mỗi batch
REQUEST_DELAY = 0.05  # Delay giữa các request (50ms)
TIMEOUT = 30  # Timeout cho mỗi request
MAX_RETRIES = 3  # Số lần retry khi fail
MAX_VERSIONS = 30  # Số phiên bản tối đa mỗi app
CRAWL_VERSIONS = True  # Có cào phiên bản hay không
AUTO_UPLOAD_TELEGRAM = True  # Tự động upload lên Telegram không cần confirm

DATA_DIR = '/root/VesTool/data'
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')
VERSIONS_DIR = os.path.join(DATA_DIR, 'versions')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
}

# Base URLs - Fixed structure for Uptodown 2024
UPTODOWN_BASE = 'https://en.uptodown.com'

# Category URLs to scrape (each has pagination)
CATEGORIES = [
    '/android/games',
    '/android/games/action',
    '/android/games/adventure',
    '/android/games/arcade',
    '/android/games/racing',
    '/android/games/sports-games',
    '/android/games/strategy',
    '/android/games/role-playing',
    '/android/games/simulation',
    '/android/games/casino',
    '/android/games/puzzle',
    '/android/games/board',
    '/android/games/music',
    '/android/communication',
    '/android/multimedia',
    '/android/multimedia/video',
    '/android/multimedia/audio',
    '/android/multimedia/photography',
    '/android/productivity',
    '/android/tools',
    '/android/lifestyle',
    '/android/social',
    '/android/shopping',
    '/android/travel',
    '/android/finance',
    '/android/education',
    '/android/health-wellness',
    '/android/editors-choice',
]

# ============ HELPERS ============

def extract_app_id_from_url(url):
    """Extract package name từ Uptodown URL hoặc page content."""
    # URL format: https://xxx.en.uptodown.com/android
    match = re.search(r'https://([^.]+)\.en\.uptodown\.com', url)
    if match:
        slug = match.group(1)
        # Convert slug to approximate package name
        return slug.replace('-', '_')
    return None


def normalize_icon_url(icon_url):
    """Ensure icon URL is valid."""
    if not icon_url:
        return ''
    if icon_url.startswith('//'):
        return 'https:' + icon_url
    if not icon_url.startswith('http'):
        return ''
    return icon_url


def safe_filename(app_id):
    """Convert app_id to safe filename."""
    return app_id.replace('.', '_')


# ============ ASYNC SCRAPER ============

class UptodownCrawler:
    def __init__(self):
        self.session = None
        self.apps = {}  # app_id -> app_data
        self.existing_apps = {}  # Load existing data
        self.stats = {
            'pages_scraped': 0,
            'apps_found': 0,
            'apps_detailed': 0,
            'errors': 0,
            'start_time': 0,
        }
        self.semaphore = None
        self.rate_limiter = None
    
    async def init_session(self):
        """Initialize aiohttp session with connection pooling."""
        connector = aiohttp.TCPConnector(
            limit=CONCURRENT_WORKERS,
            limit_per_host=20,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=HEADERS,
        )
        self.semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)
        self.rate_limiter = asyncio.Semaphore(100)  # Max 100 concurrent requests
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    def load_existing_data(self):
        """Load existing apps.json to preserve Telegram links."""
        if os.path.exists(APPS_FILE):
            try:
                with open(APPS_FILE, 'r', encoding='utf-8') as f:
                    apps_list = json.load(f)
                    for app in apps_list:
                        app_id = app.get('app_id')
                        if app_id:
                            self.existing_apps[app_id] = app
                print(f'📂 Loaded {len(self.existing_apps)} existing apps')
            except Exception as e:
                print(f'⚠️ Error loading existing data: {e}')
    
    async def fetch(self, url, retries=MAX_RETRIES):
        """Fetch URL with retry and rate limiting."""
        async with self.rate_limiter:
            for attempt in range(retries):
                try:
                    await asyncio.sleep(REQUEST_DELAY)
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            return await resp.text()
                        elif resp.status == 429:
                            # Rate limited - wait and retry
                            wait_time = 5 * (attempt + 1)
                            print(f'⏳ Rate limited, waiting {wait_time}s...')
                            await asyncio.sleep(wait_time)
                        elif resp.status == 404:
                            return None
                        else:
                            print(f'⚠️ HTTP {resp.status} for {url[:60]}')
                except asyncio.TimeoutError:
                    print(f'⏱️ Timeout for {url[:60]}')
                except Exception as e:
                    print(f'❌ Error fetching {url[:60]}: {e}')
                
                if attempt < retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
            
            self.stats['errors'] += 1
            return None
    
    async def scrape_category_page(self, category, page=1):
        """Scrape một trang category."""
        if page == 1:
            url = f'{UPTODOWN_BASE}{category}'
        else:
            url = f'{UPTODOWN_BASE}{category}/{page}'
        
        html = await self.fetch(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        apps = []
        seen_urls = set()
        
        # Find all app links with format: {app-slug}.en.uptodown.com/android
        for link_el in soup.select('a[href*=".en.uptodown.com/android"]'):
            try:
                app_url = link_el.get('href', '')
                if not app_url or '.en.uptodown.com/android' not in app_url:
                    continue
                
                # Deduplicate URLs on same page
                if app_url in seen_urls:
                    continue
                seen_urls.add(app_url)
                
                # Extract basic info from link text/image
                title = link_el.get_text(strip=True) or ''
                icon = ''
                
                # Try to get icon from nearby img
                img = link_el.select_one('img')
                if img:
                    icon = img.get('src') or img.get('data-src', '')
                    icon = normalize_icon_url(icon)
                
                apps.append({
                    'url': app_url,
                    'title': title,
                    'icon': icon,
                })
            except Exception as e:
                continue
        
        self.stats['pages_scraped'] += 1
        return apps
    
    async def scrape_app_detail(self, app_url, basic_info=None):
        """Scrape chi tiết một app từ Uptodown."""
        async with self.semaphore:
            html = await self.fetch(app_url)
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            try:
                # Title
                title_el = soup.select_one('h1.name, h1.detail-title, h1')
                title = title_el.get_text(strip=True) if title_el else (basic_info or {}).get('title', '')
                
                # Icon - Priority: og:image (always correct), then img.utdstc.com links
                icon = ''
                
                # Priority 1: og:image meta tag (most reliable)
                og_image = soup.select_one('meta[property="og:image"]')
                if og_image:
                    icon = og_image.get('content', '')
                    if icon and 'img.utdstc.com/icon' in icon:
                        icon = normalize_icon_url(icon)
                
                # Priority 2: Find any img with img.utdstc.com/icon
                if not icon or 'utdstc.com/icon' not in icon:
                    for img in soup.select('img[src*="img.utdstc.com/icon"], img[data-src*="img.utdstc.com/icon"]'):
                        icon_url = img.get('src') or img.get('data-src', '')
                        if icon_url and 'img.utdstc.com/icon' in icon_url:
                            icon = normalize_icon_url(icon_url)
                            break
                
                # Priority 3: Search in srcset
                if not icon or 'utdstc.com/icon' not in icon:
                    for img in soup.select('img[srcset*="img.utdstc.com/icon"]'):
                        srcset = img.get('srcset', '')
                        match = re.search(r'(https://img\.utdstc\.com/icon[^\s,]+)', srcset)
                        if match:
                            icon = normalize_icon_url(match.group(1))
                            break
                
                # Priority 4: Regex search in HTML for icon URL
                if not icon or 'utdstc.com/icon' not in icon:
                    icon_match = re.search(r'https://img\.utdstc\.com/icon/[a-f0-9]+/[a-f0-9]+/[a-f0-9]+(?::\d+)?', html)
                    if icon_match:
                        icon = icon_match.group(0)
                        # Add :200 size suffix if not present
                        if ':' not in icon:
                            icon = icon + ':200'
                
                if not icon:
                    icon = (basic_info or {}).get('icon', '')
                
                # Package name - try to find in page
                pkg_el = soup.select_one('[class*="package"], .technical-data .package')
                if pkg_el:
                    app_id = pkg_el.get_text(strip=True)
                else:
                    # Try to find in script or meta
                    pkg_match = re.search(r'"package"\s*:\s*"([^"]+)"', html)
                    if pkg_match:
                        app_id = pkg_match.group(1)
                    else:
                        # Use URL slug as fallback
                        slug_match = re.search(r'https://([^.]+)\.en\.uptodown\.com', app_url)
                        if slug_match:
                            app_id = f'com.uptodown.{slug_match.group(1).replace("-", "")}'
                        else:
                            app_id = hashlib.md5(app_url.encode()).hexdigest()[:16]
                
                # Description - try multiple sources
                description = ''
                
                # Priority 1: Meta description (usually most complete)
                meta_desc = soup.select_one('meta[name="description"]')
                if meta_desc:
                    description = meta_desc.get('content', '').strip()
                
                # Priority 2: OG description
                if not description:
                    og_desc = soup.select_one('meta[property="og:description"]')
                    if og_desc:
                        description = og_desc.get('content', '').strip()
                
                # Priority 3: Page content description
                if not description:
                    for sel in ['.description', '#description', '.detail-description', '.app-description', '.content p']:
                        desc_el = soup.select_one(sel)
                        if desc_el:
                            desc_text = desc_el.get_text(strip=True)
                            if len(desc_text) > 30:  # Only take meaningful descriptions
                                description = desc_text
                                break
                
                # Clean and limit description
                if description:
                    # Remove download/APK promotional text
                    description = re.sub(r'Download.*?for free\.?\s*', '', description, flags=re.IGNORECASE)
                    description = re.sub(r'.*?APK.*?for Android.*?\.\s*', '', description, flags=re.IGNORECASE) 
                    description = description.strip()
                    # Limit to reasonable length but allow longer descriptions
                    description = description[:1000] if len(description) > 1000 else description
                
                # Version
                ver_el = soup.select_one('.version, .detail-version, [itemprop="softwareVersion"]')
                version = ver_el.get_text(strip=True) if ver_el else ''
                
                # Size
                size_el = soup.select_one('.size, .detail-size, .file-size')
                size_text = size_el.get_text(strip=True) if size_el else ''
                size_mb = 0
                if size_text:
                    size_match = re.search(r'([\d.]+)\s*(MB|GB|KB)', size_text, re.I)
                    if size_match:
                        val = float(size_match.group(1))
                        unit = size_match.group(2).upper()
                        if unit == 'GB':
                            size_mb = val * 1024
                        elif unit == 'KB':
                            size_mb = val / 1024
                        else:
                            size_mb = val
                
                # APK download URL (Uptodown detail page, NOT actual APK)
                # Actual APK sẽ được resolve khi user request
                apk_page_url = app_url.rstrip('/') + '/download'
                
                # Build result
                result = {
                    'app_id': app_id,
                    'title': title,
                    'icon': icon,
                    'description': description,
                    'version': version,
                    'apk_size_mb': round(size_mb, 2),
                    'uptodown_url': app_url,
                    'uptodown_download': apk_page_url,
                    'apk_url': '',  # Will be filled on-demand
                    'telegram_link': '',  # Will be filled when uploaded
                    'local_apk_url': '',
                    'channel2_link': '',
                    'date': datetime.now().isoformat(),
                    'source': 'uptodown',
                }
                
                # Preserve existing Telegram data if available
                existing = self.existing_apps.get(app_id, {})
                if existing.get('telegram_link'):
                    result['telegram_link'] = existing['telegram_link']
                    result['local_apk_url'] = existing.get('local_apk_url', '')
                if existing.get('channel2_link'):
                    result['channel2_link'] = existing['channel2_link']
                
                self.stats['apps_detailed'] += 1
                return result
                
            except Exception as e:
                print(f'❌ Error parsing {app_url[:50]}: {e}')
                self.stats['errors'] += 1
                return None
    
    async def scrape_app_versions(self, app_url, app_id):
        """Cào danh sách phiên bản cũ từ /versions page."""
        versions = []
        versions_url = app_url.rstrip('/') + '/versions'
        
        html = await self.fetch(versions_url)
        if not html:
            # Try /old as fallback
            versions_url = app_url.rstrip('/') + '/old'
            html = await self.fetch(versions_url)
        
        if not html:
            return versions
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find version items - multiple selector strategies
        ver_items = soup.select('div[data-url][data-version-id]')
        if not ver_items:
            ver_items = soup.select('div#versions-items-list div[data-url]')
        if not ver_items:
            ver_items = soup.select('div[data-url]')
        
        seen = set()
        for item in ver_items[:MAX_VERSIONS * 2]:
            try:
                # Version name
                ver_name = ''
                ver_tag = item.select_one('span.version, .versionName, .name')
                if ver_tag:
                    ver_name = ver_tag.get_text(strip=True)
                if not ver_name:
                    ver_name = item.get('data-version', '')
                
                # Extract version number
                ver_match = re.search(r'(\d+(?:\.\d+)+)', ver_name)
                if ver_match:
                    ver_name = ver_match.group(1)
                elif not ver_name:
                    continue
                
                if ver_name in seen:
                    continue
                seen.add(ver_name)
                
                # Download URL
                data_url = item.get('data-url', '')
                version_id = item.get('data-version-id', '')
                apk_url = ''
                if data_url and version_id:
                    apk_url = f'{data_url.rstrip("/")}/download/{version_id}'
                elif data_url:
                    apk_url = f'{data_url.rstrip("/")}/download'
                
                # Size
                size_str = ''
                size_tag = item.select_one('.size, .file-size')
                if size_tag:
                    size_str = size_tag.get_text(strip=True)
                
                # Date
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
                
                if len(versions) >= MAX_VERSIONS:
                    break
                    
            except Exception as e:
                continue
        
        return versions
    
    def save_versions(self, app_id, versions):
        """Lưu danh sách phiên bản vào file JSON."""
        if not versions:
            return False
        
        os.makedirs(VERSIONS_DIR, exist_ok=True)
        filename = safe_filename(app_id) + '.json'
        filepath = os.path.join(VERSIONS_DIR, filename)
        
        data = {
            'app_id': app_id,
            'versions': versions,
            'updated_at': datetime.now().isoformat(),
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True
    
    async def scrape_all_category_pages(self):
        """Cào tất cả các trang từ các danh mục để lấy danh sách app."""
        print('🔍 Đang cào danh sách app từ Uptodown categories...')
        
        all_apps = []
        seen_urls = set()
        
        for category in CATEGORIES:
            page = 1
            # Increase max pages per category to ensure we get 10k apps
            max_pages_per_category = 100  # Increased from calculated value
            
            print(f'📁 Category: {category}')
            
            while len(all_apps) < MAX_APPS and page <= max_pages_per_category:
                apps = await self.scrape_category_page(category, page)
                if not apps:
                    print(f'  📄 Trang {page}: không có app, chuyển category.')
                    break
                
                # Add only new apps
                new_count = 0
                for app in apps:
                    if app['url'] not in seen_urls:
                        seen_urls.add(app['url'])
                        all_apps.append(app)
                        new_count += 1
                
                print(f'  📄 Trang {page}: +{new_count} apps mới (tổng: {len(all_apps)})')
                
                if new_count == 0:
                    break  # No new apps found, move to next category
                
                page += 1
            
            if len(all_apps) >= MAX_APPS:
                print(f'✅ Đã đạt {MAX_APPS} apps, dừng cào.')
                break
        
        self.stats['apps_found'] = len(all_apps)
        print(f'✅ Tìm thấy {len(all_apps)} apps unique')
        return all_apps[:MAX_APPS]
    
    async def scrape_app_details_batch(self, apps):
        """Cào chi tiết nhiều apps cùng lúc."""
        print(f'🔎 Đang cào chi tiết {len(apps)} apps...')
        
        results = []
        batch_num = 0
        
        for i in range(0, len(apps), BATCH_SIZE):
            batch = apps[i:i+BATCH_SIZE]
            batch_num += 1
            
            tasks = [
                self.scrape_app_detail(app['url'], app)
                for app in batch
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if result and not isinstance(result, Exception):
                    results.append(result)
            
            # Progress update
            elapsed = time.time() - self.stats['start_time']
            rate = self.stats['apps_detailed'] / elapsed if elapsed > 0 else 0
            print(f'📦 Batch {batch_num}: {len(results)}/{len(apps)} apps ({rate:.1f} apps/s)')
            
            # Small delay between batches
            await asyncio.sleep(0.5)
        
        return results
    
    async def scrape_versions_batch(self, apps):
        """Cào phiên bản cho nhiều apps cùng lúc."""
        if not CRAWL_VERSIONS:
            print('⏭️ Bỏ qua crawl phiên bản (CRAWL_VERSIONS=False)')
            return 0
        
        print(f'📚 Đang cào phiên bản cho {len(apps)} apps...')
        
        versions_count = 0
        batch_num = 0
        
        for i in range(0, len(apps), BATCH_SIZE):
            batch = apps[i:i+BATCH_SIZE]
            batch_num += 1
            
            tasks = []
            for app in batch:
                app_url = app.get('uptodown_url', '')
                app_id = app.get('app_id', '')
                if app_url and app_id:
                    tasks.append(self.scrape_app_versions(app_url, app_id))
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Save versions
            for j, result in enumerate(batch_results):
                if result and not isinstance(result, Exception) and len(result) > 0:
                    app_id = batch[j].get('app_id', '')
                    if app_id and self.save_versions(app_id, result):
                        versions_count += 1
            
            # Progress update
            print(f'📚 Batch {batch_num}: {versions_count} apps có phiên bản')
            
            await asyncio.sleep(0.3)
        
        return versions_count
    
    def save_apps(self, apps, upload_to_telegram=True):
        """Save apps to JSON file."""
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Merge with existing apps that have Telegram links
        apps_dict = {app['app_id']: app for app in apps}
        
        # Add existing apps with Telegram links that weren't in this crawl
        for app_id, existing in self.existing_apps.items():
            if app_id not in apps_dict and existing.get('telegram_link'):
                apps_dict[app_id] = existing
        
        # Sort by date (newest first)
        apps_list = sorted(
            apps_dict.values(),
            key=lambda x: x.get('date', ''),
            reverse=True
        )
        
        with open(APPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(apps_list, f, ensure_ascii=False, indent=2)
        
        print(f'💾 Đã lưu {len(apps_list)} apps vào {APPS_FILE}')
        
        # Upload metadata to Telegram for memory optimization
        if upload_to_telegram and TELEGRAM_UPLOAD_AVAILABLE:
            print('📤 Uploading new apps metadata to Telegram...')
            
            # Only upload NEW apps (not existing ones)
            new_apps = [app for app in apps if app.get('app_id') not in self.existing_apps]
            if new_apps:
                print(f'📤 Uploading {len(new_apps)} new apps to Telegram metadata channel...')
                uploaded, failed = batch_upload_apps(new_apps)
                print(f'📊 Telegram upload: ✅ {uploaded} | ❌ {failed}')
            else:
                print('📝 No new apps to upload to Telegram')
        
        return len(apps_list)
    
    async def run(self):
        """Main crawl function."""
        print('=' * 60)
        print('🚀 UPTODOWN TRENDING CRAWLER')
        print(f'📊 Target: {MAX_APPS} apps')
        print(f'⚡ Workers: {CONCURRENT_WORKERS}')
        print(f'📚 Crawl versions: {CRAWL_VERSIONS}')
        print('=' * 60)
        
        self.stats['start_time'] = time.time()
        
        # Load existing data
        self.load_existing_data()
        
        # Initialize session
        await self.init_session()
        
        try:
            # Step 1: Get all apps list from categories
            apps_list = await self.scrape_all_category_pages()
            
            if not apps_list:
                print('❌ Không tìm thấy apps nào!')
                return
            
            # Step 2: Scrape details for all apps
            detailed_apps = await self.scrape_app_details_batch(apps_list)
            
            # Step 3: Crawl versions for all apps
            versions_saved = 0
            if CRAWL_VERSIONS:
                versions_saved = await self.scrape_versions_batch(detailed_apps)
            
            # Step 4: Save to file and optionally upload to Telegram
            upload_to_tg = AUTO_UPLOAD_TELEGRAM
            if upload_to_tg:
                print('📤 Auto-uploading to Telegram (AUTO_UPLOAD_TELEGRAM=True)...')
            total_saved = self.save_apps(detailed_apps, upload_to_telegram=upload_to_tg)
            
            # Final stats
            elapsed = time.time() - self.stats['start_time']
            print('=' * 60)
            print('✅ HOÀN TẤT!')
            print(f'📄 Trang đã cào: {self.stats["pages_scraped"]}')
            print(f'🔍 Apps tìm thấy: {self.stats["apps_found"]}')
            print(f'📦 Apps chi tiết: {self.stats["apps_detailed"]}')
            print(f'📚 Apps có versions: {versions_saved}')
            print(f'💾 Apps đã lưu: {total_saved}')
            print(f'❌ Lỗi: {self.stats["errors"]}')
            print(f'⏱️ Thời gian: {elapsed:.1f}s')
            print(f'⚡ Tốc độ: {self.stats["apps_detailed"]/elapsed:.1f} apps/s')
            print('=' * 60)
            
        finally:
            await self.close_session()


async def main():
    crawler = UptodownCrawler()
    await crawler.run()


if __name__ == '__main__':
    # Run with uvloop if available for better performance
    try:
        import uvloop
        uvloop.install()
        print('🚀 Using uvloop for better performance')
    except ImportError:
        pass
    
    asyncio.run(main())
