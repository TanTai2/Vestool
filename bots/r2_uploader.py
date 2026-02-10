"""
R2 Uploader - Upload APK files lên Cloudflare R2 + Telegram Channel
Flow: Local APK -> Telegram Channel (lưu trữ) -> Cloudflare R2 (CDN)
"""
import os
import logging
import asyncio
import hashlib
import mimetypes
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename

logger = logging.getLogger("r2_uploader")


class R2Uploader:
    """Upload APK lên Cloudflare R2 Storage"""

    def __init__(self, config: dict):
        self.account_id = config["account_id"]
        self.access_key = config["access_key_id"]
        self.secret_key = config["secret_access_key"]
        self.bucket = config["bucket_name"]
        self.endpoint = config["endpoint_url"]
        self.public_url = config.get("public_url", "")
        self._client = None

    @property
    def client(self):
        if not self._client:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=BotoConfig(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
                region_name="auto",
            )
        return self._client

    def ensure_bucket(self):
        """Tạo bucket nếu chưa tồn tại"""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            logger.info(f"R2 bucket '{self.bucket}' exists")
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
                logger.info(f"Created R2 bucket '{self.bucket}'")
            except Exception as e:
                logger.error(f"Cannot create bucket: {e}")

    def upload_file(self, local_path: str, r2_key: str, content_type: str = None) -> str:
        """
        Upload file lên R2
        Returns: public URL hoặc empty string nếu fail
        """
        if not os.path.exists(local_path):
            logger.error(f"File not found: {local_path}")
            return ""

        if not content_type:
            content_type, _ = mimetypes.guess_type(local_path)
            if not content_type:
                content_type = "application/vnd.android.package-archive"

        try:
            file_size = os.path.getsize(local_path)
            logger.info(f"Uploading {local_path} ({file_size / 1048576:.1f}MB) -> r2://{self.bucket}/{r2_key}")

            # Multipart upload cho file > 100MB
            if file_size > 100 * 1024 * 1024:
                from boto3.s3.transfer import TransferConfig
                transfer_config = TransferConfig(
                    multipart_threshold=50 * 1024 * 1024,
                    multipart_chunksize=50 * 1024 * 1024,
                    max_concurrency=4,
                )
                self.client.upload_file(
                    local_path,
                    self.bucket,
                    r2_key,
                    ExtraArgs={"ContentType": content_type},
                    Config=transfer_config,
                )
            else:
                with open(local_path, "rb") as f:
                    self.client.put_object(
                        Bucket=self.bucket,
                        Key=r2_key,
                        Body=f,
                        ContentType=content_type,
                    )

            url = f"{self.public_url}/{r2_key}" if self.public_url else f"{self.endpoint}/{self.bucket}/{r2_key}"
            logger.info(f"Uploaded: {url}")
            return url

        except Exception as e:
            logger.error(f"R2 upload error: {e}")
            return ""

    def upload_apk(self, local_path: str, slug: str, version: str = "") -> str:
        """Upload APK với key chuẩn: apks/{slug}/{slug}-v{version}.apk"""
        ver_suffix = f"-v{version}" if version else ""
        r2_key = f"apks/{slug}/{slug}{ver_suffix}.apk"
        return self.upload_file(local_path, r2_key, "application/vnd.android.package-archive")

    def upload_icon(self, local_path: str, slug: str) -> str:
        """Upload icon: icons/{slug}.png"""
        ext = Path(local_path).suffix or ".png"
        r2_key = f"icons/{slug}{ext}"
        ct = "image/png" if ext == ".png" else "image/jpeg"
        return self.upload_file(local_path, r2_key, ct)

    def delete_file(self, r2_key: str) -> bool:
        """Xóa file trên R2"""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=r2_key)
            return True
        except Exception as e:
            logger.error(f"R2 delete error: {e}")
            return False

    def list_files(self, prefix: str = "") -> list:
        """Liệt kê file trên R2"""
        try:
            resp = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=1000)
            return [obj["Key"] for obj in resp.get("Contents", [])]
        except Exception as e:
            logger.error(f"R2 list error: {e}")
            return []


