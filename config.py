"""
VesTool Configuration
Telegram API + Cloudflare R2 credentials
"""
import os

# ==================== TELEGRAM CONFIG ====================
TELEGRAM = {
    # MTProto API (for large file downloads via Telethon/Pyrogram)
    'api_id': 39475646,
    'api_hash': 'be1addd395c6a9c9c7e7301d0d824ee3',
    'app_name': 'Vestool Pro',
    'short_name': 'Tantaicute',
    
    # Bot API
    'bot_token': '8560694013:AAG9ajjYkvZnc6FaJMPqaEB6ZcOBTHeq0tA',
    'channel_id': -1003864259175,
    
    # MTProto Servers
    'test_dc': {
        'host': '149.154.167.40',
        'port': 443,
        'dc_id': 2
    },
    'production_dc': {
        'host': '149.154.167.50',
        'port': 443,
        'dc_id': 2
    },
    
    # Local Bot API Server (no 50MB limit)
    'local_api_base': os.environ.get('TG_API_BASE', 'http://localhost:8081'),
}

# ==================== CLOUDFLARE R2 CONFIG ====================
R2 = {
    # Account credentials
    'account_id': '4ab86eee85a2f3d10bdd3568f290aab3',
    'access_key_id': 'f17824a216e648707ee7b23d7fda3fe7',
    'secret_access_key': 'ea781be6b6716b0dc0862f487f553ca79439685d4b329b6b70ac19c6cb67a926',
    
    # Bucket settings
    'bucket_name': os.environ.get('R2_BUCKET', 'vestool-apks'),
    'endpoint_url': f"https://4ab86eee85a2f3d10bdd3568f290aab3.r2.cloudflarestorage.com",
    
    # Public URL (configure in R2 dashboard)
    'public_url': os.environ.get('R2_PUBLIC_URL', 'https://apk.vestool.pro'),
}

# ==================== CRAWLER CONFIG ====================
CRAWLER = {
    # Sources priority (higher = preferred)
    'sources': [
        {'name': 'apkpure', 'base_url': 'https://apkpure.com', 'priority': 90},
        {'name': 'apkmirror', 'base_url': 'https://www.apkmirror.com', 'priority': 95},
        {'name': 'apkcombo', 'base_url': 'https://apkcombo.com', 'priority': 85},
        {'name': 'uptodown', 'base_url': 'https://en.uptodown.com/android', 'priority': 80},
        {'name': 'apkaio', 'base_url': 'https://apkaio.com', 'priority': 75},
        {'name': 'liteapks', 'base_url': 'https://liteapks.com', 'priority': 70},
        {'name': 'modyolo', 'base_url': 'https://modyolo.com', 'priority': 65},
        {'name': 'an1', 'base_url': 'https://an1.com', 'priority': 60},
    ],
    
    # Download settings
    'max_retries': 3,
    'retry_delay': 2,
    'timeout': 300,
    'chunk_size': 8192,
    
    # Temp directory
    'temp_dir': '/root/VesTool/tmp',
    'data_dir': '/root/VesTool/data',
}

# ==================== APP CATEGORIES ====================
CATEGORIES = {
    'streaming': 'Phim Nhạc & Streaming',
    'photo_video': 'Chỉnh Sửa Ảnh & Video',
    'education': 'Học Tập & Đọc Sách',
    'games': 'Game Offline Mod',
    'tools': 'Công Cụ & Tiện Ích',
    'office': 'Văn Phòng & Năng Suất',
    'travel': 'Bản Đồ & Du Lịch',
    'health': 'Sức Khỏe & Thể Thao',
    'mod_tools': 'Công Cụ Mod & Hack',
}
