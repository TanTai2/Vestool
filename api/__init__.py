from flask import Flask, jsonify, request, abort, send_file, Response
from werkzeug.utils import secure_filename
import requests
import re
try:
    from flask_socketio import SocketIO
    _SOCKETIO_AVAILABLE = True
except ImportError:
    _SOCKETIO_AVAILABLE = False
    class SocketIO:
        def __init__(self, app):
            self.app = app
        def emit(self, *args, **kwargs):
            return None
        def on(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
        def run(self, app, host="127.0.0.1", port=5000):
            app.run(host=host, port=port)
import os
from flask_cors import CORS

# Telegram Bot API config for direct download
TG_API_BASE = os.environ.get('TG_API_BASE', 'http://telegram-bot-api:8081')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')
from json import loads
import packagestore

from models import BaseModel
from models.device import Device
from models.package import Package
import logging
import appstore
import migrations
import sys
from models import PROJECT_ROOT
sys.path.insert(0, PROJECT_ROOT)
try:
    from vestool_apk.vestool_apk_core import tim_kiem_app_ngoai
except Exception:
    tim_kiem_app_ngoai = None

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)
CORS(app, supports_credentials=True)
# app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
ALLOWED_EXTENSIONS = ["apk"]
EV_PACKAGE_PUSHED = "update_push"
EV_APP_STARTED = "appStarted"
EV_APP_DEPLOYED = "appDeployed"
EV_APP_DEPLOYING = "appDeploying"
EV_APP_INSTALLED = "appInstalled"
# Notification events
EV_NOTIFY_DEPLOYING = "deploymentNotification"
migrations.run_migrations()


@app.route('/')
def hello_world():
    return 'Hello World!'


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def broadcast_creation(pkginfo):
    ev = 'package_creation' if pkginfo['is_new'] else 'package_updated'
    payload = {
        "type": "update_push",
        "package": pkginfo["package"],
        "version": pkginfo["version"],
        "ev": ev
    }
    socketio.emit(EV_PACKAGE_PUSHED, payload, broadcast=True)


def broadcast_deploying(dev_serial, pkginfo, version):
    ev = ""
    payload = {
        "device": dev_serial,
        "package": pkginfo["package"],
        "version": version
    }
    socketio.emit(EV_NOTIFY_DEPLOYING, payload, broadcast=True)


@app.route('/api/package', methods=['POST'])
def upload_package():
    if 'file' not in request.files:
        return abort(404)
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return abort(404)
    pkginfo = packagestore.put(file)
    # Broadcast to all connected sockets that we have an event
    # { type : "update_push" }
    broadcast_creation(pkginfo)
    return jsonify({
        "success": True,
        "pkginfo": pkginfo
    })


@app.route('/api/<package>/version', methods=['GET'])
def version_check(package):
    pkg = packagestore.has(package)
    if not pkg:
        return abort(404)
    return jsonify({'version': pkg.version})


@app.route('/api/<package>', methods=['GET'])
def get_package(package):
    pkg = packagestore.has(package)
    if not pkg:
        return abort(404)
    return send_file(pkg.file, mimetype='application/vnd.android.package-archive')


@app.route("/api/devices_packages", methods=['GET'])
def get_devpacks():
    devpacks = appstore.get_all_dev_packages()
    return jsonify(devpacks)


@app.route("/api/push_package/<name>", methods=['GET'])
def push_package(name):
    pkginfo = packagestore.get_pkginfo(name)
    if pkginfo is None:
        return abort(404)
    broadcast_creation(pkginfo)
    return jsonify({
        "success": True
    })


@app.route("/api/packages", methods=['GET'])
def get_packages():
    packs = packagestore.list_all()
    return jsonify(packs)


@app.route("/api/apps", methods=['GET'])
def get_apps():
    """Serve apps.json data to frontend.
    Endpoint: GET /api/apps
    Returns: List of all apps with their metadata.
    """
    import json
    apps_file = os.path.join(PROJECT_ROOT, 'data', 'apps.json')
    if not os.path.exists(apps_file):
        return jsonify([])
    try:
        with open(apps_file, 'r', encoding='utf-8') as f:
            apps = json.load(f)
        return jsonify(apps)
    except Exception as e:
        print(f'Error loading apps.json: {e}')
        return jsonify([])


