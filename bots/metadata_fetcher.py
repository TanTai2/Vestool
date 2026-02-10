"""
Metadata Fetcher - Kéo icon, mô tả (tiếng Việt), phụ đề từ Google Play & các nguồn
"""
import os
import re
import json
import logging
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup

logger = logging.getLogger("metadata_fetcher")

ICON_DIR = Path("/root/VesTool/data/icons")
ICON_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class MetadataFetcher:
    """Lấy metadata từ Google Play Store (tiếng Việt) và các nguồn khác"""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _get(self, url: str, headers: dict = None) -> str | None:
        default_headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if headers:
            default_headers.update(headers)

        for attempt in range(3):
            try:
                async with self.session.get(url, headers=default_headers, timeout=aiohttp.ClientTimeout(total=20), ssl=False) as r:
                    if r.status == 200:
                        return await r.text()
                    elif r.status == 429:
                        await asyncio.sleep(3 * (attempt + 1))
                    else:
                        return None
            except Exception as e:
                logger.debug(f"GET error {url}: {e}")
                await asyncio.sleep(1)
        return None

    async def _download_file(self, url: str, dest: str) -> bool:
        """Download file (icon, screenshot, etc.)"""
        try:
            async with self.session.get(url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as r:
                if r.status != 200:
                    return False
                async with aiofiles.open(dest, "wb") as f:
                    async for chunk in r.content.iter_chunked(8192):
                        await f.write(chunk)
                return os.path.getsize(dest) > 100
        except Exception as e:
            logger.debug(f"Download file error: {e}")
            return False

    # ====================================================================
    # Google Play Store (tiếng Việt)
    # ====================================================================
    async def fetch_google_play(self, package_name: str = "", app_name: str = "") -> dict:
        """
        Lấy metadata từ Google Play Store bằng tiếng Việt
        """
        result = {
            "description_vi": "",
            "short_description_vi": "",
            "icon_url": "",
            "developer": "",
            "rating": "",
            "installs": "",
            "category_play": "",
        }

        # Thử search bằng tên app nếu không có package_name
        if package_name:
            url = f"https://play.google.com/store/apps/details?id={package_name}&hl=vi&gl=VN"
        else:
            # Search Google Play
            search_url = f"https://play.google.com/store/search?q={quote(app_name)}&c=apps&hl=vi&gl=VN"
            search_html = await self._get(search_url)
            if not search_html:
                return result

            # Tìm package name từ kết quả search
            pkg_match = re.search(r'details\?id=([a-zA-Z0-9_.]+)', search_html)
            if not pkg_match:
                return result
            package_name = pkg_match.group(1)
            url = f"https://play.google.com/store/apps/details?id={package_name}&hl=vi&gl=VN"

        html = await self._get(url)
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")

        # Description (tiếng Việt)
        desc_el = soup.select_one('[data-g-id="description"], div[itemprop="description"]')
        if desc_el:
            result["description_vi"] = desc_el.get_text(separator="\n", strip=True)

        # Short description / Subtitle
        subtitle_el = soup.select_one('div.W4P4ne, meta[name="description"]')
        if subtitle_el:
            if subtitle_el.name == "meta":
                result["short_description_vi"] = subtitle_el.get("content", "")
            else:
                result["short_description_vi"] = subtitle_el.get_text(strip=True)

        # Icon
        icon_els = soup.select('img[itemprop="image"], img[alt*="icon"], img.T75of')
        for img in icon_els:
            src = img.get("src", "") or img.get("data-src", "")
            if src and ("icon" in src.lower() or "googleusercontent" in src):
                result["icon_url"] = src.split("=")[0] + "=s512" if "=" in src else src
                break

        # Developer
        dev_el = soup.select_one('a[href*="developer"], div.Vbfug span')
        if dev_el:
            result["developer"] = dev_el.get_text(strip=True)

        # Rating
        rating_el = soup.select_one('div.TT9eCd, div.BHMmbe')
        if rating_el:
            result["rating"] = rating_el.get_text(strip=True)

        # Installs
        for el in soup.select("div.ClM7O"):
            text = el.get_text(strip=True)
            if "+" in text and any(c.isdigit() for c in text):
                result["installs"] = text
                break

        # Category
        cat_el = soup.select_one('a[itemprop="genre"], span.T32cc')
        if cat_el:
            result["category_play"] = cat_el.get_text(strip=True)

        return result

    # ====================================================================
    # Tạo mô tả tiếng Việt từ thông tin có sẵn
    # ====================================================================
    def generate_description_vi(self, app_info: dict) -> str:
        """
        Tạo mô tả xịn bằng tiếng Việt cho app nếu không lấy được từ Google Play
        """
        name = app_info.get("name", "")
        category = app_info.get("category_name", "")
        
        # Map category -> template mô tả
        templates = {
            "streaming": (
                f"🎬 **{name}** - Ứng dụng giải trí hàng đầu\n\n"
                f"Trải nghiệm xem phim, nghe nhạc không giới hạn với {name}. "
                f"Phiên bản mod được mở khóa toàn bộ tính năng Premium, loại bỏ quảng cáo "
                f"và hỗ trợ tải nội dung offline. Chất lượng video/âm thanh cao nhất, "
                f"không bị gián đoạn bởi quảng cáo.\n\n"
                f"✅ Mở khóa Premium\n✅ Không quảng cáo\n✅ Tải offline\n✅ Chất lượng cao nhất"
            ),
            "photo_video": (
                f"📸 **{name}** - Công cụ chỉnh sửa đỉnh cao\n\n"
                f"Biến mọi bức ảnh và video trở nên chuyên nghiệp với {name}. "
                f"Phiên bản mod mở khóa tất cả filter, hiệu ứng cao cấp, "
                f"gỡ watermark và export chất lượng cao.\n\n"
                f"✅ Mở khóa tất cả filter & hiệu ứng\n✅ Không watermark\n"
                f"✅ Export chất lượng cao\n✅ Tất cả tính năng Pro"
            ),
            "education": (
                f"📚 **{name}** - Học tập thông minh\n\n"
                f"Nâng cao kiến thức với {name}. Phiên bản mod mở khóa toàn bộ "
                f"khóa học Premium, tải nội dung offline và trải nghiệm học tập "
                f"không quảng cáo.\n\n"
                f"✅ Mở khóa Premium\n✅ Tải offline\n✅ Không quảng cáo\n✅ Học không giới hạn"
            ),
            "games": (
                f"🎮 **{name}** - Game đỉnh cao\n\n"
                f"Trải nghiệm {name} với đầy đủ tính năng được mở khóa. "
                f"Phiên bản mod cung cấp tiền không giới hạn, mở khóa tất cả "
                f"nhân vật và vật phẩm, chơi offline hoàn toàn.\n\n"
                f"✅ Mở khóa tất cả\n✅ Tiền/Kim cương không giới hạn\n"
                f"✅ Chơi offline\n✅ Không quảng cáo"
            ),
            "tools": (
                f"🛠️ **{name}** - Tiện ích mạnh mẽ\n\n"
                f"Tối ưu hóa thiết bị với {name}. Phiên bản mod mở khóa "
                f"toàn bộ tính năng Pro, không quảng cáo và các công cụ "
                f"nâng cao.\n\n"
                f"✅ Mở khóa Pro\n✅ Không quảng cáo\n✅ Tính năng nâng cao\n✅ Giao diện sạch"
            ),
            "office": (
                f"💼 **{name}** - Năng suất tối đa\n\n"
                f"Làm việc hiệu quả với {name}. Phiên bản mod mở khóa "
                f"Premium, cloud storage không giới hạn và tất cả template.\n\n"
                f"✅ Mở khóa Premium\n✅ Không quảng cáo\n✅ Template đầy đủ\n✅ Cloud storage"
            ),
            "travel": (
                f"🗺️ **{name}** - Du lịch thông minh\n\n"
                f"Khám phá thế giới với {name}. Phiên bản mod mở khóa "
                f"bản đồ offline, tính năng Premium và hướng dẫn chi tiết.\n\n"
                f"✅ Bản đồ offline\n✅ Mở khóa Premium\n✅ Không quảng cáo\n✅ Hướng dẫn chi tiết"
            ),
            "health": (
                f"💪 **{name}** - Sức khỏe toàn diện\n\n"
                f"Theo dõi sức khỏe và thể thao với {name}. Phiên bản mod "
                f"mở khóa Premium, kế hoạch tập luyện cá nhân hóa.\n\n"
                f"✅ Mở khóa Premium\n✅ Kế hoạch cá nhân hóa\n✅ Không quảng cáo\n✅ Theo dõi chi tiết"
            ),
            "mod_tools": (
                f"⚙️ **{name}** - Công cụ Mod chuyên nghiệp\n\n"
                f"Tùy biến thiết bị với {name}. Công cụ mạnh mẽ cho phép "
                f"mod, clone, quản lý ứng dụng nâng cao.\n\n"
                f"✅ Tính năng đầy đủ\n✅ Mở khóa Pro\n✅ Hỗ trợ root & non-root\n✅ Cập nhật thường xuyên"
            ),
        }

        cat_key = app_info.get("category", "tools")
        return templates.get(cat_key, templates["tools"])

    # ====================================================================
    # Download icon
    # ====================================================================
    async def download_icon(self, icon_url: str, slug: str) -> str | None:
        """Download icon và lưu local. Returns local path."""
        if not icon_url:
            return None

        ext = ".png"
        if ".jpg" in icon_url or ".jpeg" in icon_url:
            ext = ".jpg"
        elif ".webp" in icon_url:
            ext = ".webp"

        dest = str(ICON_DIR / f"{slug}{ext}")
        if os.path.exists(dest) and os.path.getsize(dest) > 100:
            return dest

        success = await self._download_file(icon_url, dest)
        if success:
            logger.info(f"Downloaded icon: {slug}")
            return dest
        return None

    # ====================================================================
    # Fetch tất cả metadata cho 1 app
    # ====================================================================
    async def fetch_all(self, app_info: dict) -> dict:
        """
        Lấy toàn bộ metadata cho 1 app:
        - description_vi (Google Play hoặc generate)
        - icon (download local)
        - thông tin bổ sung
        """
        name = app_info.get("name", "")
        slug = app_info.get("slug", "")
        package_name = app_info.get("package_name", "")

        metadata = {
            "description_vi": "",
            "short_description_vi": "",
            "icon_local": "",
            "icon_url": app_info.get("icon_url", ""),
            "developer": "",
            "rating": "",
            "installs": "",
        }

        # 1. Thử lấy từ Google Play (tiếng Việt)
        gp_data = await self.fetch_google_play(package_name=package_name, app_name=name)

        if gp_data.get("description_vi"):
            metadata["description_vi"] = gp_data["description_vi"]
            metadata["short_description_vi"] = gp_data.get("short_description_vi", "")
            metadata["developer"] = gp_data.get("developer", "")
            metadata["rating"] = gp_data.get("rating", "")
            metadata["installs"] = gp_data.get("installs", "")

            if gp_data.get("icon_url"):
                metadata["icon_url"] = gp_data["icon_url"]
        else:
            # Generate mô tả tiếng Việt từ template
            metadata["description_vi"] = self.generate_description_vi(app_info)

        # 2. Download icon
        icon_url = metadata.get("icon_url") or app_info.get("icon_url", "")
        if icon_url:
            icon_path = await self.download_icon(icon_url, slug)
            if icon_path:
                metadata["icon_local"] = icon_path

        logger.info(f"Metadata fetched: {name} (desc={'GP' if gp_data.get('description_vi') else 'generated'}, icon={'ok' if metadata['icon_local'] else 'missing'})")
        return metadata
