"""
APK Sources - Tìm và tải APK từ nguồn uy tín
Nguồn chính: Uptodown (không Cloudflare, hỗ trợ download token)
Nguồn metadata: Google Play Scraper

Flow: search slug → detail page → download page → token → dw.uptodown.com/dwn/{token}
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

_ua_idx = 0
def _ua():
    global _ua_idx
    _ua_idx = (_ua_idx + 1) % len(USER_AGENTS)
    return USER_AGENTS[_ua_idx]

def _headers():
    return {
        "User-Agent": _ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }


# ============================================================
# Slugify helpers
# ============================================================
def _to_uptodown_slug(name: str) -> str:
    """Convert app name to uptodown URL slug.
    'Spotify' -> 'spotify'
    'VLC Media Player' -> 'vlc-media-player'
    'CapCut' -> 'capcut'
    """
    # Remove mod/pro/premium suffixes
    clean = re.sub(r'\s+(Mod|Pro|Premium|Gold|Diamond|VIP|Plus|Full|Lite|Hack|Patched)\b', '', name, flags=re.IGNORECASE)
    clean = clean.strip()
    # Slugify
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', clean)
    slug = re.sub(r'\s+', '-', slug).lower().strip('-')
    return slug

# Common app name -> uptodown slug mappings for apps that don't follow standard pattern
SLUG_OVERRIDES = {
    "youtube-revanced": "youtube",
    "spotify-premium-mod": "spotify",
    "spotify-lite-mod": "spotify-lite",
    "tiktok-mod": "tiktok",
    "tiktok-lite-mod": "tiktok-lite",
    "netflix-mod": "netflix",
    "soundcloud-mod": "soundcloud",
    "deezer-premium-mod": "deezer-music",
    "tidal-hifi-mod": "tidal-music",
    "joox-vip-mod": "joox",
    "zing-mp3-premium-mod": "zing-mp3",
    "nhaccuatui-vip-mod": "nhaccuatui",
    "hbo-max-mod": "hbo-max",
    "disney-mod": "disney-plus",
    "prime-video-mod": "amazon-prime-video",
    "twitch-mod": "twitch",
    "bilibili-mod": "bilibili",
    "capcut-pro-mod": "capcut",
    "adobe-lightroom-premium-mod": "adobe-lightroom",
    "picsart-gold-mod": "picsart",
    "vsco-premium-mod": "vsco",
    "snapseed-pro-mod": "snapseed",
    "faceapp-pro-mod": "faceapp",
    "remini-mod": "remini",
    "kinemaster-diamond-mod": "kinemaster",
    "powerdirector-premium-mod": "powerdirector",
    "filmorago-pro-mod": "filmorago",
    "inshot-pro-mod": "inshot",
    "vivavideo-pro-mod": "vivavideo",
    "alight-motion-pro-mod": "alight-motion",
    "canva-pro-mod": "canva",
    "duolingo-plus-mod": "duolingo",
    "photomath-plus-mod": "photomath",
    "minecraft-pe-mod": "minecraft",
    "stardew-valley-mod": "stardew-valley",
    "terraria-mod": "terraria",
    "dead-cells-mod": "dead-cells",
    "plants-vs-zombies-12-mod": "plants-vs-zombies-2",
    "subway-surfers-mod": "subway-surfers",
    "hill-climb-racing-12-mod": "hill-climb-racing-2",
    "expressvpn-mod": "expressvpn",
    "nordvpn-mod": "nordvpn",
    "surfshark-mod": "surfshark-vpn",
    "solid-explorer-pro-mod": "solid-explorer",
    "mixplorer-silver-mod": "mixplorer",
    "microsoft-office-mod": "microsoft-365",
    "wps-office-premium-mod": "wps-office",
    "myfitnesspal-premium-mod": "myfitnesspal",
    "strava-premium-mod": "strava",
    "spotify-equalizer-pro-mod": "equalizer",
    "calm-premium-mod": "calm",
    "headspace-premium-mod": "headspace",
    "lucky-patcher": "lucky-patcher",
    "gameguardian": "gameguardian",
    "parallel-space-vip-mod": "parallel-space",
    "maps-me-pro-mod": "maps-me-lite",
    "sygic-gps-navigation-mod": "sygic",
    "waze-mod": "waze",
    "stremio-mod": "stremio",
    "kodi-mod": "kodi",
    "filmplus-mod": "filmplus",
    "beetv-mod": "beetv",
    "live-nettv-mod": "live-nettv",
    "cinema-hd-mod": "cinema-hd-v2",
    "crunchyroll-mod": "crunchyroll",
    "funimation-mod": "funimation",
    "viki-mod": "viki",
    "iqiyi-mod": "iqiyi",
    "wetv-mod": "wetv",
    "viu-mod": "viu",
    "mangotv-mod": "mango-tv",
    "hulu-mod": "hulu",
    "peacock-tv-mod": "peacock-tv",
    "paramount-mod": "paramount-plus",
    "plex-mod": "plex",
    "mxplayer-pro-mod": "mxplayer",
    "vlc-pro-mod": "vlc",
    "kmplayer-premium-mod": "kmplayer",
    "b612-mod": "b612",
    "snow-mod": "snow",
    "meitu-mod": "meitu",
    "vn-video-editor-mod": "vn-video-editor",
    "moon-reader-pro-mod": "moon-reader",
    "camscanner-pro-mod": "camscanner",
    "soul-knight-mod": "soul-knight",
    "angry-birds-series-mod": "angry-birds-2",
    "plants-vs-zombies-12-mod": "plants-vs-zombies-2",
    "sd-maid-pro-mod": "sd-maid",
    "ccleaner-pro-mod": "ccleaner",
    "titanium-backup-pro-mod": "titanium-backup",
    "accubattery-pro-mod": "accubattery",
    "forest-premium-mod": "forest-stay-focused",
    "ticktick-premium-mod": "ticktick",
    "todoist-pro-mod": "todoist",
    "notion-premium-mod": "notion",
    "evernote-premium-mod": "evernote",
    "osmand-premium-mod": "osmand",
    "zedge-premium-mod": "zedge",
    "walli-4k-premium-mod": "walli",
    "sleep-as-android-premium-mod": "sleep-as-android",
}


# ============================================================
# Uptodown Source (Primary - works without Cloudflare)
# ============================================================
class UptodownSource:
    """
    Uptodown.com - Nguồn APK chính.
    Flow: slug URL → detail page (version, icon) → download page (token) → dw.uptodown.com/dwn/{token}
    """
    name = "uptodown"
    priority = 95

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _get(self, url: str, **kw) -> str | None:
        for attempt in range(3):
            try:
                async with self.session.get(url, headers=_headers(),
                                            timeout=aiohttp.ClientTimeout(total=20),
                                            allow_redirects=True, **kw) as r:
                    if r.status == 200:
                        return await r.text()
                    if r.status == 404:
                        return None
                    logger.debug(f"[uptodown] {url} -> {r.status}")
            except Exception as e:
                logger.debug(f"[uptodown] request error {url}: {e}")
                await asyncio.sleep(1)
        return None

    def _resolve_slug(self, app_name: str, app_slug: str) -> list[str]:
        """Generate possible Uptodown slugs for an app."""
        slugs = []

        # 1. Check override map
        if app_slug in SLUG_OVERRIDES:
            slugs.append(SLUG_OVERRIDES[app_slug])

        # 2. Auto-generate from name
        auto = _to_uptodown_slug(app_name)
        if auto and auto not in slugs:
            slugs.append(auto)

        # 3. Try first word only (brand name)
        words = app_name.split()
        brand = words[0].lower() if words else ""
        if brand and brand not in slugs and len(brand) > 2:
            slugs.append(brand)

        return slugs

    async def search(self, app_name: str, app_slug: str = "",
                     keywords: list = None) -> dict | None:
        """
        Tìm app trên Uptodown bằng direct slug URL.
        Thử nhiều slug variants cho đến khi tìm thấy.
        """
        slugs = self._resolve_slug(app_name, app_slug)

        for slug in slugs:
            url = f"https://{slug}.en.uptodown.com/android"
            html = await self._get(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Verify it's a real app page (has version info)
            ver_el = soup.select_one("span.version")
            if not ver_el:
                continue

            result = {
                "name": app_name,
                "slug": app_slug or slug,
                "version": ver_el.get_text(strip=True),
                "size": "",
                "download_url": "",  # filled by _get_download_url
                "icon_url": "",
                "source": self.name,
                "detail_url": url,
                "uptodown_slug": slug,
                "package_name": "",
            }

            # Icon
            icon = soup.select_one("img[alt], figure img, .icon img")
            for img in soup.select("img"):
                src = img.get("src", "")
                if "icon" in src.lower() or "utdstc.com/icon" in src:
                    result["icon_url"] = src
                    break

            # Package name from page
            pkg_el = soup.select_one("[data-package], .package-name")
            if pkg_el:
                result["package_name"] = pkg_el.get("data-package", pkg_el.get_text(strip=True))

            # Size
            for dt in soup.select("dt, th, .detail-title"):
                txt = dt.get_text(strip=True).lower()
                if "size" in txt:
                    dd = dt.find_next_sibling("dd") or dt.find_next_sibling("td")
                    if dd:
                        result["size"] = dd.get_text(strip=True)
                        break

            # Get download URL
            dl_url = await self._get_download_url(slug)
            if dl_url:
                result["download_url"] = dl_url
                logger.info(f"[uptodown] Found: {app_name} v{result['version']} (slug={slug})")
                return result

        return None

    async def _get_download_url(self, slug: str) -> str | None:
        """Parse download page to extract token-based URL."""
        dl_page = f"https://{slug}.en.uptodown.com/android/download"
        html = await self._get(dl_page)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Find button with data-url token
        btn = soup.select_one("button.download[data-url]")
        if not btn:
            # Try other selectors
            btn = soup.select_one("[data-url]")
            if btn and btn.get("data-url") in ("apps", "games", ""):
                btn = None

        if btn:
            token = btn.get("data-url", "")
            if token and len(token) > 20:
                return f"https://dw.uptodown.com/dwn/{token}"

        # Fallback: look for direct links
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if "dw.uptodown" in href or href.endswith(".apk"):
                return href

        return None

    async def download(self, download_url: str, dest_path: str) -> bool:
        """Download APK file from the token URL."""
        try:
            async with self.session.get(
                download_url,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=600),
                allow_redirects=True,
            ) as r:
                if r.status != 200:
                    logger.error(f"[uptodown] Download failed: {r.status}")
                    return False

                content_length = int(r.headers.get("Content-Length", 0))
                logger.info(f"[uptodown] Downloading {content_length / 1024 / 1024:.1f}MB")

                async with aiofiles.open(dest_path, "wb") as f:
                    downloaded = 0
                    async for chunk in r.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)

                # Verify file
                if os.path.exists(dest_path):
                    size = os.path.getsize(dest_path)
                    if size > 10000:
                        # Quick check: APK = ZIP (starts with PK)
                        with open(dest_path, "rb") as f:
                            magic = f.read(2)
                        if magic == b"PK":
                            return True
                        else:
                            logger.warning(f"[uptodown] File is not APK (magic: {magic})")
                            os.remove(dest_path)
                return False
        except Exception as e:
            logger.error(f"[uptodown] Download error: {e}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False


# ============================================================
# Google Play Metadata (for package name + metadata discovery)
# ============================================================
class GooglePlaySource:
    """
    Google Play Store - Chỉ lấy metadata (package name, icon, version).
    Không tải APK (Play Store không cho download trực tiếp).
    """
    name = "google_play"
    priority = 50

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self._scraper = None

    def _get_scraper(self):
        if self._scraper is None:
            try:
                from google_play_scraper import app as gp_app, search as gp_search
                self._scraper = {"app": gp_app, "search": gp_search}
            except ImportError:
                logger.warning("google-play-scraper not installed")
                self._scraper = {}
        return self._scraper

    async def search(self, app_name: str, app_slug: str = "",
                     keywords: list = None) -> dict | None:
        """Search Google Play for metadata only."""
        scraper = self._get_scraper()
        if not scraper:
            return None

        try:
            # Run in executor to not block event loop
            loop = asyncio.get_event_loop()

            # Clean name for search
            clean_name = re.sub(
                r'\s+(Mod|Pro|Premium|Gold|Diamond|VIP|Plus|Full|Lite|Hack|Patched)\b',
                '', app_name, flags=re.IGNORECASE
            ).strip()

            results = await loop.run_in_executor(
                None, lambda: scraper["search"](clean_name, lang="vi", country="vn", n_hits=3)
            )

            if not results:
                return None

            # Get first result details
            best = results[0]
            pkg = best.get("appId", "")

            detail = await loop.run_in_executor(
                None, lambda: scraper["app"](pkg, lang="vi", country="vn")
            )

            return {
                "name": app_name,
                "slug": app_slug,
                "package_name": pkg,
                "version": detail.get("version", ""),
                "icon_url": detail.get("icon", ""),
                "description": detail.get("description", ""),
                "description_summary": detail.get("summary", ""),
                "developer": detail.get("developer", ""),
                "rating": detail.get("score", ""),
                "installs": detail.get("installs", ""),
                "source": self.name,
                "download_url": "",  # No direct download from Play Store
            }
        except Exception as e:
            logger.debug(f"[google_play] Error for '{app_name}': {e}")
            return None


# ============================================================
# Source Manager
# ============================================================
class SourceManager:
    """Quản lý nguồn APK, ưu tiên Uptodown (tải), Google Play (metadata)."""

    def __init__(self, session: aiohttp.ClientSession, max_concurrent: int = 3):
        self.uptodown = UptodownSource(session)
        self.google_play = GooglePlaySource(session)
        self.session = session
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.temp_dir = Path("/root/VesTool/tmp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def find_best(self, app_name: str, keywords: list = None,
                        app_slug: str = "") -> dict | None:
        """
        Tìm APK: Uptodown (download) + Google Play (metadata).
        Merge kết quả để có cả download URL + metadata.
        """
        async with self.semaphore:
            # Search Uptodown (primary - has download)
            uptodown_result = await self.uptodown.search(app_name, app_slug, keywords)

            # Search Google Play (metadata only)
            gp_result = None
            try:
                gp_result = await self.google_play.search(app_name, app_slug, keywords)
            except Exception as e:
                logger.debug(f"Google Play search error: {e}")

            # Merge results
            if uptodown_result:
                result = uptodown_result
                # Enrich with Google Play metadata if available
                if gp_result:
                    if not result.get("package_name"):
                        result["package_name"] = gp_result.get("package_name", "")
                    if not result.get("icon_url"):
                        result["icon_url"] = gp_result.get("icon_url", "")
                    result["gp_description"] = gp_result.get("description", "")
                    result["developer"] = gp_result.get("developer", "")
                    result["rating"] = gp_result.get("rating", "")
                    result["installs"] = gp_result.get("installs", "")
                return result

            elif gp_result:
                # Only metadata, no download URL
                logger.info(f"[sources] Only Google Play metadata for '{app_name}' (no APK)")
                return gp_result

            logger.warning(f"[sources] No source found for: {app_name}")
            return None

    async def download_apk(self, app_info: dict, dest_dir: str = None) -> str | None:
        """Download APK về local. Trả về path hoặc None."""
        if not dest_dir:
            dest_dir = str(self.temp_dir)

        url = app_info.get("download_url", "")
        if not url:
            return None

        slug = app_info.get("slug", app_info.get("name", "unknown").lower().replace(" ", "-"))
        slug = re.sub(r'[^a-z0-9_-]', '', slug)
        filename = f"{slug}.apk"
        dest_path = os.path.join(dest_dir, filename)

        success = await self.uptodown.download(url, dest_path)

        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000:
            # Calculate MD5
            md5 = hashlib.md5()
            with open(dest_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            app_info["md5"] = md5.hexdigest()
            app_info["file_size"] = os.path.getsize(dest_path)
            logger.info(f"[sources] Downloaded: {dest_path} "
                        f"({app_info['file_size'] / 1024 / 1024:.1f}MB, md5={app_info['md5'][:8]})")
            return dest_path

        logger.error(f"[sources] Download failed for {slug}")
        return None