@app.route("/api/versions/<app_id>", methods=['GET'])
def get_app_versions(app_id):
    """Get all versions of an app.
    Endpoint: GET /api/versions/{app_id}
    """
    import json
    safe_id = app_id.replace('.', '_')
    version_file = os.path.join(PROJECT_ROOT, 'data', 'versions', f'{safe_id}.json')
    if not os.path.exists(version_file):
        return jsonify([])
    try:
        with open(version_file, 'r', encoding='utf-8') as f:
            versions = json.load(f)
        return jsonify(versions)
    except Exception as e:
        print(f'Error loading versions for {app_id}: {e}')
        return jsonify([])


@app.route("/api/search_apps", methods=['GET'])
def search_apps():
    q = (request.args.get('q') or '').strip()
    limit = int(request.args.get('limit') or '12')
    if not q:
        return jsonify([])
    items = []
    if tim_kiem_app_ngoai:
        try:
            items = tim_kiem_app_ngoai(q, limit=limit)
        except Exception:
            items = []
    return jsonify(items)


def _parse_telegram_link(link):
    """Parse Telegram link to extract channel_id and message_id.
    Format: https://t.me/c/1234567890/123
    """
    match = re.search(r't\.me/c/(\d+)/(\d+)', link)
    if match:
        return f'-100{match.group(1)}', int(match.group(2))
    return None, None


def _tg_api_call(method, **kwargs):
    """Call Telegram Bot API."""
    if not TG_BOT_TOKEN:
        return None
    try:
        # Use form data (not json) for Telegram Bot API
        if 'json' in kwargs:
            kwargs['data'] = kwargs.pop('json')
        resp = requests.post(
            f'{TG_API_BASE}/bot{TG_BOT_TOKEN}/{method}',
            timeout=300,
            **kwargs
        )
        print(f'TG API {method}: status={resp.status_code}')
        if resp.ok:
            result = resp.json()
            if result.get('ok'):
                return result.get('result')
            else:
                print(f'TG API error: {result}')
        else:
            print(f'TG API HTTP error: {resp.status_code} {resp.text[:200]}')
    except Exception as e:
        print(f'Telegram API error: {e}')
        import traceback
        traceback.print_exc()
    return None


