#!/usr/bin/env python3
"""
bot1.py - VesTool APK Crawler
Tìm, tải, lưu metadata, upload Telegram + R2 cho 499 apps.
Chỉ tải bản mới nhất. Không kéo phiên bản cũ.

Chạy:
    python3 bots/bot1.py                    # crawl tất cả
    python3 bots/bot1.py --limit 10         # chỉ crawl 10 app đầu
    python3 bots/bot1.py --category games   # chỉ category games
    python3 bots/bot1.py --dry-run          # test không tải thật
    python3 bots/bot1.py --skip-upload      # tải APK nhưng không upload
    python3 bots/bot1.py --app "Spotify"    # crawl 1 app cụ thể
"""

import os
import sys
import json
import time
import signal
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Thêm root vào path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import aiohttp

from config import TELEGRAM, R2, CRAWLER, CATEGORIES

# Import modules
from bots.apk_sources import SourceManager
from bots.r2_uploader import StorageManager
from bots.metadata_fetcher import MetadataFetcher

# ============================================================
# Logging
# ============================================================
LOG_FILE = ROOT / "bot1.log"

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    # Giảm noise từ thư viện
    for lib in ("urllib3", "httpcore", "httpx", "telethon", "boto3", "botocore"):
        logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger("bot1")

# ============================================================
# Paths
# ============================================================
APPS_LIST = ROOT / "data" / "apps_list.json"
APPS_DB = ROOT / "data" / "apps.json"          # trạng thái đã crawl
TEMP_DIR = Path(CRAWLER.get("temp_dir", "/root/VesTool/tmp"))
ICONS_DIR = ROOT / "data" / "icons"

