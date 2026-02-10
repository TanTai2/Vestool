import os
import time
import hashlib
import mimetypes
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.85 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Local Telegram Bot API server — no 50MB limit, supports up to 2GB
TG_API_BASE = os.environ.get('TG_API_BASE', 'http://localhost:8081')

# --------------- Helpers ---------------

ICON_CACHE_DIR = os.path.join('/tmp', 'vestool_icons')

def _get_fresh_uptodown_url(detail_url):
    """Visit Uptodown download page and get fresh APK download URL with session."""
    session = requests.Session()
    session.headers.update(HEADERS)
    download_page = detail_url.rstrip('/') + '/download'
    try:
        r = session.get(download_page, timeout=30)
        if r.status_code != 200:
            return None, None
        soup = BeautifulSoup(r.text, 'html.parser')
        btn = soup.select_one('button#detail-download-button[data-url]')
        if btn:
            data_url = btn.get('data-url')
            if data_url and not data_url.startswith(('http', '/')):
                apk_url = f'https://dw.uptodown.com/dwn/{data_url}'
                return apk_url, session
    except Exception:
        pass
    return None, None


def _download_icon_file(icon_url):
    """Fetch icon_url into a local temp file so Telegram can upload reliably."""
    if not icon_url or not icon_url.startswith('http'):
        return None
    try:
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
        resp = requests.get(icon_url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.content
        if len(data) < 512 or len(data) > 5 * 1024 * 1024:
            return None
        ctype = resp.headers.get('Content-Type', '').split(';')[0].strip()
        ext = mimetypes.guess_extension(ctype) if ctype else None
        if not ext:
            path_ext = os.path.splitext(urllib.parse.urlparse(icon_url).path)[1]
            ext = path_ext if path_ext else '.jpg'
        name = hashlib.md5(icon_url.encode()).hexdigest() + ext
        path = os.path.join(ICON_CACHE_DIR, name)
        with open(path, 'wb') as f:
            f.write(data)
        return path, (ctype or 'image/jpeg')
    except Exception as e:
        print(f'  Icon download failed: {e}')
        return None


def download_file(url, out_path, session=None):
    """Download a file from URL to local path."""
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
    try:
        r = session.get(url, stream=True, timeout=300, allow_redirects=True)
        if r.status_code == 404:
            print(f'  Download 404: {url[:80]}')
            return False
        r.raise_for_status()
        content_type = r.headers.get('Content-Type', '')
        content_length = int(r.headers.get('Content-Length', 0))
        if 'text/html' in content_type and content_length < 100000:
            print(f'  Download error: got HTML instead of APK for {url[:60]}')
            return False
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        size = os.path.getsize(out_path)
        if size < 10000:
            print(f'  Download too small ({size} bytes), removing: {out_path}')
            os.remove(out_path)
            return False
        print(f'  Downloaded: {out_path} ({size / 1024 / 1024:.1f} MB)')
        return out_path
    except Exception as e:
        print(f'  Download error: {e}')
        return False


# --------------- Telegram ---------------

def _tg_api(method, token, **kwargs):
    """Call Telegram Bot API (local server) with retry on rate limit."""
    for attempt in range(5):
        try:
            resp = requests.post(
                f'{TG_API_BASE}/bot{token}/{method}',
                timeout=1800, **kwargs
            )
            if resp.status_code == 429:
                retry_after = 5
                try:
                    retry_after = resp.json().get('parameters', {}).get('retry_after', 5)
                except Exception:
                    pass
                print(f'  Telegram rate limited, waiting {retry_after}s...')
                time.sleep(retry_after + 1)
                continue
            return resp
        except Exception as e:
            print(f'  Telegram API error (attempt {attempt+1}): {e}')
            if attempt < 4:
                time.sleep(3)
    return None


def _tg_message_link(chat_id, message_id):
    """Build a Telegram message link from chat_id and message_id."""
    cid = str(chat_id)
    # Private channel: -100xxxxx -> https://t.me/c/xxxxx/msg_id
    if cid.startswith('-100'):
        return f'https://t.me/c/{cid[4:]}/{message_id}'
    # Public channel @username handled separately
    return f'https://t.me/c/{cid.lstrip("-")}/{message_id}'


def send_document(file_path, caption='', reply_to=None, channel_id=None):
    """Upload a file as document to Telegram channel.
    Returns (message_link, message_id) or (None, None).
    """
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = channel_id or os.environ.get('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        print('  Telegram: missing BOT_TOKEN or CHANNEL_ID')
        return None, None

    data = {'chat_id': chat_id}
    if caption:
        data['caption'] = caption[:1024]
        data['parse_mode'] = 'HTML'
    if reply_to:
        data['reply_to_message_id'] = reply_to

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    print(f'  Telegram upload: {file_name} ({file_size / 1024 / 1024:.1f} MB)...')

    with open(file_path, 'rb') as f:
        resp = _tg_api('sendDocument', token,
                        data=data,
                        files={'document': (file_name, f, 'application/vnd.android.package-archive')})

    if not resp:
        return None, None

    if resp.ok:
        result = resp.json().get('result', {})
        msg_id = result.get('message_id')
        link = _tg_message_link(chat_id, msg_id)
        print(f'  Telegram upload OK: {link}')
        return link, msg_id
    else:
        print(f'  Telegram upload failed: {resp.status_code} {resp.text[:200]}')
        return None, None


def upload_apk_to_telegram(file_path, app_title='', app_id='', version='', channel_id=None, icon_url=''):
    """Upload an APK to Telegram channel via local API server.
    No size limit — local server supports up to 2GB.
    If icon_url provided, sends icon first then replies with APK.
    Returns (message_link, size_mb) or (None, 0).
    """
    file_size = os.path.getsize(file_path)
    size_mb = file_size / 1024 / 1024

    caption = f'📦 <b>{app_title}</b>\n'
    if version:
        caption += f'📋 Version: <code>{version}</code>\n'
    if app_id:
        caption += f'📱 <code>{app_id}</code>\n'
    caption += f'💾 {size_mb:.1f} MB'

    # Nếu có icon, gửi icon trước rồi reply APK
    reply_to = None
    if icon_url and icon_url.startswith('http'):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = channel_id or os.environ.get('TELEGRAM_CHANNEL_ID')
        if token and chat_id:
            icon_data = _download_icon_file(icon_url)
            if icon_data:
                icon_path, mime_type = icon_data
                with open(icon_path, 'rb') as f:
                    icon_resp = _tg_api('sendPhoto', token,
                        data={
                            'chat_id': chat_id,
                            'caption': f'🖼️ {app_title}',
                            'parse_mode': 'HTML'
                        },
                        files={'photo': (os.path.basename(icon_path), f, mime_type)})
                try:
                    os.remove(icon_path)
                except Exception:
                    pass
                if icon_resp and icon_resp.ok:
                    reply_to = icon_resp.json().get('result', {}).get('message_id')

    link, msg_id = send_document(file_path, caption=caption, channel_id=channel_id, reply_to=reply_to)
    return link, size_mb


def send_text(message, parse_mode=None):
    """Send a text message to Telegram channel. Auto-retry on rate limit (429)."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        return False
    data = {'chat_id': chat_id, 'text': message}
    if parse_mode:
        data['parse_mode'] = parse_mode
    resp = _tg_api('sendMessage', token, json=data)
    return resp and resp.ok


def send_app_card(app):
    """Send a rich app notification to Telegram channel 1 with download link."""
    title = app.get('title', 'Unknown')
    app_id = app.get('app_id', '')
    apk_public_url = app.get('apk_public_url', '')
    icon = app.get('icon', '')
    size_mb = app.get('apk_size_mb', 0)

    lines = [f'📦 <b>{title}</b>']
    if app_id:
        lines.append(f'📱 <code>{app_id}</code>')
    if size_mb:
        lines.append(f'💾 {size_mb:.1f} MB')
    if apk_public_url:
        lines.append(f'⬇️ <a href="{apk_public_url}">Tải APK</a>')
    else:
        lines.append('❌ Không có APK')

    msg = '\n'.join(lines)
    return send_text(msg, parse_mode='HTML')


def send_app_info_to_channel2(app):
    """Post app info (icon photo + details caption) to Channel 2.
    Channel 2 is used as an app showcase/info channel.
    Returns (message_link, message_id) or (None, None).
    """
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_INFO_CHANNEL_ID')
    if not token or not chat_id:
        print('  Channel 2: missing BOT_TOKEN or INFO_CHANNEL_ID, skipping')
        return None, None

    title = app.get('title', 'Unknown')
    app_id = app.get('app_id', '')
    icon = app.get('icon', '')
    desc = app.get('description', '')
    apk_url = app.get('apk_public_url') or app.get('apk_url') or ''
    size_mb = app.get('apk_size_mb', 0)

    # Build caption
    lines = [f'📱 <b>{title}</b>']
    if app_id:
        lines.append(f'🆔 <code>{app_id}</code>')
    if size_mb:
        lines.append(f'💾 {size_mb:.1f} MB')
    if desc:
        # Truncate description for Telegram caption (max 1024 chars total)
        max_desc = 600
        short_desc = desc[:max_desc] + ('...' if len(desc) > max_desc else '')
        lines.append(f'\n📝 {short_desc}')
    if apk_url:
        lines.append(f'\n⬇️ <a href="{apk_url}">Tải APK</a>')

    caption = '\n'.join(lines)
    if len(caption) > 1024:
        caption = caption[:1020] + '...'

    # If icon exists, send as photo with caption
    if icon and icon.startswith('http'):
        icon_data = _download_icon_file(icon)
        if icon_data:
            icon_path, mime_type = icon_data
            with open(icon_path, 'rb') as f:
                resp = _tg_api('sendPhoto', token,
                               data={
                                   'chat_id': chat_id,
                                   'caption': caption,
                                   'parse_mode': 'HTML',
                               },
                               files={'photo': (os.path.basename(icon_path), f, mime_type)})
            try:
                os.remove(icon_path)
            except Exception:
                pass
            if resp and resp.ok:
                result = resp.json().get('result', {})
                msg_id = result.get('message_id')
                link = _tg_message_link(chat_id, msg_id)
                print(f'  Channel 2 info posted: {link}')
                return link, msg_id
            else:
                err = resp.text[:200] if resp else 'No response'
                print(f'  Channel 2 photo failed: {err}, trying text only...')

    # Fallback: send as text message
    data = {
        'chat_id': chat_id,
        'text': caption,
        'parse_mode': 'HTML',
    }
    resp = _tg_api('sendMessage', token, data=data)
    if resp and resp.ok:
        result = resp.json().get('result', {})
        msg_id = result.get('message_id')
        link = _tg_message_link(chat_id, msg_id)
        print(f'  Channel 2 info posted (text): {link}')
        return link, msg_id
    return None, None


# --------------- Main flow ---------------

# Directory to store APKs for direct download
APK_STORAGE_DIR = os.environ.get('APK_STORAGE_DIR', '/root/VesTool/data/apks')


def download_and_upload(apk_url, app_id='unknown', tmp_dir='tmp', uptodown_detail=None, title='', version='', max_size_mb=0):
    """Download APK -> Upload to Telegram channel -> Return (message_link, size_mb, local_path).
    Also stores APK locally for direct download through web.
    Uses local API server — no file size limit (up to 2GB).
    If max_size_mb > 0, skip upload for files larger than that.
    """
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(APK_STORAGE_DIR, exist_ok=True)
    
    h = hashlib.md5(apk_url.encode()).hexdigest()[:8]
    safe_id = app_id.replace('.', '_') if app_id else 'unknown'
    name = f'{safe_id}_{h}.apk'
    path = os.path.join(tmp_dir, name)

    session = None
    actual_url = apk_url

    # If we have an Uptodown detail URL, get a fresh download link
    if uptodown_detail:
        fresh_url, fresh_session = _get_fresh_uptodown_url(uptodown_detail)
        if fresh_url:
            actual_url = fresh_url
            session = fresh_session
    elif 'uptodown.com' in apk_url:
        session = requests.Session()
        session.headers.update(HEADERS)

    got = download_file(actual_url, path, session=session)
    if not got:
        if uptodown_detail:
            download_page = uptodown_detail.rstrip('/') + '/download'
            print(f'  Download failed, using Uptodown link: {download_page}')
            return download_page, 0, None
        return None, 0, None

    file_size = os.path.getsize(path)
    size_mb = file_size / 1024 / 1024

    # Skip upload if file exceeds max size (prevents OOM on limited-RAM servers)
    if max_size_mb > 0 and size_mb > max_size_mb:
        print(f'  ⚠️ APK too large ({size_mb:.1f} MB > {max_size_mb} MB limit), skipping upload')
        try:
            os.remove(path)
        except Exception:
            pass
        return None, size_mb, None

    # Upload to Telegram (handles any file size via split)
    tg_link, _ = upload_apk_to_telegram(
        path, app_title=title or app_id, app_id=app_id, version=version
    )

    # Clean up temp file after upload (don't store locally to save disk space)
    local_path = None
    try:
        if tg_link:
            local_path = tg_link  # Use Telegram link as the "local" path
        # Always remove the temp file to prevent disk full
        os.remove(path)
    except Exception as e:
        print(f'  Cleanup error: {e}')

    if tg_link:
        return tg_link, size_mb, local_path

    return None, 0, local_path


def check_secrets():
    ok = True
    if not os.environ.get('TELEGRAM_BOT_TOKEN'):
        print('  Secrets: TELEGRAM_BOT_TOKEN missing')
        ok = False
    if not os.environ.get('TELEGRAM_CHANNEL_ID'):
        print('  Secrets: TELEGRAM_CHANNEL_ID missing')
        ok = False
    return ok