@app.route("/api/download", methods=['GET'])
def proxy_download():
    """Proxy download APK from Telegram through VPS.
    VPS acts as bridge: User -> VPS -> Telegram Bot API -> Stream back to User
    
    Có 2 cách tải:
    1. Qua local Bot API (forward message): /api/download?link=...
    2. Qua Stream Server (Telethon - khuyên dùng): redirect tới /stream/...
    
    Usage: /api/download?link=https://t.me/c/xxx/yyy&name=app.apk
    """
    link = request.args.get('link', '')
    filename = request.args.get('name', 'app.apk')
    use_stream = request.args.get('stream', '1')  # Mặc định dùng stream server
    
    if not link or 't.me' not in link:
        return abort(400, 'Invalid link')
    
    channel_id, message_id = _parse_telegram_link(link)
    if not channel_id or not message_id:
        return abort(400, 'Cannot parse telegram link')
    
    # Option 1: Redirect to streaming server (recommended - tiết kiệm RAM)
    if use_stream == '1':
        stream_url = os.environ.get('STREAM_SERVER_URL', 'http://localhost:8088')
        return jsonify({
            'stream_url': f'{stream_url}/stream/{message_id}?name={filename}&channel={channel_id}',
            'redirect': link,  # Fallback
        })
    
    # Option 2: Download qua local Bot API (legacy)
    if not TG_BOT_TOKEN:
        # Fallback: redirect to telegram link
        return jsonify({'redirect': link})
    
    try:
        # Step 1: Forward message to same channel to get file_id
        # (Bot must be admin of channel)
        forwarded = _tg_api_call('forwardMessage', json={
            'chat_id': channel_id,
            'from_chat_id': channel_id,
            'message_id': message_id,
        })
        
        if not forwarded:
            print(f'Failed to forward message {message_id} from {channel_id}')
            return jsonify({'redirect': link, 'error': 'Cannot access message'})
        
        new_msg_id = forwarded.get('message_id')
        document = forwarded.get('document')
        
        if not document:
            # Message doesn't contain a document
            if new_msg_id:
                _tg_api_call('deleteMessage', json={'chat_id': channel_id, 'message_id': new_msg_id})
            return jsonify({'redirect': link, 'error': 'Message has no document'})
        
        file_id = document.get('file_id')
        file_name = document.get('file_name', filename)
        file_size = document.get('file_size', 0)
        
        # Step 2: Get file path from Telegram
        file_info = _tg_api_call('getFile', json={'file_id': file_id})
        
        # Delete forwarded message immediately
        if new_msg_id:
            _tg_api_call('deleteMessage', json={'chat_id': channel_id, 'message_id': new_msg_id})
        
        if not file_info or not file_info.get('file_path'):
            return jsonify({'redirect': link, 'error': 'Cannot get file info'})
        
        file_path = file_info.get('file_path')
        
        # Step 3: Stream file from local Telegram Bot API server to user
        file_url = f'{TG_API_BASE}/file/bot{TG_BOT_TOKEN}/{file_path}'
        
        def generate():
            """Stream file in chunks to user."""
            try:
                with requests.get(file_url, stream=True, timeout=1800) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=65536):  # 64KB chunks
                        if chunk:
                            yield chunk
            except Exception as e:
                print(f'Stream error: {e}')
        
        # Return streaming response with proper headers
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
        print(f'Proxy download error: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'redirect': link, 'error': str(e)})


@app.route("/api/download/<app_id>/<version>", methods=['GET'])
def download_version(app_id, version):
    """Download specific version of an app.
    Looks up the version file from local storage or redirects to telegram.
    """
    import json
    
    # Try to find version info
    safe_id = app_id.replace('.', '_')
    version_file = os.path.join(PROJECT_ROOT, 'data', 'versions', f'{safe_id}.json')
    
    if not os.path.exists(version_file):
        return abort(404, 'App not found')
    
    try:
        with open(version_file, 'r') as f:
            versions = json.load(f)
        
        # Find matching version
        target = None
        for v in versions:
            if v.get('version_name') == version:
                target = v
                break
        
        if not target:
            return abort(404, 'Version not found')
        
        # Check if we have a local file
        local_file = target.get('local_file')
        if local_file and os.path.exists(local_file):
            return send_file(local_file, 
                           mimetype='application/vnd.android.package-archive',
                           as_attachment=True,
                           download_name=f'{app_id}_{version}.apk')
        
        # Check telegram link
        tg_link = target.get('telegram_link') or target.get('apk_url', '')
        if tg_link and 't.me' in tg_link:
            return jsonify({'redirect': tg_link})
        
        # Direct URL
        apk_url = target.get('apk_url')
        if apk_url:
            return jsonify({'redirect': apk_url})
        
        return abort(404, 'No download available')
        
    except Exception as e:
        print(f'Error reading version: {e}')
        return abort(500, str(e))


@app.route("/api/apk/<filename>", methods=['GET'])
def serve_apk(filename):
    """Serve APK file from local storage.
    Usage: /api/apk/com_spotify_music_abc123.apk
    """
    # Sanitize filename to prevent directory traversal
    safe_filename = os.path.basename(filename)
    if not safe_filename.endswith('.apk'):
        return abort(400, 'Invalid file type')
    
    # APK storage is at /root/VesTool/data/apks (parent of API dir)
    apk_dir = os.path.join(os.path.dirname(PROJECT_ROOT), 'data', 'apks')
    file_path = os.path.join(apk_dir, safe_filename)
    
    if not os.path.exists(file_path):
        return abort(404, 'APK not found')
    
    # Get file size for Content-Length header
    file_size = os.path.getsize(file_path)
    
    # Stream the file to avoid memory issues with large files
    def generate():
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)  # 64KB chunks
                if not chunk:
                    break
                yield chunk
    
    # Create filename for download
    download_name = safe_filename
    
    return Response(
        generate(),
        headers={
            'Content-Disposition': f'attachment; filename="{download_name}"',
            'Content-Length': str(file_size),
            'Content-Type': 'application/vnd.android.package-archive',
        },
        mimetype='application/vnd.android.package-archive'
    )


