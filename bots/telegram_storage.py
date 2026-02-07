import os
import requests

def download_file(url, out_path):
    r = requests.get(url, stream=True, timeout=300)
    r.raise_for_status()
    with open(out_path, 'wb') as f:
        for chunk in r.iter_content(8192):
            if chunk:
                f.write(chunk)
    return out_path

def upload_apk(apk_path):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        return None
    files = {'document': open(apk_path, 'rb')}
    data = {'chat_id': chat_id}
    resp = requests.post(f'https://api.telegram.org/bot{token}/sendDocument', data=data, files=files, timeout=300)
    resp.raise_for_status()
    msg = resp.json()
    file_id = msg['result']['document']['file_id']
    gf = requests.get(f'https://api.telegram.org/bot{token}/getFile', params={'file_id': file_id}, timeout=60)
    gf.raise_for_status()
    file_path = gf.json()['result']['file_path']
    return f'https://api.telegram.org/file/bot{token}/{file_path}'

def download_and_upload(apk_url, tmp_dir='tmp'):
    os.makedirs(tmp_dir, exist_ok=True)
    name = os.path.basename(apk_url.split('?')[0]) or 'app.apk'
    path = os.path.join(tmp_dir, name)
    download_file(apk_url, path)
    return upload_apk(path)

def send_text(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        return False
    resp = requests.post(f'https://api.telegram.org/bot{token}/sendMessage', json={
        'chat_id': chat_id,
        'text': message
    }, timeout=60)
    return resp.ok

def check_secrets():
    ok = True
    if not os.environ.get('TELEGRAM_BOT_TOKEN'):
        print('Secrets: TELEGRAM_BOT_TOKEN missing')
        ok = False
    if not os.environ.get('TELEGRAM_CHANNEL_ID'):
        print('Secrets: TELEGRAM_CHANNEL_ID missing')
        ok = False
    print(f'Secrets: Telegram token present={bool(os.environ.get("TELEGRAM_BOT_TOKEN"))}, channel present={bool(os.environ.get("TELEGRAM_CHANNEL_ID"))}')
    return ok
