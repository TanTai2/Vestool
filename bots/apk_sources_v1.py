"""
APK Sources - Tìm và tải APK từ nhiều nguồn uy tín
Sources: APKPure, APKMirror, APKCombo, Uptodown, LiteAPKs, MoDYolo, AN1
"""
import os
import re
import time
import hashlib
import logging
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

logger = logging.getLogger("apk_sources")

# ============================================================
# User-Agent rotation
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def _ua():
    import random
    return random.choice(USER_AGENTS)

def _headers():
    h = dict(HEADERS_BASE)
    h["User-Agent"] = _ua()
    return h


# ============================================================
# Base Source class
# ============================================================
class BaseSource:
    name = "base"
    base_url = ""
    priority = 0

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _get(self, url, **kw):
        """GET with retry"""
        for attempt in range(3):
            try:
                async with self.session.get(url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=30), ssl=False, **kw) as r:
                    if r.status == 200:
                        return await r.text()
                    elif r.status == 429:
                        wait = 5 * (attempt + 1)
                        logger.warning(f"[{self.name}] Rate limited, waiting {wait}s")
                        await asyncio.sleep(wait)
                    else:
                        logger.debug(f"[{self.name}] GET {url} -> {r.status}")
                        return None
            except Exception as e:
                logger.debug(f"[{self.name}] GET error {url}: {e}")
                await asyncio.sleep(2)
        return None

    async def search(self, app_name: str, keywords: list) -> dict | None:
        """Search for an app, return {name, version, size, download_url, icon_url, source} or None"""
        raise NotImplementedError

    async def download(self, download_url: str, dest_path: str) -> bool:
        """Download APK to dest_path. Return True on success."""
        try:
            async with self.session.get(download_url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=600), ssl=False) as r:
                if r.status != 200:
                    logger.warning(f"[{self.name}] Download failed {r.status}: {download_url}")
                    return False
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                async with aiofiles.open(dest_path, "wb") as f:
                    async for chunk in r.content.iter_chunked(65536):
                        await f.write(chunk)
                        downloaded += len(chunk)
                if total > 0 and downloaded < total * 0.95:
                    logger.warning(f"[{self.name}] Incomplete download: {downloaded}/{total}")
                    return False
                logger.info(f"[{self.name}] Downloaded {downloaded/1048576:.1f}MB -> {dest_path}")
                return True
        except Exception as e:
            logger.error(f"[{self.name}] Download error: {e}")
            return False


# ============================================================
# APKPure
# ============================================================
class APKPureSource(BaseSource):
    name = "apkpure"
    base_url = "https://apkpure.com"
    priority = 90

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"{self.base_url}/search?q={query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        # Tìm kết quả đầu tiên
        first = soup.select_one("div.first a.first-info, a.dd, div.search-title a")
        if not first:
            # Thử selector khác
            first = soup.select_one("a[href*='/download/']") or soup.select_one(".list-wrap a")
        if not first:
            return None

        app_url = urljoin(self.base_url, first.get("href", ""))
        if not app_url or app_url == self.base_url:
            return None

        # Lấy trang detail
        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        # Version
        ver_el = dsoup.select_one("span.info-sdk span, .details-sdk span, .ver-info-m")
        if ver_el:
            result["version"] = ver_el.get_text(strip=True)

        # Icon
        icon_el = dsoup.select_one("div.icon img, img.icon-img, .apk_info img")
        if icon_el:
            result["icon_url"] = icon_el.get("src", "")

        # Size
        size_el = dsoup.select_one("span.fsize span, .info_style span, .apk_size")
        if size_el:
            result["size"] = size_el.get_text(strip=True)

        # Download link
        dl_btn = dsoup.select_one("a.da, a.download_apk_news, a[href*='APK/download'], a.is-download")
        if dl_btn:
            dl_url = urljoin(self.base_url, dl_btn.get("href", ""))
            # Follow download page
            dl_html = await self._get(dl_url)
            if dl_html:
                dl_soup = BeautifulSoup(dl_html, "html.parser")
                final = dl_soup.select_one("a#download_link, a.ga, a[href$='.apk'], a[href*='download.apkpure']")
                if final:
                    result["download_url"] = final.get("href", "")
        return result if result["download_url"] else None


