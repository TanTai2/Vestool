import os
import shutil
import tempfile
from typing import List, Dict
try:
    from google_play_scraper import search as gp_search, app as gp_app
except Exception:
    gp_search = None
    gp_app = None
try:
    from werkzeug.utils import secure_filename
except Exception:
    secure_filename = lambda x: x
try:
    from bots.bot_crawler import _uptodown_search_get_detail, _uptodown_direct, _apkcombo_search_get_detail, _apkcombo_direct
except Exception:
    _uptodown_search_get_detail = None
    _uptodown_direct = None
    _apkcombo_search_get_detail = None
    _apkcombo_direct = None
try:
    from api.packagestore import get_apkinfo
except Exception:
    get_apkinfo = None
try:
    from api.models.package import Package
except Exception:
    Package = None


def tim_kiem_app_ngoai(tu_khoa: str, limit: int = 12) -> List[Dict]:
    items: List[Dict] = []
    q = (tu_khoa or "").strip()
    if not q or not gp_search:
        return items
    try:
        res = gp_search(q, lang='vi', country='vn')
        for r in res[:limit]:
            app_id = r.get('appId') or ''
            title = r.get('title') or app_id
            icon = r.get('icon') or ''
            desc = ''
            try:
                if gp_app and app_id:
                    info = gp_app(app_id, lang='vi', country='vn')
                    desc = info.get('description') or ''
            except Exception:
                desc = ''
            apk_url = None
            try:
                if _uptodown_search_get_detail and _uptodown_direct:
                    det = _uptodown_search_get_detail(app_id=app_id, title=title)
                    if det:
                        apk_url = _uptodown_direct(det)
                if not apk_url and _apkcombo_search_get_detail and _apkcombo_direct:
                    det2 = _apkcombo_search_get_detail(title)
                    if det2:
                        apk_url = _apkcombo_direct(det2)
            except Exception:
                apk_url = None
            items.append({
                'app_id': app_id,
                'title': title,
                'icon': icon,
                'description': desc,
                'apk_url': apk_url
            })
    except Exception:
        items = []
    return items


def vestool_upload_local(file_path: str) -> Dict:
    if not file_path or not os.path.isfile(file_path):
        return {'success': False}
    tmp_dir = tempfile.gettempdir()
    tmp_copy = os.path.join(tmp_dir, os.path.basename(file_path))
    shutil.copy(file_path, tmp_copy)
    if not get_apkinfo:
        return {'success': False}
    apk = get_apkinfo(tmp_copy)
    name = secure_filename(apk.package) if apk else os.path.basename(file_path)
    dest_dir = os.path.join('.', 'packages')
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f'{name}.apk')
    shutil.move(tmp_copy, dest_path)
    is_new = True
    try:
        if Package:
            existing = list(Package.select().where(Package.name == apk.package))
            if existing:
                is_new = False
                Package.update(version=apk.version_name, file=dest_path).where(Package.id == existing[0].id).execute()
            else:
                Package.create(name=apk.package, version=apk.version_name, file=dest_path)
    except Exception:
        pass
    return {
        'success': True,
        'package': apk.package if apk else name,
        'version': apk.version_name if apk else '',
        'file': dest_path,
        'is_new': is_new
    }
