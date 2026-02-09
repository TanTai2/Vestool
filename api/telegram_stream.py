"""
Telegram APK Streaming Server - Tối ưu cho VPS 1GB RAM

Kỹ thuật: Chunked Transfer - Telegram đẩy tới đâu, VPS stream về client tới đó.
Không load toàn bộ file vào RAM, phù hợp với file APK tới 2GB.

Chạy standalone: python telegram_stream.py
Hoặc import vào Flask app qua run_stream_server()

Yêu cầu env vars:
  - TG_API_ID: API ID từ my.telegram.org  
  - TG_API_HASH: API Hash từ my.telegram.org
  - TELEGRAM_BOT_TOKEN: Bot token từ BotFather
  - TELEGRAM_CHANNEL_ID: Channel ID chứa file APK

Usage:
  GET /stream/{message_id}?name=app.apk  - Tải file từ message ID
  GET /stream/link?url=...&name=app.apk  - Tải file từ telegram link
"""

import os
import re
import asyncio
import logging
from typing import Optional, Tuple

# Config - lấy từ environment variables
TG_API_ID = os.environ.get('TG_API_ID', '')
TG_API_HASH = os.environ.get('TG_API_HASH', '')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')

# Stream config - tối ưu cho VPS 1GB RAM
CHUNK_SIZE = 1024 * 1024  # 1MB per chunk - cân bằng giữa tốc độ và RAM
MAX_CONNECTIONS = 15  # Với 360Mbps upload, ~15 người tải song song
STREAM_PORT = int(os.environ.get('STREAM_PORT', '8088'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_telegram_link(link: str) -> Tuple[Optional[str], Optional[int]]:
    """Parse Telegram link to extract channel_id and message_id.
    
    Formats supported:
      - https://t.me/c/1234567890/123 (private channel)
      - https://t.me/channelname/123 (public channel)
    
    Returns: (channel_id, message_id) or (None, None)
    """
    # Private channel format: t.me/c/xxx/yyy
    match = re.search(r't\.me/c/(\d+)/(\d+)', link)
    if match:
        return f'-100{match.group(1)}', int(match.group(2))
    
    # Public channel format: t.me/channelname/yyy
    match = re.search(r't\.me/([^/]+)/(\d+)', link)
    if match:
        username = match.group(1)
        msg_id = int(match.group(2))
        return f'@{username}', msg_id
    
    return None, None


# ============ Telethon-based Streaming (Recommended) ============

try:
    from telethon import TelegramClient
    from telethon.tl.types import DocumentAttributeFilename
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    TelegramClient = None
    logger.warning("Telethon not installed. Run: pip install telethon")

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None
    logger.warning("aiohttp not installed. Run: pip install aiohttp")


class TelegramStreamer:
    """Stream files directly from Telegram without saving to disk.
    
    Sử dụng Telethon để stream chunks trực tiếp từ Telegram servers.
    RAM usage: ~1-2MB per download (chỉ buffer 1 chunk tại một thời điểm).
    """
    
    def __init__(self, api_id: str, api_hash: str, bot_token: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.client: Optional[TelegramClient] = None
        self._active_downloads = 0
        
    async def start(self):
        """Initialize and connect Telegram client."""
        if not TELETHON_AVAILABLE:
            raise RuntimeError("Telethon not installed")
        
        session_path = os.path.join(os.path.dirname(__file__), 'stream_bot_session')
        self.client = TelegramClient(session_path, self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("Telegram client connected")
        
    async def stop(self):
        """Disconnect client."""
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram client disconnected")
            
    async def get_message(self, channel_id: str, message_id: int):
        """Get message from channel by ID."""
        if not self.client:
            return None
        
        try:
            # Try different channel ID formats
            entity = None
            for cid in [channel_id, int(channel_id) if channel_id.lstrip('-').isdigit() else channel_id]:
                try:
                    entity = await self.client.get_entity(cid)
                    break
                except Exception:
                    continue
                    
            if not entity:
                logger.error(f"Cannot find channel: {channel_id}")
                return None
                
            msg = await self.client.get_messages(entity, ids=message_id)
            return msg
        except Exception as e:
            logger.error(f"Error getting message {message_id}: {e}")
            return None
    
    def get_file_name(self, message) -> str:
        """Extract filename from message document."""
        if not message or not message.document:
            return 'unknown.apk'
            
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name
        return f'file_{message.id}.apk'
    
    def get_file_size(self, message) -> int:
        """Get file size from message."""
        if message and message.document:
            return message.document.size
        return 0
    
    async def stream_file(self, message, chunk_size: int = CHUNK_SIZE):
        """Async generator that yields file chunks.
        
        Đây là core của kỹ thuật streaming:
        - Telegram đẩy tới đâu, yield về client tới đó
        - Chỉ giữ 1 chunk trong RAM tại một thời điểm
        - File 2GB chỉ tốn ~1MB RAM
        """
        if not message or not message.document:
            return
            
        self._active_downloads += 1
        try:
            async for chunk in self.client.iter_download(message.document, chunk_size=chunk_size):
                yield chunk
        finally:
            self._active_downloads -= 1
            
    @property
    def active_downloads(self) -> int:
        return self._active_downloads


# Global streamer instance
_streamer: Optional[TelegramStreamer] = None


async def get_streamer() -> TelegramStreamer:
    """Get or create global streamer instance."""
    global _streamer
    if _streamer is None:
        if not all([TG_API_ID, TG_API_HASH, TG_BOT_TOKEN]):
            raise RuntimeError(
                "Missing Telegram credentials. Set environment variables:\n"
                "  TG_API_ID, TG_API_HASH, TELEGRAM_BOT_TOKEN"
            )
        _streamer = TelegramStreamer(TG_API_ID, TG_API_HASH, TG_BOT_TOKEN)
        await _streamer.start()
    return _streamer


# ============ aiohttp Web Server ============

async def handle_stream_by_id(request: 'web.Request') -> 'web.StreamResponse':
    """Stream file by message ID.
    
    GET /stream/{message_id}?name=app.apk&channel=-100xxx
    """
    message_id = request.match_info.get('message_id')
    filename = request.query.get('name', 'app.apk')
    channel = request.query.get('channel', TG_CHANNEL_ID)
    
    if not message_id or not message_id.isdigit():
        return web.Response(text="Invalid message_id", status=400)
    
    try:
        streamer = await get_streamer()
        
        # Check concurrent download limit
        if streamer.active_downloads >= MAX_CONNECTIONS:
            return web.Response(
                text=f"Server busy ({streamer.active_downloads} active downloads). Try again later.",
                status=503
            )
        
        msg = await streamer.get_message(channel, int(message_id))
        
        if not msg or not msg.document:
            return web.Response(text="Message not found or has no file", status=404)
        
        # Get file info
        file_name = filename or streamer.get_file_name(msg)
        file_size = streamer.get_file_size(msg)
        
        # Prepare streaming response
        headers = {
            'Content-Disposition': f'attachment; filename="{file_name}"',
            'Content-Type': 'application/vnd.android.package-archive',
            'X-Content-Type-Options': 'nosniff',
        }
        if file_size:
            headers['Content-Length'] = str(file_size)
        
        response = web.StreamResponse(headers=headers)
        await response.prepare(request)
        
        # Stream chunks - đây là magic trick cho RAM thấp!
        bytes_sent = 0
        async for chunk in streamer.stream_file(msg):
            await response.write(chunk)
            bytes_sent += len(chunk)
        
        logger.info(f"Streamed {file_name}: {bytes_sent / 1024 / 1024:.1f} MB")
        return response
        
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return web.Response(text=f"Error: {str(e)}", status=500)


async def handle_stream_by_link(request: 'web.Request') -> 'web.StreamResponse':
    """Stream file by Telegram link.
    
    GET /stream/link?url=https://t.me/c/xxx/yyy&name=app.apk
    """
    link = request.query.get('url', '')
    filename = request.query.get('name', 'app.apk')
    
    if not link or 't.me' not in link:
        return web.Response(text="Invalid telegram link", status=400)
    
    channel_id, message_id = parse_telegram_link(link)
    if not channel_id or not message_id:
        return web.Response(text="Cannot parse telegram link", status=400)
    
    # Reuse stream_by_id logic
    request.match_info['message_id'] = str(message_id)
    request._rel_url = request._rel_url.with_query({
        'name': filename,
        'channel': channel_id
    })
    return await handle_stream_by_id(request)


async def handle_health(request: 'web.Request') -> 'web.Response':
    """Health check endpoint."""
    try:
        streamer = await get_streamer()
        return web.json_response({
            'status': 'ok',
            'active_downloads': streamer.active_downloads,
            'max_connections': MAX_CONNECTIONS,
        })
    except Exception as e:
        return web.json_response({
            'status': 'error',
            'error': str(e)
        }, status=500)


async def handle_status(request: 'web.Request') -> 'web.Response':
    """Server status page."""
    global _streamer
    
    html = f"""
    <html>
    <head><title>VesTool Stream Server</title></head>
    <body style="font-family: sans-serif; padding: 20px;">
        <h1>📦 VesTool APK Stream Server</h1>
        <p><b>Status:</b> {'🟢 Running' if _streamer else '🔴 Not initialized'}</p>
        <p><b>Active Downloads:</b> {_streamer.active_downloads if _streamer else 0} / {MAX_CONNECTIONS}</p>
        <p><b>Chunk Size:</b> {CHUNK_SIZE / 1024 / 1024:.0f} MB</p>
        <hr>
        <h3>API Endpoints:</h3>
        <ul>
            <li><code>GET /stream/{{message_id}}?name=app.apk&channel=-100xxx</code> - Stream by message ID</li>
            <li><code>GET /stream/link?url=https://t.me/c/xxx/yyy&name=app.apk</code> - Stream by link</li>
            <li><code>GET /health</code> - Health check</li>
        </ul>
        <h3>Ưu điểm:</h3>
        <ul>
            <li>✅ RAM không bao giờ tràn - chỉ buffer {CHUNK_SIZE / 1024 / 1024:.0f}MB/chunk</li>
            <li>✅ Hỗ trợ file APK tới 2GB</li>
            <li>✅ {MAX_CONNECTIONS} người tải đồng thời</li>
            <li>✅ Direct download - không nhảy app</li>
        </ul>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')


def create_app() -> 'web.Application':
    """Create aiohttp application."""
    if not AIOHTTP_AVAILABLE:
        raise RuntimeError("aiohttp not installed. Run: pip install aiohttp")
    
    app = web.Application()
    
    # Routes
    app.router.add_get('/', handle_status)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/stream/link', handle_stream_by_link)
    app.router.add_get('/stream/{message_id}', handle_stream_by_id)
    
    return app


async def on_startup(app):
    """Initialize streamer on app startup."""
    try:
        await get_streamer()
        logger.info("Streamer initialized on startup")
    except Exception as e:
        logger.warning(f"Streamer init skipped: {e}")


async def on_cleanup(app):
    """Cleanup streamer on shutdown."""
    global _streamer
    if _streamer:
        await _streamer.stop()
        _streamer = None


def run_stream_server(port: int = STREAM_PORT):
    """Run standalone streaming server.
    
    Chạy server này riêng biệt, không ảnh hưởng Flask API hiện có.
    """
    if not AIOHTTP_AVAILABLE or not TELETHON_AVAILABLE:
        print("ERROR: Missing dependencies. Run:")
        print("  pip install aiohttp telethon")
        return
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  VesTool Telegram APK Streaming Server                           ║
║  Optimized for VPS 1GB RAM                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Port: {port:<5}                                                  ║
║  Chunk Size: {CHUNK_SIZE / 1024 / 1024:.0f} MB                                                 ║
║  Max Connections: {MAX_CONNECTIONS}                                             ║
╠══════════════════════════════════════════════════════════════════╣
║  Endpoints:                                                      ║
║    /stream/{{message_id}}   - Stream by message ID                ║
║    /stream/link?url=...    - Stream by Telegram link             ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    app = create_app()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    web.run_app(app, port=port, print=lambda x: logger.info(x))


# ============ Flask Integration ============

def get_flask_blueprint():
    """Create Flask blueprint for streaming endpoints.
    
    Tích hợp vào Flask app hiện có:
    
        from telegram_stream import get_flask_blueprint
        stream_bp = get_flask_blueprint()
        app.register_blueprint(stream_bp, url_prefix='/stream')
    """
    try:
        from flask import Blueprint, Response, request as flask_request, jsonify
    except ImportError:
        return None
    
    bp = Blueprint('telegram_stream', __name__)
    
    # We need to run async code in sync Flask context
    import asyncio
    
    def run_async(coro):
        """Run async function in sync context."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    
    @bp.route('/health')
    def health():
        try:
            streamer = run_async(get_streamer())
            return jsonify({
                'status': 'ok',
                'active_downloads': streamer.active_downloads,
            })
        except Exception as e:
            return jsonify({'status': 'error', 'error': str(e)}), 500
    
    @bp.route('/<int:message_id>')
    def stream_by_id(message_id):
        filename = flask_request.args.get('name', 'app.apk')
        channel = flask_request.args.get('channel', TG_CHANNEL_ID)
        
        try:
            streamer = run_async(get_streamer())
            msg = run_async(streamer.get_message(channel, message_id))
            
            if not msg or not msg.document:
                return "Message not found", 404
            
            file_name = filename or streamer.get_file_name(msg)
            file_size = streamer.get_file_size(msg)
            
            # Sync generator wrapper
            def generate():
                async def async_gen():
                    async for chunk in streamer.stream_file(msg):
                        yield chunk
                
                loop = asyncio.new_event_loop()
                gen = async_gen()
                try:
                    while True:
                        chunk = loop.run_until_complete(gen.__anext__())
                        yield chunk
                except StopAsyncIteration:
                    pass
                finally:
                    loop.close()
            
            headers = {
                'Content-Disposition': f'attachment; filename="{file_name}"',
                'Content-Type': 'application/vnd.android.package-archive',
            }
            if file_size:
                headers['Content-Length'] = str(file_size)
            
            return Response(
                generate(),
                headers=headers,
                mimetype='application/vnd.android.package-archive'
            )
            
        except Exception as e:
            return str(e), 500
    
    @bp.route('/link')
    def stream_by_link():
        link = flask_request.args.get('url', '')
        filename = flask_request.args.get('name', 'app.apk')
        
        if not link or 't.me' not in link:
            return "Invalid link", 400
        
        channel_id, message_id = parse_telegram_link(link)
        if not channel_id or not message_id:
            return "Cannot parse link", 400
        
        # Redirect to stream_by_id with query params
        from flask import redirect, url_for
        return redirect(url_for('.stream_by_id', message_id=message_id, name=filename, channel=channel_id))
    
    return bp


if __name__ == '__main__':
    run_stream_server()