# ============================================================
# APKCombo
# ============================================================
class APKComboSource(BaseSource):
    name = "apkcombo"
    base_url = "https://apkcombo.com"
    priority = 85

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"{self.base_url}/search/{query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        first = soup.select_one("div.content a.column, a.card")
        if not first:
            return None

        app_url = urljoin(self.base_url, first.get("href", ""))
        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        # Version & Size
        info = dsoup.select("div.information span, .spec span")
        for el in info:
            txt = el.get_text(strip=True)
            if re.match(r"\d+\.\d+", txt):
                result["version"] = txt
            elif "MB" in txt or "GB" in txt:
                result["size"] = txt

        # Icon
        icon_el = dsoup.select_one("img.avatar, img.icon, figure img")
        if icon_el:
            result["icon_url"] = icon_el.get("src", "")

        # Download
        dl_btn = dsoup.select_one("a.variant, a[href*='download'], a.btn-download")
        if dl_btn:
            dl_url = urljoin(self.base_url, dl_btn.get("href", ""))
            dl_html = await self._get(dl_url)
            if dl_html:
                dl_soup = BeautifulSoup(dl_html, "html.parser")
                final = dl_soup.select_one("a[href$='.apk'], a.file-list a, a[href*='download']")
                if final:
                    result["download_url"] = final.get("href", "")

        return result if result["download_url"] else None


# ============================================================
# Uptodown
# ============================================================
class UptodownSource(BaseSource):
    name = "uptodown"
    base_url = "https://en.uptodown.com/android"
    priority = 80

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"https://en.uptodown.com/android/search?q={query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        first = soup.select_one("div.search-results a, div.item a, a.name")
        if not first:
            return None

        app_url = first.get("href", "")
        if not app_url.startswith("http"):
            app_url = "https:" + app_url if app_url.startswith("//") else urljoin("https://en.uptodown.com", app_url)

        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        # Version
        ver_el = dsoup.select_one("div.version, span.version, #version-name")
        if ver_el:
            result["version"] = ver_el.get_text(strip=True)

        # Size
        size_el = dsoup.select_one("dt:contains('Size') + dd, .size")
        if not size_el:
            for dt in dsoup.select("dt"):
                if "size" in dt.get_text(strip=True).lower():
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        result["size"] = dd.get_text(strip=True)
                        break

        # Icon
        icon_el = dsoup.select_one("img.icon, img[itemprop='image'], .icon img")
        if icon_el:
            result["icon_url"] = icon_el.get("src", "")

        # Download
        dl_btn = dsoup.select_one("button.button.download, a.button.download, a[data-url], #detail-download-button")
        if dl_btn:
            dl_url = dl_btn.get("data-url") or dl_btn.get("href", "")
            if dl_url:
                if not dl_url.startswith("http"):
                    dl_url = urljoin(app_url, dl_url)
                # Uptodown usually has /download page
                if "/download" not in dl_url:
                    dl_url = app_url.rstrip("/") + "/download"
                dl_html = await self._get(dl_url)
                if dl_html:
                    dl_soup = BeautifulSoup(dl_html, "html.parser")
                    post_dl = dl_soup.select_one("a.post-download, a[data-url], a[href*='.apk']")
                    if post_dl:
                        result["download_url"] = post_dl.get("data-url") or post_dl.get("href", "")

        return result if result["download_url"] else None


# ============================================================
# LiteAPKs (mod source)
# ============================================================
class LiteAPKsSource(BaseSource):
    name = "liteapks"
    base_url = "https://liteapks.com"
    priority = 70

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"{self.base_url}/?s={query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        first = soup.select_one("article a, .post-title a, h2 a")
        if not first:
            return None

        app_url = first.get("href", "")
        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        # Extract info from detail page
        info_items = dsoup.select("ul.jejeinfo li, .jejeinfo span, .app-info li")
        for item in info_items:
            txt = item.get_text(strip=True).lower()
            if "version" in txt:
                ver = re.search(r"[\d.]+", txt)
                if ver:
                    result["version"] = ver.group()
            elif "size" in txt:
                sz = re.search(r"[\d.]+\s*[MG]B", txt, re.I)
                if sz:
                    result["size"] = sz.group()

        # Icon
        icon_el = dsoup.select_one("img.app-icon, .jejeicon img, .entry-content img")
        if icon_el:
            result["icon_url"] = icon_el.get("src", "")

        # Download button
        dl_btn = dsoup.select_one("a.jejedownloadbtn, a.download-btn, a[href*='download'], a.btn-download")
        if dl_btn:
            result["download_url"] = dl_btn.get("href", "")

        return result if result["download_url"] else None