for d in (TEMP_DIR, ICONS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# Trạng thái đã crawl
# ============================================================
def load_db() -> dict:
    """Load database trạng thái các app đã crawl."""
    if APPS_DB.exists():
        try:
            data = json.loads(APPS_DB.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "apps" in data:
                return data
            if isinstance(data, list):
                return {"apps": data, "last_updated": ""}
            if isinstance(data, dict):
                return {"apps": [], "last_updated": "", **data}
        except Exception:
            pass
    return {"apps": [], "last_updated": ""}


def save_db(db: dict):
    """Lưu database trạng thái."""
    db["last_updated"] = datetime.now(timezone.utc).isoformat()
    APPS_DB.write_text(
        json.dumps(db, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_in_db(db: dict, slug: str) -> dict | None:
    """Tìm app trong database theo slug."""
    for app in db.get("apps", []):
        if app.get("slug") == slug:
            return app
    return None


# ============================================================
# Load danh sách apps
# ============================================================
def load_apps_list() -> list:
    """Load danh sách 499 apps từ apps_list.json."""
    data = json.loads(APPS_LIST.read_text(encoding="utf-8"))
    return data.get("apps", data) if isinstance(data, dict) else data


# ============================================================
# Smart keyword extraction
# ============================================================
_STRIP_WORDS = {
    "mod", "pro", "premium", "gold", "diamond", "vip", "plus",
    "full", "unlock", "unlocked", "paid", "patched", "lite",
    "cracked", "hack", "hacked", "modded", "apk",
}

def _smart_keywords(app_name: str, package_name: str = "") -> list:
    """
    Tạo keywords tìm kiếm thông minh từ tên app mod.
    'Spotify Premium Mod' -> ['Spotify', 'Spotify Premium']
    'YouTube ReVanced' -> ['YouTube', 'YouTube ReVanced']
    'KineMaster Diamond Mod' -> ['KineMaster', 'KineMaster Diamond']
    """
    words = app_name.split()
    # Lọc bỏ suffix mod
    clean = [w for w in words if w.lower() not in _STRIP_WORDS]
    if not clean:
        clean = words[:1]

    result = []
    # Tên sạch (không có mod/pro/premium)
    clean_name = " ".join(clean)
    if clean_name != app_name:
        result.append(clean_name)

    # Từ đầu tiên (brand)
    if clean[0] not in result:
        result.append(clean[0])

    # Tên gốc
    result.append(app_name)

    # Package name nếu có
    if package_name:
        result.append(package_name)

    return result


# ============================================================
# Main Crawler
# ============================================================
class VesToolCrawler:
    """Crawler chính - tìm, tải, fetch metadata, upload."""

    def __init__(self, args):
        self.args = args
        self.db = load_db()
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }
        self._stop = False

    async def run(self):
        """Entry point."""
        apps = self._filter_apps(load_apps_list())
        self.stats["total"] = len(apps)
        logger.info(f"=== VesTool Crawler bắt đầu: {len(apps)} apps ===")

        timeout = aiohttp.ClientTimeout(total=CRAWLER.get("timeout", 300))
        connector = aiohttp.TCPConnector(limit=5, force_close=True)

        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            # Khởi tạo modules
            self.sources = SourceManager(session)
            self.metadata = MetadataFetcher(session)
            self.storage = None

            if not self.args.dry_run and not self.args.skip_upload:
                self.storage = StorageManager(TELEGRAM, R2)
                try:
                    await self.storage.start()
                    logger.info("Storage (Telegram + R2) connected")
                except Exception as e:
                    logger.warning(f"Storage init failed: {e}. Will skip upload.")
                    self.storage = None

            try:
                for i, app in enumerate(apps):
                    if self._stop:
                        logger.info("Nhận tín hiệu dừng, đang thoát...")
                        break
                    await self._process_app(i + 1, len(apps), app)

                    # Lưu DB mỗi 5 app
                    if (i + 1) % 5 == 0:
                        save_db(self.db)

            finally:
                # Cleanup
                if self.storage:
                    try:
                        await self.storage.stop()
                    except Exception:
                        pass
                save_db(self.db)

        self._print_summary()

    async def _process_app(self, idx: int, total: int, app: dict):
        """Xử lý 1 app: tìm -> tải -> metadata -> upload."""
        slug = app.get("slug", "")
        name = app.get("name", slug)
        category = app.get("category", "unknown")
        cat_name = CATEGORIES.get(category, category)

        logger.info(f"[{idx}/{total}] {name} ({cat_name})")

        # Kiểm tra đã crawl chưa
        existing = find_in_db(self.db, slug)
        if existing and existing.get("status") == "done":
            # Check if app exists on R2 before skipping
            if self.storage and not self.storage.check_app_exists(slug):
                logger.info(f"  -> App {slug} không tồn tại trên R2, xử lý lại.")
            else:
                logger.info(f"  -> Đã có, skip.")
                self.stats["skipped"] += 1
                return

        try:
            # ---- Bước 1: Tìm APK từ các nguồn ----
            keywords = app.get("keywords", [])
            if not keywords:
                keywords = _smart_keywords(name, app.get("package_name", ""))

            search_result = await self.sources.find_best(
                name, keywords=keywords, app_slug=slug
            )

            if not search_result:
                logger.warning(f"  -> Không tìm thấy APK từ nguồn nào")
                self._record_fail(app, "no_source_found")
                return

            source_name = search_result.get("source", "unknown")
            version = search_result.get("version", "")
            download_url = search_result.get("download_url", "")
            package = search_result.get("package_name", app.get("package_name", ""))

            logger.info(f"  -> Tìm thấy: {source_name} v{version}")

            if self.args.dry_run:
                logger.info(f"  -> [DRY-RUN] Bỏ qua tải & upload")
                self._record_success(app, search_result, dry_run=True)
                return

            # ---- Bước 2: Tải APK ----
            apk_path = await self.sources.download_apk(
                search_result, str(TEMP_DIR)
            )
            if not apk_path:
                logger.warning(f"  -> Tải APK thất bại")
                self._record_fail(app, "download_failed")
                return

            apk_size = os.path.getsize(apk_path)
            logger.info(f"  -> Đã tải: {apk_size / 1024 / 1024:.1f}MB")

            # ---- Bước 3: Fetch metadata ----
            meta = await self.metadata.fetch_all({
                "name": name,
                "slug": slug,
                "package_name": package,
                "category": category,
                **search_result,
            })

            icon_path = meta.get("icon_local", "")
            description_vi = meta.get("description_vi", "")
            subtitle = meta.get("subtitle", "")

            logger.info(f"  -> Metadata: icon={'có' if icon_path else 'không'}, "
                        f"desc={len(description_vi)} chars")

            # ---- Bước 4: Upload ----
            upload_result = {}
            if not self.args.skip_upload and self.storage:
                retry_attempts = 3
                for attempt in range(retry_attempts):
                    try:
                        # Upload APK
                        app_info_for_upload = {
                            "name": name,
                            "slug": slug,
                            "version": version,
                            "package_name": package,
                            "category": category,
                            "description": description_vi,
                        }
                        upload_result = await self.storage.upload_apk(
                            apk_path, app_info_for_upload
                        )
                        logger.info(f"  -> Upload APK: OK")

                        # Upload icon
                        if icon_path and os.path.exists(icon_path):
                            icon_result = await self.storage.upload_icon(
                                icon_path, app_info_for_upload
                            )
                            upload_result["icon"] = icon_result
                            logger.info(f"  -> Upload icon: OK")
                        break  # Exit retry loop if successful
                    except Exception as e:
                        logger.error(f"  -> Upload attempt {attempt + 1} failed: {e}")
                        if attempt == retry_attempts - 1:
                            upload_result["error"] = str(e)
                            logger.error("  -> All upload attempts failed.")
                            break
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff

            # ---- Bước 5: Ghi kết quả ----
            self._record_success(app, search_result, meta, upload_result)

            # Cleanup temp APK
            try:
                if os.path.exists(apk_path):
                    os.remove(apk_path)
            except Exception:
                pass

            # Rate limit
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"  -> Lỗi: {e}", exc_info=True)
            self._record_fail(app, str(e))

    def _record_success(self, app: dict, source: dict,
                        meta: dict = None, upload: dict = None,
                        dry_run: bool = False):
        """Ghi app đã crawl thành công vào DB."""
        slug = app.get("slug", "")
        entry = find_in_db(self.db, slug)
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "slug": slug,
            "name": app.get("name", ""),
            "category": app.get("category", ""),
            "package_name": source.get("package_name", app.get("package_name", "")),
            "version": source.get("version", ""),
            "source": source.get("source", ""),
            "download_url": source.get("download_url", ""),
            "status": "dry_run" if dry_run else "done",
            "crawled_at": now,
        }

        if meta:
            record["icon_url"] = meta.get("icon_url", "")
            record["description_vi"] = meta.get("description_vi", "")
            record["subtitle"] = meta.get("subtitle", "")
            record["developer"] = meta.get("developer", "")
            record["rating"] = meta.get("rating", "")
            record["installs"] = meta.get("installs", "")

        if upload:
            record["telegram_file_id"] = upload.get("telegram_file_id", "")
            record["telegram_msg_id"] = upload.get("telegram_msg_id", "")
            record["r2_url"] = upload.get("r2_url", "")
            record["r2_icon"] = upload.get("icon", {}).get("r2_url", "")

        if entry:
            # Update existing
            idx = self.db["apps"].index(entry)
            self.db["apps"][idx] = record
        else:
            self.db["apps"].append(record)

        self.stats["success"] += 1

    def _record_fail(self, app: dict, reason: str):
        """Ghi app crawl thất bại."""
        slug = app.get("slug", "")
        now = datetime.now(timezone.utc).isoformat()

        entry = find_in_db(self.db, slug)
        record = {
            "slug": slug,
            "name": app.get("name", ""),
            "category": app.get("category", ""),
            "status": "failed",
            "fail_reason": reason,
            "crawled_at": now,
        }

        if entry:
            idx = self.db["apps"].index(entry)
            self.db["apps"][idx] = record
        else:
            self.db["apps"].append(record)

        self.stats["failed"] += 1
        self.stats["errors"].append(f"{app.get('name', slug)}: {reason}")

    def _filter_apps(self, apps: list) -> list:
        """Lọc apps theo args (category, limit, app name)."""
        result = apps

        if self.args.category:
            result = [a for a in result if a.get("category") == self.args.category]
            logger.info(f"Lọc category '{self.args.category}': {len(result)} apps")

        if self.args.app:
            query = self.args.app.lower()
            result = [a for a in result
                      if query in a.get("name", "").lower()
                      or query in a.get("slug", "").lower()]
            logger.info(f"Tìm app '{self.args.app}': {len(result)} kết quả")

        if self.args.retry_failed:
            failed_slugs = set()
            db = load_db()
            for a in db.get("apps", []):
                if a.get("status") == "failed":
                    failed_slugs.add(a.get("slug"))
            result = [a for a in result if a.get("slug") in failed_slugs]
            logger.info(f"Retry failed: {len(result)} apps")

        if self.args.limit and self.args.limit > 0:
            result = result[: self.args.limit]
            logger.info(f"Giới hạn: {self.args.limit} apps")

        return result

    def _print_summary(self):
        """In tổng kết."""
        s = self.stats
        elapsed = "N/A"
        logger.info("=" * 60)
        logger.info(f"=== TỔNG KẾT ===")
        logger.info(f"  Tổng:       {s['total']}")
        logger.info(f"  Thành công: {s['success']}")
        logger.info(f"  Thất bại:   {s['failed']}")
        logger.info(f"  Bỏ qua:     {s['skipped']}")
        if s["errors"]:
            logger.info(f"  Lỗi chi tiết:")
            for err in s["errors"][:20]:
                logger.info(f"    - {err}")
        logger.info("=" * 60)

    def stop(self):
        """Graceful stop."""
        self._stop = True


# ============================================================
# CLI
# ============================================================
def parse_args():
    p = argparse.ArgumentParser(description="VesTool APK Crawler")
    p.add_argument("--limit", type=int, default=0,
                   help="Giới hạn số app crawl (0=tất cả)")
    p.add_argument("--category", type=str, default="",
                   choices=[""] + list(CATEGORIES.keys()),
                   help="Chỉ crawl category cụ thể")
    p.add_argument("--app", type=str, default="",
                   help="Tìm kiếm và crawl 1 app cụ thể")
    p.add_argument("--dry-run", action="store_true",
                   help="Chỉ tìm kiếm, không tải & upload")
    p.add_argument("--skip-upload", action="store_true",
                   help="Tải APK nhưng không upload Telegram/R2")
    p.add_argument("--retry-failed", action="store_true",
                   help="Chỉ retry các app đã failed")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Debug logging")
    return p.parse_args()


async def main():
    args = parse_args()
    setup_logging(args.verbose)

    crawler = VesToolCrawler(args)

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, crawler.stop)

    start = time.time()
    await crawler.run()
    elapsed = time.time() - start
    logger.info(f"Hoàn thành trong {elapsed:.0f}s ({elapsed/60:.1f} phút)")


if __name__ == "__main__":
    asyncio.run(main())