@app.route("/api/stream/<int:message_id>", methods=['GET'])
def stream_from_telegram(message_id):
    """Stream APK directly from Telegram message via Stream Server.
    
    Tối ưu cho VPS 1GB RAM - dùng chunked transfer.
    Usage: /api/stream/{message_id}?name=app.apk&channel=-100xxx
    
    Nếu stream server chạy riêng (port 8088), endpoint này sẽ proxy request.
    """
    filename = request.args.get('name', 'app.apk')
    channel = request.args.get('channel', TG_CHANNEL_ID)
    
    # Try to use internal stream server
    stream_base = os.environ.get('STREAM_SERVER_URL', 'http://localhost:8088')
    stream_url = f'{stream_base}/stream/{message_id}?name={filename}&channel={channel}'
    
    try:
        # Proxy streaming từ stream server
        def generate():
            with requests.get(stream_url, stream=True, timeout=1800) as r:
                if r.status_code != 200:
                    return
                for chunk in r.iter_content(chunk_size=1024*1024):  # 1MB chunks
                    if chunk:
                        yield chunk
        
        # Get file info from stream server
        resp = requests.head(stream_url, timeout=10)
        file_size = resp.headers.get('Content-Length', '')
        content_disp = resp.headers.get('Content-Disposition', f'attachment; filename="{filename}"')
        
        headers = {
            'Content-Disposition': content_disp,
            'Content-Type': 'application/vnd.android.package-archive',
        }
        if file_size:
            headers['Content-Length'] = file_size
        
        return Response(
            generate(),
            headers=headers,
            mimetype='application/vnd.android.package-archive'
        )
        
    except requests.exceptions.ConnectionError:
        # Stream server không chạy - trả về hướng dẫn
        return jsonify({
            'error': 'Stream server not running',
            'hint': 'Start stream server: docker-compose up stream',
            'alternative': f'/api/download?link=https://t.me/c/{channel.lstrip("-100")}/{message_id}&name={filename}&stream=0'
        }), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/stream/link", methods=['GET'])
def stream_from_link():
    """Stream APK from Telegram link.
    
    Usage: /api/stream/link?url=https://t.me/c/xxx/yyy&name=app.apk
    """
    link = request.args.get('url', '')
    filename = request.args.get('name', 'app.apk')
    
    if not link or 't.me' not in link:
        return jsonify({'error': 'Invalid telegram link'}), 400
    
    channel_id, message_id = _parse_telegram_link(link)
    if not channel_id or not message_id:
        return jsonify({'error': 'Cannot parse telegram link'}), 400
    
    # Redirect to stream endpoint
    from flask import redirect, url_for
    return redirect(url_for('stream_from_telegram', message_id=message_id, name=filename, channel=channel_id))


@socketio.on('message')
def handle_message(message):
    print('received message: ' + message)


@socketio.on("connected")
def handle_connection(c):
    print(c)


@socketio.on(EV_APP_STARTED)
def handle_robot_app_start(json):
    print('received json: ' + str(json))
    logging.warning(json)
    json = loads(json)
    pkg = json["package"]
    ver = json["version"]
    serial = json["serial"]
    imei = json.get("imei")
    wifi_mac = json.get("wifi_mac")
    ext_ip = json.get("ext_ip")
    lan_ip = json.get("lan_ip")
    dev = Device(serial=serial, imei=imei, wifi_mac=wifi_mac, ext_ip=ext_ip, lan_ip=lan_ip)
    appstore.notice_device_app(dev, pkg, ver)


@socketio.on(EV_APP_DEPLOYED)
def handle_robot_app_deployed(json):
    print('received json: ' + str(json))
    logging.warning(json)
    json = loads(json)
    pkg = json["package"]
    ver = json["version"]
    serial = json["serial"]
    imei = json.get("imei")
    wifi_mac = json.get("wifi_mac")
    ext_ip = json.get("ext_ip")
    lan_ip = json.get("lan_ip")
    dev = Device(serial=serial, imei=imei, wifi_mac=wifi_mac, ext_ip=ext_ip, lan_ip=lan_ip)
    appstore.notice_device_app(dev, pkg, ver)


@socketio.on(EV_APP_DEPLOYING)
def handle_app_deploying(json):
    json = loads(json)
    dev_serial = json['serial']
    pkgname = json['package']
    version = json['version']
    pkginfo = packagestore.get_pkginfo(pkgname)
    if pkginfo is None:
        return
    broadcast_deploying(dev_serial, pkginfo, version)


@socketio.on('json')
def handle_json(json):
    print('received json: ' + str(json))


# eventlet or gevent and gevent-websocket

if __name__ == '__main__':
    # dev = models.Device(serial="ser1", imei="im1", wifi_mac="wifi_mac", ext_ip="ext_ip")
    # dev2 = models.Device(serial="ser2", imei="im1", wifi_mac="wifi_mac", ext_ip="ext_ip")
    # dev2.save()
    # appstore.notice_device_app(dev, "com.netlyt.cruzrdb", "1.1.0")
    # appstore.notice_device_app(dev, "com.netlyt", "1.1.0")
    # appstore.notice_device_app(dev2, "com.netlyt", "1.1.0")
    # devpacks = appstore.get_all_dev_packages()
    socketio.run(app, host="0.0.0.0", port=5000)