# ============================================================
# MoDYolo (mod source)
# ============================================================
class MoDYoloSource(BaseSource):
    name = "modyolo"
    base_url = "https://modyolo.com"
    priority = 65

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"{self.base_url}/?s={query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        first = soup.select_one("article a, .post-title a, h2 a")
        if not first:
            return None

        app_url = first.get("href", "")
        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        # Extract version/size
        info_text = dsoup.get_text()
        ver_match = re.search(r"Version[:\s]*([\d.]+)", info_text, re.I)
        if ver_match:
            result["version"] = ver_match.group(1)
        size_match = re.search(r"Size[:\s]*([\d.]+\s*[MG]B)", info_text, re.I)
        if size_match:
            result["size"] = size_match.group(1)

        # Icon
        icon_el = dsoup.select_one("img.wp-post-image, article img, .entry-content img")
        if icon_el:
            result["icon_url"] = icon_el.get("src", "")

        # Download
        dl_btn = dsoup.select_one("a.download-btn, a[href*='download'], a.btn")
        if dl_btn:
            dl_url = dl_btn.get("href", "")
            dl_html = await self._get(dl_url)
            if dl_html:
                dl_soup = BeautifulSoup(dl_html, "html.parser")
                final = dl_soup.select_one("a[href$='.apk'], a.btn-download, a[href*='dl']")
                if final:
                    result["download_url"] = final.get("href", "")
                else:
                    result["download_url"] = dl_url

        return result if result["download_url"] else None


# ============================================================
# AN1 (mod source)
# ============================================================
class AN1Source(BaseSource):
    name = "an1"
    base_url = "https://an1.com"
    priority = 60

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"{self.base_url}/search/?q={query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        first = soup.select_one("div.search_results a, .apps-list a, article a")
        if not first:
            return None

        app_url = urljoin(self.base_url, first.get("href", ""))
        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        info_text = dsoup.get_text()
        ver_match = re.search(r"Version[:\s]*([\d.]+)", info_text, re.I)
        if ver_match:
            result["version"] = ver_match.group(1)
        size_match = re.search(r"Size[:\s]*([\d.]+\s*[MG]B)", info_text, re.I)
        if size_match:
            result["size"] = size_match.group(1)

        icon_el = dsoup.select_one("img.app-icon, .app-image img, img[alt]")
        if icon_el:
            result["icon_url"] = icon_el.get("src", "")

        dl_btn = dsoup.select_one("a.download-btn, a[href*='download'], a.btn-success")
        if dl_btn:
            result["download_url"] = urljoin(self.base_url, dl_btn.get("href", ""))

        return result if result["download_url"] else None