class TelegramUploader:
    """Upload APK lên Telegram Channel (lưu trữ không giới hạn dung lượng)"""

    def __init__(self, config: dict):
        self.api_id = config["api_id"]
        self.api_hash = config["api_hash"]
        self.bot_token = config["bot_token"]
        self.channel_id = config["channel_id"]
        self.session_name = "bot1_session"
        self._client = None

    async def start(self):
        """Khởi tạo Telegram client"""
        self._client = TelegramClient(
            self.session_name,
            self.api_id,
            self.api_hash,
        )
        await self._client.start(bot_token=self.bot_token)
        logger.info("Telegram client started")
        return self._client

    async def stop(self):
        """Ngắt kết nối"""
        if self._client:
            await self._client.disconnect()
            logger.info("Telegram client stopped")

    async def upload_apk(self, local_path: str, app_info: dict) -> dict | None:
        """
        Upload APK lên Telegram channel
        Returns: {message_id, file_id, file_size} hoặc None
        """
        if not self._client:
            await self.start()

        if not os.path.exists(local_path):
            logger.error(f"File not found: {local_path}")
            return None

        file_size = os.path.getsize(local_path)
        name = app_info.get("name", "Unknown")
        version = app_info.get("version", "")
        slug = app_info.get("slug", "unknown")

        caption = (
            f"📱 **{name}**\n"
            f"📌 Version: {version}\n"
            f"📦 Size: {file_size / 1048576:.1f}MB\n"
            f"🏷️ #{slug.replace('-', '_')}\n"
            f"📂 Category: {app_info.get('category_name', '')}\n"
        )

        try:
            filename = f"{slug}-v{version}.apk" if version else f"{slug}.apk"

            msg = await self._client.send_file(
                self.channel_id,
                local_path,
                caption=caption,
                parse_mode="md",
                attributes=[DocumentAttributeFilename(filename)],
                force_document=True,
            )

            result = {
                "message_id": msg.id,
                "file_size": file_size,
            }

            # Lấy file_id từ message
            if msg.document:
                result["file_id"] = msg.document.id
                result["access_hash"] = msg.document.access_hash

            logger.info(f"Uploaded to Telegram: {name} (msg_id={msg.id})")
            return result

        except Exception as e:
            logger.error(f"Telegram upload error for {name}: {e}")
            return None

    async def upload_icon(self, icon_path: str, app_info: dict) -> dict | None:
        """Upload icon lên Telegram channel"""
        if not self._client:
            await self.start()

        if not os.path.exists(icon_path):
            return None

        try:
            name = app_info.get("name", "Unknown")
            caption = f"🎨 Icon: {name}"

            msg = await self._client.send_file(
                self.channel_id,
                icon_path,
                caption=caption,
            )

            return {"message_id": msg.id}
        except Exception as e:
            logger.error(f"Telegram icon upload error: {e}")
            return None


class StorageManager:
    """Quản lý cả R2 và Telegram storage"""

    def __init__(self, telegram_config: dict, r2_config: dict):
        self.tg = TelegramUploader(telegram_config)
        self.r2 = R2Uploader(r2_config)

    async def start(self):
        """Khởi tạo tất cả connections"""
        await self.tg.start()
        self.r2.ensure_bucket()

    async def stop(self):
        """Ngắt tất cả connections"""
        await self.tg.stop()

    async def upload_apk(self, local_path: str, app_info: dict) -> dict:
        """
        Upload APK lên cả Telegram và R2
        Returns: dict với telegram_msg_id, r2_url, etc.
        """
        result = {
            "telegram": None,
            "r2_url": "",
            "success": False,
        }

        slug = app_info.get("slug", "unknown")
        version = app_info.get("version", "")

        # 1. Upload lên Telegram trước (lưu trữ chính)
        tg_result = await self.tg.upload_apk(local_path, app_info)
        if tg_result:
            result["telegram"] = tg_result

        # 2. Upload lên R2 (CDN)
        r2_url = self.r2.upload_apk(local_path, slug, version)
        if r2_url:
            result["r2_url"] = r2_url

        result["success"] = bool(tg_result or r2_url)
        return result

    async def upload_icon(self, icon_path: str, app_info: dict) -> dict:
        """Upload icon lên cả Telegram và R2"""
        result = {
            "telegram": None,
            "r2_url": "",
        }

        slug = app_info.get("slug", "unknown")

        tg_result = await self.tg.upload_icon(icon_path, app_info)
        if tg_result:
            result["telegram"] = tg_result

        r2_url = self.r2.upload_icon(icon_path, slug)
        if r2_url:
            result["r2_url"] = r2_url

        return result