# ============================================================
# APKMirror (read-only metadata, manual download)
# ============================================================
class APKMirrorSource(BaseSource):
    name = "apkmirror"
    base_url = "https://www.apkmirror.com"
    priority = 95

    async def search(self, app_name: str, keywords: list) -> dict | None:
        query = quote(app_name)
        html = await self._get(f"{self.base_url}/?post_type=app_release&searchtype=apk&s={query}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        first = soup.select_one("div.appRow h5 a, .listWidget a.fontBlack")
        if not first:
            return None

        app_url = urljoin(self.base_url, first.get("href", ""))
        detail_html = await self._get(app_url)
        if not detail_html:
            return None
        dsoup = BeautifulSoup(detail_html, "html.parser")

        result = {
            "name": app_name,
            "version": "",
            "size": "",
            "download_url": "",
            "icon_url": "",
            "source": self.name,
            "detail_url": app_url,
        }

        # Version from title
        title_el = dsoup.select_one("h1.app-title, .appRowTitle")
        if title_el:
            ver_match = re.search(r"([\d]+\.[\d.]+)", title_el.get_text())
            if ver_match:
                result["version"] = ver_match.group(1)

        # Icon
        icon_el = dsoup.select_one("img.logo-img, .appRowIcon img, img[src*='icon']")
        if icon_el:
            src = icon_el.get("src", "")
            if src and not src.startswith("http"):
                src = urljoin(self.base_url, src)
            result["icon_url"] = src

        # APKMirror requires clicks / JS for downloads - get the download page URL
        dl_link = dsoup.select_one("a.accent_bg, a[href*='download'], a.downloadButton")
        if dl_link:
            dl_page = urljoin(self.base_url, dl_link.get("href", ""))
            dl_html = await self._get(dl_page)
            if dl_html:
                dl_soup = BeautifulSoup(dl_html, "html.parser")
                final = dl_soup.select_one("a[href*='download.php'], a.accent_bg[href*='key=']")
                if final:
                    result["download_url"] = urljoin(self.base_url, final.get("href", ""))

        return result if result.get("download_url") else None


# ============================================================
# Source Manager - quản lý tất cả source, tìm tốt nhất
# ============================================================
ALL_SOURCES = [
    APKMirrorSource,
    APKPureSource,
    APKComboSource,
    UptodownSource,
    LiteAPKsSource,
    MoDYoloSource,
    AN1Source,
]


class SourceManager:
    """Quản lý tất cả nguồn APK, tìm bản tốt nhất"""

    def __init__(self, session: aiohttp.ClientSession, max_concurrent: int = 3):
        self.sources = sorted(
            [src(session) for src in ALL_SOURCES],
            key=lambda s: s.priority,
            reverse=True,
        )
        self.session = session
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.temp_dir = Path("/root/VesTool/tmp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def _search_source(self, source: BaseSource, app_name: str, keywords: list) -> dict | None:
        async with self.semaphore:
            try:
                return await source.search(app_name, keywords)
            except Exception as e:
                logger.warning(f"[{source.name}] Search error for '{app_name}': {e}")
                return None

    async def find_best(self, app_name: str, keywords: list = None) -> dict | None:
        """
        Tìm APK từ tất cả nguồn song song, trả về kết quả tốt nhất
        (ưu tiên source có priority cao nhất mà tìm thấy)
        """
        if keywords is None:
            keywords = [app_name]

        tasks = [
            self._search_source(src, app_name, keywords)
            for src in self.sources
        ]
        results = await asyncio.gather(*tasks)

        # Lọc kết quả hợp lệ, sắp xếp theo priority
        valid = []
        for src, result in zip(self.sources, results):
            if result and result.get("download_url"):
                result["_priority"] = src.priority
                valid.append(result)

        if not valid:
            logger.warning(f"No source found for: {app_name}")
            return None

        valid.sort(key=lambda r: r["_priority"], reverse=True)
        best = valid[0]
        del best["_priority"]
        logger.info(f"Best source for '{app_name}': {best['source']} v{best.get('version', '?')}")
        return best

    async def download_apk(self, app_info: dict, dest_dir: str = None) -> str | None:
        """
        Tải APK về local. Trả về đường dẫn file hoặc None.
        """
        if not dest_dir:
            dest_dir = str(self.temp_dir)

        url = app_info.get("download_url", "")
        if not url:
            return None

        slug = app_info.get("slug", app_info.get("name", "unknown").lower().replace(" ", "-"))
        slug = re.sub(r'[^a-z0-9_-]', '', slug)
        filename = f"{slug}.apk"
        dest_path = os.path.join(dest_dir, filename)

        # Tìm source phù hợp để download
        source_name = app_info.get("source", "")
        source = next((s for s in self.sources if s.name == source_name), self.sources[0])

        success = await source.download(url, dest_path)
        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000:
            # Tính MD5
            md5 = hashlib.md5()
            async with aiofiles.open(dest_path, "rb") as f:
                while True:
                    chunk = await f.read(65536)
                    if not chunk:
                        break
                    md5.update(chunk)
            app_info["md5"] = md5.hexdigest()
            app_info["file_size"] = os.path.getsize(dest_path)
            app_info["local_path"] = dest_path
            return dest_path

        logger.error(f"Download failed for {app_info.get('name', '?')}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return None
