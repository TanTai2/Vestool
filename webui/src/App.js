import React, { useState, useEffect } from 'react';

// Generate colorful placeholder based on app name
const gradientColors = [
  ['%23FF6B6B', '%23FF8E53'], // red-orange
  ['%234ECDC4', '%2345B7D1'], // teal-cyan
  ['%23A855F7', '%23EC4899'], // purple-pink
  ['%23F59E0B', '%23EF4444'], // amber-red
  ['%233B82F6', '%238B5CF6'], // blue-purple
  ['%2310B981', '%2306B6D4'], // emerald-cyan
  ['%23F472B6', '%23FB7185'], // pink
  ['%236366F1', '%23A855F7'], // indigo-purple
];

function getPlaceholderIcon(appName) {
  const firstChar = (appName || 'A').charAt(0).toUpperCase();
  const colorIndex = firstChar.charCodeAt(0) % gradientColors.length;
  const [color1, color2] = gradientColors[colorIndex];
  return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><defs><linearGradient id="grad" x1="0%25" y1="0%25" x2="100%25" y2="100%25"><stop offset="0%25" style="stop-color:${color1}"/><stop offset="100%25" style="stop-color:${color2}"/></linearGradient></defs><rect width="80" height="80" rx="16" ry="16" fill="url(%23grad)"/><text x="40" y="52" text-anchor="middle" font-size="36" font-weight="bold" fill="white">${firstChar}</text></svg>`;
}

function parseDownloadInfo(telegramLink, apkSizeMb) {
  if (!telegramLink) return { url: null, sizeMb: apkSizeMb || null };
  const parts = telegramLink.split('#size=');
  const url = parts[0] || null;
  const sizeMb = parts[1] ? parseFloat(parts[1]) : (apkSizeMb || null);
  return { url, sizeMb };
}

// Check if URL is a Telegram link
function isTelegramLink(url) {
  return url && (url.includes('t.me/') || url.includes('telegram.'));
}

// Build proxy download URL for Telegram links
function getProxyDownloadUrl(telegramLink, appName) {
  if (!telegramLink || !isTelegramLink(telegramLink)) {
    return telegramLink; // Return as-is for direct links
  }
  // Use VPS as proxy to download from Telegram
  const safeName = (appName || 'app').replace(/[^a-zA-Z0-9._-]/g, '_') + '.apk';
  return `/api/download?link=${encodeURIComponent(telegramLink)}&name=${encodeURIComponent(safeName)}`;
}

// Get the best download URL - prefer local files, then direct links, then proxy for Telegram
function getBestDownloadUrl(app) {
  const appName = app.title || app.app_id || 'app';
  
  // Priority 1: local_apk_url - direct download from our server (fastest!)
  if (app.local_apk_url) {
    // Convert /data/apks/filename.apk to /api/apk/filename.apk
    const localUrl = app.local_apk_url.replace('/data/apks/', '/api/apk/');
    return { url: localUrl, isDirect: true, sizeMb: app.apk_size_mb, isLocal: true };
  }
  
  // Priority 2: apk_url if it's a direct download (not Telegram)
  if (app.apk_url && !isTelegramLink(app.apk_url)) {
    return { url: app.apk_url, isDirect: true, sizeMb: app.apk_size_mb };
  }
  
  // Priority 3: telegram_link - use proxy for direct download through VPS
  const { url: tgUrl, sizeMb } = parseDownloadInfo(app.telegram_link, app.apk_size_mb);
  if (tgUrl) {
    // Use proxy URL to download directly without opening Telegram
    const proxyUrl = getProxyDownloadUrl(tgUrl, appName);
    return { url: proxyUrl, isDirect: true, sizeMb, originalTgLink: tgUrl };
  }
  
  // Priority 4: apk_url - if Telegram, use proxy
  if (app.apk_url) {
    if (isTelegramLink(app.apk_url)) {
      const proxyUrl = getProxyDownloadUrl(app.apk_url, appName);
      return { url: proxyUrl, isDirect: true, sizeMb: app.apk_size_mb, originalTgLink: app.apk_url };
    }
    return { url: app.apk_url, isDirect: true, sizeMb: app.apk_size_mb };
  }
  
  return { url: null, isDirect: false, sizeMb: app.apk_size_mb };
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch { return ''; }

}

/* ==================== HEADER ==================== */
function Header({ searchQuery, onSearch, onGoHome, activeCategory, onCategoryChange }) {
  return (
    <header className="bg-white shadow-sm sticky top-0 z-50 border-b border-gray-100">
      {/* Main Header */}
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
        {/* Logo - Click to go home */}
        <div className="cursor-pointer select-none group" onClick={onGoHome}>
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 bg-gradient-to-br from-red-500 to-red-600 rounded-lg flex items-center justify-center group-hover:scale-105 transition-transform">
              <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
            <span className="text-xl font-bold text-red-500">VesTool</span>
          </div>
        </div>
        
        {/* Search Bar */}
        <div className="flex-1 max-w-xl">
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearch(e.target.value)}
              placeholder="Tìm kiếm ứng dụng..."
              className="w-full rounded-full border border-gray-200 bg-gray-50 px-4 py-2.5 pl-10 focus:outline-none focus:border-red-400 focus:bg-white text-sm transition-all"
            />
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
        </div>
      </div>
      
      {/* Category Navigation - Clean pills */}
      <nav className="border-t border-gray-100">
        <div className="max-w-7xl mx-auto px-4">
          <ul className="flex gap-1 py-2 overflow-x-auto scrollbar-hide">
            <NavItem label="Đang hot" icon={<FireIcon />} active={activeCategory === 'hot'} onClick={() => onCategoryChange('hot')} />
            <NavItem label="Game" icon={<GameIcon />} active={activeCategory === 'game'} onClick={() => onCategoryChange('game')} />
            <NavItem label="Mạng xã hội" icon={<SocialIcon />} active={activeCategory === 'social'} onClick={() => onCategoryChange('social')} />
            <NavItem label="Công cụ" icon={<ToolIcon />} active={activeCategory === 'tool'} onClick={() => onCategoryChange('tool')} />
            <NavItem label="Video & Phim" icon={<VideoIcon />} active={activeCategory === 'video'} onClick={() => onCategoryChange('video')} />
            <NavItem label="Âm nhạc" icon={<MusicIcon />} active={activeCategory === 'music'} onClick={() => onCategoryChange('music')} />
            <NavItem label="Giáo dục" icon={<BookIcon />} active={activeCategory === 'education'} onClick={() => onCategoryChange('education')} />
            <NavItem label="Mua sắm" icon={<ShopIcon />} active={activeCategory === 'shopping'} onClick={() => onCategoryChange('shopping')} />
          </ul>
        </div>
      </nav>
    </header>
  );
}

/* ==================== SVG ICONS ==================== */
const FireIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 23c-4.97 0-9-3.582-9-8 0-2.847 1.628-5.428 4.086-7.348L12 3l4.914 4.652C19.372 9.572 21 12.153 21 15c0 4.418-4.03 8-9 8zm0-2c3.866 0 7-2.691 7-6 0-2.106-1.276-4.16-3.383-5.837L12 6l-3.617 3.163C6.276 10.84 5 12.894 5 15c0 3.309 3.134 6 7 6z"/>
  </svg>
);

const GameIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-10 7H8v3H6v-3H3v-2h3V8h2v3h3v2zm4.5 2c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4-3c-.83 0-1.5-.67-1.5-1.5S18.67 9 19.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/>
  </svg>
);

const SocialIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
  </svg>
);

const ToolIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/>
  </svg>
);

const VideoIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z"/>
  </svg>
);

const MusicIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
  </svg>
);

const BookIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/>
  </svg>
);

const ShopIcon = () => (
  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
    <path d="M7 18c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49c.08-.14.12-.31.12-.48 0-.55-.45-1-1-1H5.21l-.94-2H1zm16 16c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
  </svg>
);

/* ==================== NAV ITEM ==================== */
function NavItem({ icon, label, active = false, onClick }) {
  return (
    <li 
      className={`
        flex items-center gap-1.5 px-3 py-1.5 rounded-full cursor-pointer whitespace-nowrap transition-all text-sm
        ${active 
          ? 'bg-red-500 text-white' 
          : 'text-gray-600 hover:text-red-500 hover:bg-red-50'
        }
      `}
      onClick={onClick}
    >
      {icon}
      <span className="font-medium">{label}</span>
    </li>
  );
}

/* ==================== APP CARD (Index) ==================== */
function AppCard({ app, onClick }) {
  const { url: apkUrl, isDirect, sizeMb } = getBestDownloadUrl(app);
  const hasApk = !!apkUrl;
  const placeholder = getPlaceholderIcon(app.title);

  return (
    <div
      className="bg-white rounded-xl shadow-md p-4 flex items-center gap-4 hover:shadow-xl transition-all cursor-pointer border border-gray-100 hover:border-red-200 group"
      onClick={() => onClick(app)}
    >
      {/* App Icon with subtle glow */}
      <div className="relative flex-shrink-0">
        <div className="absolute inset-0 bg-red-500/10 rounded-xl blur-md opacity-0 group-hover:opacity-100 transition-opacity"></div>
        <img
          src={app.icon || placeholder}
          alt={app.title}
          className="relative w-14 h-14 rounded-xl object-cover group-hover:scale-105 transition-transform shadow-sm"
          referrerPolicy="no-referrer"
          crossOrigin="anonymous"
          onError={(e) => { e.target.src = placeholder; }}
        />
      </div>
      
      {/* App Info */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-gray-900 truncate group-hover:text-red-600 transition-colors">{app.title}</div>
        <div className="text-xs text-gray-400 truncate font-mono">{app.app_id}</div>
        <div className="flex items-center gap-3 mt-1.5">
          {sizeMb > 0 && (
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              {sizeMb.toFixed(1)} MB
            </span>
          )}
          {app.date && (
            <span className="text-xs text-gray-400">{formatDate(app.date)}</span>
          )}
        </div>
      </div>
      
      {/* Action Button */}
      <div className="flex-shrink-0">
        {hasApk ? (
          <span className="px-4 py-2 rounded-lg bg-gradient-to-r from-red-500 to-red-600 text-white text-xs font-bold shadow-md group-hover:shadow-lg group-hover:from-red-600 group-hover:to-red-700 transition-all">
            Tải APK
          </span>
        ) : (
          <span className="px-4 py-2 rounded-lg bg-gray-100 text-gray-500 text-xs font-medium group-hover:bg-gray-200 transition-colors">
            Chi tiết
          </span>
        )}
      </div>
    </div>
  );
}

/* ==================== TOP APP ITEM (Sidebar) ==================== */
function TopAppItem({ app, rank, onClick }) {
  const placeholder = getPlaceholderIcon(app.title);
  return (
    <div
      className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 rounded-lg p-2 -m-1 transition group"
      onClick={() => onClick(app)}
    >
      <span className={`text-sm font-bold w-6 h-6 rounded-md flex items-center justify-center ${
        rank === 1 ? 'bg-yellow-100 text-yellow-600' :
        rank === 2 ? 'bg-gray-100 text-gray-600' :
        rank === 3 ? 'bg-orange-100 text-orange-600' :
        'bg-gray-50 text-gray-400'
      }`}>{rank}</span>
      <img
        src={app.icon || placeholder}
        alt={app.title}
        className="w-10 h-10 rounded-lg object-cover group-hover:scale-105 transition-transform shadow-sm"
        referrerPolicy="no-referrer"
        crossOrigin="anonymous"
        onError={(e) => { e.target.src = placeholder; }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-900 truncate group-hover:text-red-600 transition-colors">{app.title}</div>
        <div className="text-xs text-gray-400 truncate font-mono">{app.app_id}</div>
      </div>
    </div>
  );
}

/* ==================== LOADING SPINNER ==================== */
function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="animate-spin rounded-full h-10 w-10 border-4 border-gray-200 border-t-red-500 shadow-lg shadow-red-300/30"></div>
    </div>
  );
}

/* ==================== CATEGORY DETECTION ==================== */
// EXACT APP_ID MATCHES - Highest priority (for edge cases)
const EXACT_CATEGORIES = {
  // Tools that have misleading package names
  'com.instagram.basel': 'tool',           // Edits: Video Maker
  'com.desygner.socialposts': 'tool',      // Tạo Bài Đăng MXH
  'com.ss.android.tt.creator': 'tool',     // TikTok Studio  
  'io.publer': 'tool',                     // Publer Social Media Tools
  'com.webhaus.planyourgramscheduler': 'tool', // Plann
  'com.google.android.googlequicksearchbox': 'tool', // Google Search
  'com.google.android.gm': 'tool',         // Gmail
  'com.facebook.adsmanager': 'tool',       // FB Ads Manager
  
  // Social apps
  'com.nglreactnative': 'social',          // NGL Q&A
  'com.baitu.qingshu': 'social',           // Poppo Live
  'io.friendly.instagram': 'social',       // Friendly for Instagram
  'com.discoverapp': 'social',             // Discover from Facebook
  'com.bytedance.snail': 'social',         // Whee TikTok Chat
  
  // Shopping
  'com.tiktokshop.seller': 'shopping',     // TikTok Shop Seller

  // Navigation/Maps
  'com.google.android.apps.maps': 'tool',  // Google Maps
  
  // Video
  'com.ss.android.ugc.tiktok.livewallpaper': 'video', // TikTok Wallpaper
};

// Pattern-based categories (checked in order)
const PATTERN_CATEGORIES = [
  // Video/Streaming - check early, specific patterns
  { cat: 'video', patterns: [/youtube/, /netflix/, /\.video\./, /\.movie/, /\.tv\./, /player/, /fptplay/, /vieon/, /iqiyi/, /wetv/, /bilibili/, /vimeo/, /twitch/] },
  
  // Music - specific patterns
  { cat: 'music', patterns: [/spotify/, /soundcloud/, /\.music\./, /zing\.mp3/, /nhaccuatui/, /shazam/, /pandora/, /deezer/] },
  
  // Shopping - specific patterns  
  { cat: 'shopping', patterns: [/shopee/, /lazada/, /tiki\./, /sendo/, /amazon/, /alibaba/, /ebay/] },
  
  // Education
  { cat: 'education', patterns: [/duolingo/, /\.education/, /\.learn\./, /\.study/, /dictionary/, /\.school/, /coursera/, /udemy/] },

  // Tools - check BEFORE social (canva, editor apps)
  { cat: 'tool', patterns: [/canva/, /\.editor\./, /cleaner/, /booster/, /\.vpn/, /browser/, /keyboard/, /launcher/, /filemanager/, /scanner/, /calculator/, /translator/] },
  
  // Social Networks - main apps (specific patterns to avoid false positives)
  { cat: 'social', patterns: [
    /com\.facebook\./, /com\.instagram\./, /com\.twitter/, /com\.snapchat/,
    /com\.whatsapp/, /org\.telegram/, /com\.viber/, /com\.discord/,
    /com\.reddit/, /com\.linkedin/, /com\.pinterest/, /com\.tumblr/,
    /jp\.naver\.line/, /com\.zing\.zalo/,
    /com\.zhiliaoapp\.musically/, /com\.ss\.android\.ugc\./,
    /messenger/
  ]},
  
  // Games - check LAST (broad pattern)
  { cat: 'game', patterns: [/game/, /\.arcade/, /\.puzzle/, /\.racing/, /slicer/, /cutter/, /supercell/, /gameloft/, /zynga/, /\.casino/, /poker/, /slots/] },
];

// Title keywords - fallback only
const TITLE_KEYWORDS = {
  game: ['game', 'games', 'gaming', '3d cut', 'arcade'],
  social: ['chat', 'messenger', 'gọi và nhắn', 'trò chuyện', 'kết nối'],
  tool: ['chỉnh sửa', 'editor', 'quảng cáo', 'quản lý', 'công cụ'],
  video: ['video maker', 'xem phim', 'movie'],
  music: ['nhạc', 'music', 'podcast'],
  shopping: ['shop', 'mua sắm', 'seller'],
};

function categorizeApp(app) {
  const appId = (app.app_id || '').toLowerCase();
  const title = (app.title || '').toLowerCase();
  
  // STEP 1: EXACT match (highest priority)
  if (EXACT_CATEGORIES[appId]) {
    return EXACT_CATEGORIES[appId];
  }
  
  // STEP 2: Pattern matching (in order)
  for (const { cat, patterns } of PATTERN_CATEGORIES) {
    if (patterns.some(p => p.test(appId))) {
      return cat;
    }
  }
  
  // STEP 3: Title keywords (fallback)
  for (const [category, keywords] of Object.entries(TITLE_KEYWORDS)) {
    if (keywords.some(kw => title.includes(kw))) {
      return category;
    }
  }
  
  // STEP 4: Default
  return 'other';
}

/* ==================== HORIZONTAL APP CARD ==================== */
function HorizontalAppCard({ app, onClick, rank }) {
  const { url: apkUrl, isDirect, sizeMb } = getBestDownloadUrl(app);
  const hasApk = !!apkUrl;
  const placeholder = getPlaceholderIcon(app.title);

  return (
    <div
      className="flex-shrink-0 w-40 bg-white rounded-xl shadow-md p-3 hover:shadow-xl transition-all cursor-pointer border border-gray-100 hover:border-red-200 group"
      onClick={() => onClick(app)}
    >
      {/* Rank badge */}
      {rank && (
        <div className={`absolute top-2 left-2 w-6 h-6 rounded-full text-white text-xs font-bold flex items-center justify-center ${
          rank === 1 ? 'bg-gradient-to-br from-yellow-400 to-amber-500' :
          rank === 2 ? 'bg-gradient-to-br from-gray-300 to-gray-400' :
          rank === 3 ? 'bg-gradient-to-br from-orange-400 to-orange-500' :
          'bg-gradient-to-br from-red-500 to-red-600'
        }`}>
          {rank}
        </div>
      )}
      
      {/* App Icon */}
      <div className="relative">
        <div className="absolute inset-0 bg-red-500/10 rounded-xl blur-md opacity-0 group-hover:opacity-100 transition-opacity"></div>
        <img
          src={app.icon || placeholder}
          alt={app.title}
          className="relative w-16 h-16 rounded-xl object-cover mx-auto group-hover:scale-105 transition-transform shadow-sm"
          referrerPolicy="no-referrer"
          crossOrigin="anonymous"
          onError={(e) => { e.target.src = placeholder; }}
        />
      </div>
      
      <div className="mt-2.5 text-center">
        <div className="text-xs font-semibold text-gray-900 truncate group-hover:text-red-600 transition-colors">{app.title}</div>
        {sizeMb > 0 && (
          <div className="text-xs text-gray-400 mt-0.5">{sizeMb.toFixed(1)} MB</div>
        )}
        <div className="mt-2">
          {hasApk ? (
            <span className="inline-block px-3 py-1 rounded-md bg-gradient-to-r from-red-500 to-red-600 text-white text-xs font-bold group-hover:from-red-600 group-hover:to-red-700 transition-all">
              Tải APK
            </span>
          ) : (
            <span className="inline-block px-3 py-1 rounded-md bg-gray-100 text-gray-500 text-xs font-medium">
              Chi tiết
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ==================== CATEGORY SECTION ==================== */
/* ==================== CATEGORY ICON MAPPING ==================== */
function getCategoryIcon(emoji) {
  const iconClass = "w-4 h-4 text-red-500";
  const icons = {
    '🔥': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M12 23c-4.97 0-9-3.582-9-8 0-2.847 1.628-5.428 4.086-7.348L12 3l4.914 4.652C19.372 9.572 21 12.153 21 15c0 4.418-4.03 8-9 8z"/></svg>,
    '🎮': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-10 7H8v3H6v-3H3v-2h3V8h2v3h3v2zm4.5 2c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4-3c-.83 0-1.5-.67-1.5-1.5S18.67 9 19.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg>,
    '💬': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>,
    '🛠️': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>,
    '🎬': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z"/></svg>,
    '🎵': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>,
    '📚': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/></svg>,
    '🛒': <svg className={iconClass} fill="currentColor" viewBox="0 0 24 24"><path d="M7 18c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49c.08-.14.12-.31.12-.48 0-.55-.45-1-1-1H5.21l-.94-2H1zm16 16c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>,
  };
  return icons[emoji] || <span className="text-lg">{emoji}</span>;
}

function CategorySection({ title, emoji, apps, onSelectApp, showRank = false, bgGradient = 'from-gray-900 to-gray-800' }) {
  if (apps.length === 0) return null;
  
  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
          <span className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center">{getCategoryIcon(emoji)}</span>
          <span>{title}</span>
          <span className="text-xs font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{apps.length}</span>
        </h2>
        <button className="text-sm text-red-500 hover:text-red-600 font-medium transition flex items-center gap-1">
          Xem tất cả
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      
      {/* Horizontal Scroll Container */}
      <div className="relative">
        {/* Scrollable content */}
        <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide" style={{scrollbarWidth: 'none', msOverflowStyle: 'none'}}>
          {apps.slice(0, 12).map((app, idx) => (
            <HorizontalAppCard 
              key={app.app_id || idx} 
              app={app} 
              onClick={onSelectApp}
              rank={showRank ? idx + 1 : null}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

/* ==================== TRENDING HERO SECTION ==================== */
function TrendingHero({ app, onSelectApp }) {
  if (!app) return null;
  
  const { url: apkUrl, isDirect, sizeMb } = getBestDownloadUrl(app);
  const hasApk = !!apkUrl;
  const placeholder = getPlaceholderIcon(app.title);

  return (
    <section className="mb-8">
      <div 
        className="relative rounded-2xl overflow-hidden bg-gradient-to-r from-red-600 via-red-500 to-orange-500 cursor-pointer group"
        onClick={() => onSelectApp(app)}
      >
        {/* Background pattern */}
        <div className="absolute inset-0 opacity-10" style={{backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'1\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")'}}></div>
        
        {/* Content */}
        <div className="relative p-6 flex items-center gap-6">
          {/* Badge */}
          <div className="absolute top-4 left-4">
            <div className="flex items-center gap-2 bg-yellow-400 text-yellow-900 px-3 py-1 rounded-full text-xs font-bold shadow-lg">
              <span className="w-2 h-2 bg-yellow-900 rounded-full animate-pulse"></span>
              TOP TRENDING
            </div>
          </div>
          
          {/* App Icon */}
          <div className="relative mt-6">
            <div className="absolute inset-0 bg-white/20 rounded-2xl blur-xl scale-110"></div>
            <img
              src={app.icon || placeholder}
              alt={app.title}
              className="relative w-24 h-24 rounded-2xl object-cover shadow-2xl border-2 border-white/30 group-hover:scale-105 transition-transform"
              referrerPolicy="no-referrer"
              crossOrigin="anonymous"
              onError={(e) => { e.target.src = placeholder; }}
            />
          </div>
          
          {/* Info */}
          <div className="flex-1 text-white mt-6">
            <h3 className="text-2xl font-bold mb-1 group-hover:text-yellow-200 transition-colors drop-shadow-lg">{app.title}</h3>
            <p className="text-white/70 text-sm mb-3 font-mono">{app.app_id}</p>
            <div className="flex items-center gap-3">
              {sizeMb > 0 && (
                <span className="text-sm bg-white/20 backdrop-blur-sm px-3 py-1 rounded-full font-medium">{sizeMb.toFixed(1)} MB</span>
              )}
              {hasApk && (
                <span className="text-sm bg-green-500/40 backdrop-blur-sm px-3 py-1 rounded-full font-medium flex items-center gap-1">
                  <span className="w-2 h-2 bg-green-400 rounded-full"></span>
                  APK sẵn sàng
                </span>
              )}
            </div>
          </div>
          
          {/* Download Button */}
          {hasApk && (
            <a
              href={apkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-6 px-6 py-3 bg-white text-red-600 font-bold rounded-xl shadow-xl hover:shadow-2xl hover:scale-105 transition-all no-underline flex items-center gap-2"
              onClick={(e) => e.stopPropagation()}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Tải ngay
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

/* ==================== OLD VERSIONS SECTION ==================== */
function OldVersionsSection({ appId, appTitle }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    fetchVersions();
  }, [appId]);

  async function fetchVersions() {
    setLoading(true);
    setError(null);
    try {
      // Try API first, fallback to static file
      const sources = [
        `/api/versions/${appId}`,
        `/data/versions/${appId.replace(/\./g, '_')}.json`,
        `http://${window.location.hostname}:5000/api/versions/${appId}`,
      ];
      
      let data = null;
      for (const url of sources) {
        try {
          const res = await fetch(url);
          if (res.ok) {
            data = await res.json();
            console.log('Loaded versions from:', url);
            break;
          }
        } catch (e) {
          console.log('Failed versions from:', url);
        }
      }
      
      if (!data || data.length === 0) {
        setVersions([]);
        setLoading(false);
        return;
      }
      
      // Sort versions by parsed version number descending
      data.sort((a, b) => {
        const pa = (a.version_name || '').split('.').map(Number);
        const pb = (b.version_name || '').split('.').map(Number);
        for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
          const diff = (pb[i] || 0) - (pa[i] || 0);
          if (diff !== 0) return diff;
        }
        return 0;
      });
      setVersions(data);
    } catch (err) {
      console.log('Versions fetch:', err.message);
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }

  const displayed = showAll ? versions : versions.slice(0, 5);

  if (loading) {
    return (
      <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-6 border border-gray-100">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          <span role="img" aria-label="history">&#x1F4E6;</span> Phiên bản cũ
        </h2>
        <div className="flex items-center justify-center py-6">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-200 border-t-red-500"></div>
          <span className="ml-3 text-sm text-gray-400">Đang tải...</span>
        </div>
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-6 border border-gray-100">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          <span role="img" aria-label="history">&#x1F4E6;</span> Phiên bản cũ
        </h2>
        <div className="text-center py-6">
          <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
            <span className="text-gray-400 text-xl">&#x1F4CB;</span>
          </div>
          <p className="text-gray-400 text-sm">Chưa có dữ liệu phiên bản cũ</p>
          <p className="text-gray-300 text-xs mt-1">Chạy <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">python3 bots/crawl_versions.py</code> để cào dữ liệu</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-6 border border-gray-100 hover:shadow-xl transition-shadow">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">
          <span role="img" aria-label="history">&#x1F4E6;</span> Phiên bản cũ ({versions.length})
        </h2>
      </div>

      <div className="space-y-0 divide-y divide-gray-100">
        {displayed.map((v, idx) => {
          // Build download URL - prefer local, then proxy for external sources
          const localUrl = v.local_apk_url || null;
          const externalUrl = v.apk_url || v.telegram_link || null;
          const versionName = `${appTitle}_v${v.version_name}.apk`.replace(/[^a-zA-Z0-9._-]/g, '_');
          
          // Use proxy for all external URLs (uptodown, apkpure, telegram)
          // This allows direct download through VPS without redirect
          let dlUrl = null;
          if (localUrl) {
            dlUrl = localUrl;  // Local file - direct serve
          } else if (externalUrl) {
            // Proxy all external URLs through VPS for direct download
            dlUrl = `/api/proxy-download?url=${encodeURIComponent(externalUrl)}&name=${encodeURIComponent(versionName)}`;
          }
          
          const hasUrl = !!dlUrl;
          const isDirect = true;  // Always direct download via local or proxy
          return (
            <div key={v.id || idx} className="flex items-center gap-4 py-3 group">
              {/* Version badge */}
              <div className="flex-shrink-0">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold ${
                  idx === 0
                    ? 'bg-gradient-to-br from-red-500 to-red-400 text-white shadow-lg shadow-red-300/50'
                    : 'bg-gray-100 text-gray-500'
                }`}>
                  {idx === 0 ? <span>&#x2B50;</span> : `v${idx + 1}`}
                </div>
              </div>

              {/* Version info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-800">
                    {appTitle} v{v.version_name}
                  </span>
                  {idx === 0 && (
                    <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full font-medium">
                      Mới nhất
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  {v.apk_size_mb > 0 && (
                    <span className="text-xs text-gray-400">{v.apk_size_mb.toFixed(1)} MB</span>
                  )}
                  {v.release_date && (
                    <span className="text-xs text-gray-400">{v.release_date}</span>
                  )}
                  {v.source && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-500 font-medium">
                      {v.source}
                    </span>
                  )}
                </div>
              </div>

              {/* Download button */}
              <div className="flex-shrink-0">
                {hasUrl && isDirect ? (
                  <a
                    href={dlUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-100 text-green-700 text-xs font-medium hover:bg-green-500 hover:text-white transition-all no-underline group-hover:shadow-sm hover:shadow-green-300/50"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Tải APK
                  </a>
                ) : hasUrl ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-yellow-50 text-yellow-600 text-xs font-medium">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Đang tải lên
                  </span>
                ) : (
                  <span className="text-xs text-gray-300 px-3 py-1.5">—</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Show more / less */}
      {versions.length > 5 && (
        <div className="mt-4 text-center">
          <button
            onClick={() => setShowAll(!showAll)}
            className="text-sm text-red-500 hover:text-red-600 font-medium transition"
          >
            {showAll
              ? <span>&#x25B2; Thu gọn</span>
              : <span>&#x25BC; Xem tất cả {versions.length} phiên bản</span>
            }
          </button>
        </div>
      )}
    </div>
  );
}

/* ==================== DETAIL PAGE ==================== */
function AppDetailPage({ app, onBack, relatedApps, onSelectApp }) {
  const { url: apkUrl, isDirect, sizeMb } = getBestDownloadUrl(app);
  const placeholder = getPlaceholderIcon(app.title);
  const hasApk = !!apkUrl;
  const isTelegram = !isDirect && apkUrl && apkUrl.includes('t.me/');
  const storageLabel = isDirect ? 'Direct Download' : (isTelegram ? 'Telegram' : 'External');

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-gray-50 to-red-50/20">
      {/* Breadcrumb */}
      <div className="max-w-5xl mx-auto px-4 pt-4">
        <nav className="flex items-center gap-2 text-sm text-gray-500 mb-4">
          <span className="hover:text-red-500 cursor-pointer transition-colors" onClick={onBack}>Trang chủ</span>
          <span>/</span>
          <span className="text-gray-800 font-medium truncate">{app.title}</span>
        </nav>
      </div>

      {/* Hero Section */}
      <div className="max-w-5xl mx-auto px-4">
        <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-2xl overflow-hidden hover:shadow-3xl transition-shadow border border-gray-100">
          {/* Top banner gradient */}
          <div className="h-40 bg-gradient-to-br from-red-600 via-red-500 to-red-400 relative overflow-hidden">
            <div className="absolute inset-0 bg-black/10"></div>
            <div className="absolute inset-0 opacity-20" style={{background: 'radial-gradient(circle at top right, rgba(255,255,255,0.3), transparent)'}}></div>
            {/* Animated particles effect */}
            <div className="absolute inset-0 overflow-hidden">
              <div className="absolute w-32 h-32 bg-white/10 rounded-full blur-xl -top-10 -right-10 animate-pulse"></div>
              <div className="absolute w-24 h-24 bg-white/10 rounded-full blur-xl bottom-0 left-1/4 animate-pulse" style={{animationDelay: '1s'}}></div>
            </div>
          </div>

          {/* App info overlay */}
          <div className="px-6 pb-6 -mt-12 relative">
            <div className="flex flex-col sm:flex-row gap-5 items-start">
              {/* Icon */}
              <img
                src={app.icon || placeholder}
                alt={app.title}
                className="w-24 h-24 rounded-2xl object-cover shadow-2xl shadow-red-300/50 border-4 border-white flex-shrink-0 hover:scale-105 transition-transform"
                referrerPolicy="no-referrer"
                crossOrigin="anonymous"
                onError={(e) => { e.target.src = placeholder; }}
              />
              {/* Text info */}
              <div className="flex-1 min-w-0 pt-2">
                <h1 className="text-2xl font-bold text-gray-900 leading-tight">{app.title}</h1>
                <p className="text-sm text-gray-500 mt-1">{app.app_id}</p>

                {/* Meta chips */}
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  {sizeMb > 0 && (
                    <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-600 rounded-full px-3 py-1 text-xs font-medium">
                      <span role="img" aria-label="size">&#x1F4BE;</span> {sizeMb.toFixed(1)} MB
                    </span>
                  )}
                  {app.date && (
                    <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-600 rounded-full px-3 py-1 text-xs font-medium">
                      <span role="img" aria-label="date">&#x1F4C5;</span> {formatDate(app.date)}
                    </span>
                  )}
                  {hasApk && (
                    <span className="inline-flex items-center gap-1 bg-red-50 text-red-700 rounded-full px-3 py-1 text-xs font-medium">
                      <span role="img" aria-label="check">&#x2705;</span> APK có sẵn
                    </span>
                  )}
                  {hasApk && (
                    <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-600 rounded-full px-3 py-1 text-xs font-medium">
                      {storageLabel}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Download Section */}
      <div className="max-w-5xl mx-auto px-4 mt-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Download + Description */}
          <div className="lg:col-span-2 space-y-5">
            {/* Download Card */}
            <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-6 border border-gray-100 hover:shadow-xl transition-shadow">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">
                <span role="img" aria-label="download">&#x2B07;&#xFE0F;</span> Tải xuống
              </h2>
              {hasApk ? (
                <div className="space-y-4">
                  <a
                    href={apkUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-3 w-full py-4 rounded-xl bg-gradient-to-r from-red-500 to-red-600 text-white text-lg font-bold shadow-lg shadow-red-500/40 hover:shadow-xl hover:shadow-red-500/60 transition-all no-underline transform hover:scale-[1.02] active:scale-[0.98]"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Tải APK ({sizeMb ? sizeMb.toFixed(1) + ' MB' : 'Download'})
                  </a>
                  <div className="flex items-center gap-3 p-3 bg-red-50 rounded-xl border border-red-200 shadow-md">
                    <span className="text-red-500 text-xl" role="img" aria-label="warning">&#x26A0;&#xFE0F;</span>
                    <p className="text-xs text-red-700">
                      Cho phép <strong>"Cài đặt từ nguồn không xác định"</strong> trong Cài đặt của thiết bị trước khi cài file APK.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                    <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                    </svg>
                  </div>
                  <p className="text-gray-500 font-medium">Chưa có file APK</p>
                  <p className="text-gray-400 text-sm mt-1">Ứng dụng này chưa được tải lên hệ thống</p>
                </div>
              )}
            </div>

            {/* Old Versions Card */}
            <OldVersionsSection appId={app.app_id} appTitle={app.title} />

            {/* Description Card */}
            <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-6 border border-gray-100 hover:shadow-xl transition-shadow">
              <h2 className="text-lg font-semibold text-gray-800 mb-3">
                <span role="img" aria-label="info">&#x1F4CB;</span> Mô tả ứng dụng
              </h2>
              {app.description ? (
                <p className="text-gray-600 leading-relaxed whitespace-pre-line">{app.description}</p>
              ) : (
                <p className="text-gray-400 italic">Chưa có mô tả cho ứng dụng này.</p>
              )}
            </div>

            {/* App Details Table */}
            <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-6 border border-gray-100 hover:shadow-xl transition-shadow">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">
                <span role="img" aria-label="detail">&#x1F50D;</span> Thông tin chi tiết
              </h2>
              <div className="divide-y divide-gray-100">
                <div className="flex py-3">
                  <span className="w-40 text-sm text-gray-500 flex-shrink-0">Package ID</span>
                  <span className="text-sm text-gray-800 font-mono break-all">{app.app_id}</span>
                </div>
                <div className="flex py-3">
                  <span className="w-40 text-sm text-gray-500 flex-shrink-0">Tên ứng dụng</span>
                  <span className="text-sm text-gray-800">{app.title}</span>
                </div>
                {sizeMb > 0 && (
                  <div className="flex py-3">
                    <span className="w-40 text-sm text-gray-500 flex-shrink-0">Kích thước APK</span>
                    <span className="text-sm text-gray-800">{sizeMb.toFixed(1)} MB</span>
                  </div>
                )}
                {app.date && (
                  <div className="flex py-3">
                    <span className="w-40 text-sm text-gray-500 flex-shrink-0">Ngày cập nhật</span>
                    <span className="text-sm text-gray-800">{formatDate(app.date)}</span>
                  </div>
                )}
                {hasApk && (
                  <div className="flex py-3">
                    <span className="w-40 text-sm text-gray-500 flex-shrink-0">Nguồn lưu trữ</span>
                    <span className="text-sm text-gray-800">{storageLabel}</span>
                  </div>
                )}
                <div className="flex py-3">
                  <span className="w-40 text-sm text-gray-500 flex-shrink-0">Trạng thái</span>
                  <span className={`text-sm font-medium ${hasApk ? 'text-red-600' : 'text-gray-400'}`}>
                    {hasApk ? 'Có sẵn để tải' : 'Chưa có APK'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Right Sidebar: Related Apps */}
          <div className="lg:col-span-1 space-y-5">
            {/* Quick Download (sticky) */}
            {hasApk && (
              <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-5 border border-gray-100 sticky top-20 hover:shadow-xl transition-shadow">
                <img
                  src={app.icon || placeholder}
                  alt={app.title}
                  className="w-14 h-14 rounded-xl object-cover mx-auto mb-3"
                  referrerPolicy="no-referrer"
                  crossOrigin="anonymous"
                  onError={(e) => { e.target.src = placeholder; }}
                />
                <p className="text-center text-sm font-semibold text-gray-800 truncate mb-3">{app.title}</p>
                <a
                  href={apkUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-red-500 to-red-600 text-white text-sm font-bold hover:shadow-lg hover:shadow-red-500/50 transition no-underline"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Tải ngay
                </a>
                {sizeMb > 0 && (
                  <p className="text-center text-xs text-gray-400 mt-2">{sizeMb.toFixed(1)} MB</p>
                )}
              </div>
            )}

            {/* Related apps */}
            <div className="bg-white/95 backdrop-blur-sm rounded-2xl shadow-lg p-5 border border-gray-100 hover:shadow-xl transition-shadow">
              <h3 className="text-base font-semibold text-gray-800 mb-4">
                <span role="img" aria-label="apps">&#x1F4F1;</span> Ứng dụng khác
              </h3>
              <div className="space-y-3">
                {relatedApps.length > 0 ? (
                  relatedApps.map((ra, idx) => (
                    <div
                      key={ra.app_id || idx}
                      className="flex items-center gap-3 cursor-pointer hover:bg-red-50/50 rounded-lg p-2 -mx-2 transition hover-lift"
                      onClick={() => onSelectApp(ra)}
                    >
                      <img
                        src={ra.icon || getPlaceholderIcon(ra.title)}
                        alt={ra.title}
                        className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                        referrerPolicy="no-referrer"
                        crossOrigin="anonymous"
                        onError={(e) => { e.target.src = getPlaceholderIcon(ra.title); }}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-800 truncate">{ra.title}</div>
                        <div className="text-xs text-gray-400 truncate">{ra.app_id}</div>
                      </div>
                      {(ra.apk_url) && (
                        <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0 shadow-lg shadow-red-500/50" title="APK có sẵn"></span>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-gray-400 text-center py-4">Không có ứng dụng liên quan</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Back button floating */}
      <div className="max-w-5xl mx-auto px-4 py-8">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-red-500 transition"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Quay lại trang chủ
        </button>
      </div>
    </div>
  );
}

/* ==================== INDEX PAGE ==================== */
function IndexPage({ apps, loading, error, searchQuery, onSearch, onRefresh, onSelectApp, activeCategory, onCategoryChange }) {
  const [showAllApps, setShowAllApps] = useState(false);
  
  const filtered = apps.filter((app) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (app.title || '').toLowerCase().includes(q) ||
      (app.app_id || '').toLowerCase().includes(q)
    );
  });

  // Sort apps - with APK first
  const withApk = filtered.filter((a) => a.apk_url);
  const withoutApk = filtered.filter((a) => !a.apk_url);
  const sortedApps = [...withApk, ...withoutApk];
  
  // Top trending (apps with APK, sorted by date)
  const trendingApps = [...withApk].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
  const topTrending = trendingApps[0];
  
  // Categorize apps
  const gameApps = filtered.filter(app => categorizeApp(app) === 'game');
  const socialApps = filtered.filter(app => categorizeApp(app) === 'social');
  const toolApps = filtered.filter(app => categorizeApp(app) === 'tool');
  const videoApps = filtered.filter(app => categorizeApp(app) === 'video');
  const musicApps = filtered.filter(app => categorizeApp(app) === 'music');
  const educationApps = filtered.filter(app => categorizeApp(app) === 'education');
  const shoppingApps = filtered.filter(app => categorizeApp(app) === 'shopping');
  
  // Display limit for all apps
  const displayedApps = showAllApps ? sortedApps : sortedApps.slice(0, 10);

  // If searching, show filtered results directly
  if (searchQuery.trim()) {
    return (
      <main className="max-w-7xl mx-auto px-4 py-8">
        {loading && <LoadingSpinner />}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4 text-red-700 shadow-md">
            Lỗi tải dữ liệu: {error}
            <button onClick={onRefresh} className="ml-3 underline hover:text-red-900 transition">Thử lại</button>
          </div>
        )}
        {!loading && !error && (
          <div className="animate-fadeInUp">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-800">
                🔍 Kết quả tìm kiếm "{searchQuery}" ({filtered.length})
              </h2>
              <button
                onClick={onRefresh}
                className="text-sm text-gray-500 hover:text-red-500 transition flex items-center gap-1"
              >
                🔄 Làm mới
              </button>
            </div>
            {sortedApps.length === 0 ? (
              <div className="text-center text-gray-500 py-16 bg-white/50 rounded-2xl">
                <div className="text-6xl mb-4">😔</div>
                <p className="text-lg">Không tìm thấy ứng dụng phù hợp</p>
                <p className="text-sm text-gray-400 mt-2">Thử tìm với từ khóa khác</p>
              </div>
            ) : (
              <div className="space-y-4">
                {sortedApps.map((app, idx) => (
                  <AppCard key={app.app_id || idx} app={app} onClick={onSelectApp} />
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      {loading && <LoadingSpinner />}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4 text-red-700 shadow-md">
          Lỗi tải dữ liệu: {error}
          <button onClick={onRefresh} className="ml-3 underline hover:text-red-900 transition">Thử lại</button>
        </div>
      )}
      {!loading && !error && (
        <div className="animate-fadeInUp">
          {/* Show category-specific view when not 'hot' */}
          {activeCategory !== 'hot' ? (
            <>
              {/* Category Header */}
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                  {getCategoryIcon(
                    activeCategory === 'game' ? '🎮' :
                    activeCategory === 'social' ? '💬' :
                    activeCategory === 'tool' ? '🛠️' :
                    activeCategory === 'video' ? '🎬' :
                    activeCategory === 'music' ? '🎵' :
                    activeCategory === 'education' ? '📚' :
                    activeCategory === 'shopping' ? '🛒' : '🔥'
                  )}
                  <span>
                    {activeCategory === 'game' ? 'Game' :
                     activeCategory === 'social' ? 'Mạng xã hội' :
                     activeCategory === 'tool' ? 'Công cụ & Tiện ích' :
                     activeCategory === 'video' ? 'Video & Phim' :
                     activeCategory === 'music' ? 'Âm nhạc' :
                     activeCategory === 'education' ? 'Giáo dục & Học tập' :
                     activeCategory === 'shopping' ? 'Mua sắm & Giao hàng' : 'Đang Hot'}
                  </span>
                  <span className="text-sm font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                    {(activeCategory === 'game' ? gameApps :
                      activeCategory === 'social' ? socialApps :
                      activeCategory === 'tool' ? toolApps :
                      activeCategory === 'video' ? videoApps :
                      activeCategory === 'music' ? musicApps :
                      activeCategory === 'education' ? educationApps :
                      activeCategory === 'shopping' ? shoppingApps : trendingApps).length}
                  </span>
                </h2>
                <button
                  onClick={() => onCategoryChange('hot')}
                  className="text-sm text-gray-500 hover:text-red-500 transition flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                  Quay lại
                </button>
              </div>
              
              {/* Category Apps Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {(activeCategory === 'game' ? gameApps :
                  activeCategory === 'social' ? socialApps :
                  activeCategory === 'tool' ? toolApps :
                  activeCategory === 'video' ? videoApps :
                  activeCategory === 'music' ? musicApps :
                  activeCategory === 'education' ? educationApps :
                  activeCategory === 'shopping' ? shoppingApps : trendingApps
                ).map((app, idx) => (
                  <AppCard key={app.app_id || idx} app={app} onClick={onSelectApp} />
                ))}
              </div>
              
              {/* Empty state */}
              {(activeCategory === 'game' ? gameApps :
                activeCategory === 'social' ? socialApps :
                activeCategory === 'tool' ? toolApps :
                activeCategory === 'video' ? videoApps :
                activeCategory === 'music' ? musicApps :
                activeCategory === 'education' ? educationApps :
                activeCategory === 'shopping' ? shoppingApps : trendingApps
              ).length === 0 && (
                <div className="text-center text-gray-500 py-16 bg-white rounded-xl">
                  <div className="text-5xl mb-4">📭</div>
                  <p className="text-lg">Chưa có ứng dụng nào trong danh mục này</p>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Top Trending Hero */}
              <TrendingHero app={topTrending} onSelectApp={onSelectApp} />
              
              {/* Promo Banner */}
              <section className="mb-8">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Banner 1 - Game */}
                  <div 
                    className="bg-gradient-to-br from-purple-600 to-pink-500 rounded-2xl p-5 text-white relative overflow-hidden group cursor-pointer hover:scale-[1.02] transition-transform"
                    onClick={() => onCategoryChange('game')}
                  >
                    <div className="absolute -top-10 -right-10 w-32 h-32 bg-white/10 rounded-full blur-2xl"></div>
                    <div className="relative">
                      <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center mb-2">
                        <GameIcon />
                      </div>
                      <h3 className="font-bold text-lg">Game Hot</h3>
                      <p className="text-white/70 text-sm">Tải game mới nhất miễn phí</p>
                    </div>
                  </div>
                  
                  {/* Banner 2 - Video */}
                  <div 
                    className="bg-gradient-to-br from-blue-600 to-cyan-500 rounded-2xl p-5 text-white relative overflow-hidden group cursor-pointer hover:scale-[1.02] transition-transform"
                    onClick={() => onCategoryChange('video')}
                  >
                    <div className="absolute -top-10 -right-10 w-32 h-32 bg-white/10 rounded-full blur-2xl"></div>
                    <div className="relative">
                      <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center mb-2">
                        <VideoIcon />
                      </div>
                      <h3 className="font-bold text-lg">Xem Phim</h3>
                      <p className="text-white/70 text-sm">Ứng dụng stream phim HD</p>
                    </div>
                  </div>
                  
                  {/* Banner 3 - Social */}
                  <div 
                    className="bg-gradient-to-br from-green-600 to-emerald-500 rounded-2xl p-5 text-white relative overflow-hidden group cursor-pointer hover:scale-[1.02] transition-transform"
                    onClick={() => onCategoryChange('social')}
                  >
                    <div className="absolute -top-10 -right-10 w-32 h-32 bg-white/10 rounded-full blur-2xl"></div>
                    <div className="relative">
                      <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center mb-2">
                        <SocialIcon />
                      </div>
                      <h3 className="font-bold text-lg">Mạng Xã Hội</h3>
                      <p className="text-white/70 text-sm">Kết nối bạn bè mọi lúc</p>
                    </div>
                  </div>
                </div>
              </section>
              
              {/* Hot Trending Section */}
              <CategorySection
                title="Đang Hot"
                emoji="🔥"
                apps={trendingApps.slice(1, 13)}
                onSelectApp={onSelectApp}
                showRank={true}
              />
              
              {/* Games Section */}
              <CategorySection
                title="Game"
                emoji="🎮"
                apps={gameApps}
                onSelectApp={onSelectApp}
              />
              
              {/* Social Media Section */}
              <CategorySection
                title="Mạng xã hội"
                emoji="💬"
                apps={socialApps}
                onSelectApp={onSelectApp}
              />
              
              {/* Tools Section */}
              <CategorySection
                title="Công cụ & Tiện ích"
                emoji="🛠️"
                apps={toolApps}
                onSelectApp={onSelectApp}
              />
              
              {/* Video & Movie Section */}
              <CategorySection
                title="Video & Phim"
                emoji="🎬"
                apps={videoApps}
                onSelectApp={onSelectApp}
              />
              
              {/* Music Section */}
              <CategorySection
                title="Âm nhạc"
                emoji="🎵"
                apps={musicApps}
                onSelectApp={onSelectApp}
              />
              
              {/* Education Section */}
              <CategorySection
                title="Giáo dục & Học tập"
                emoji="📚"
                apps={educationApps}
                onSelectApp={onSelectApp}
              />
              
              {/* Shopping Section */}
              <CategorySection
                title="Mua sắm & Giao hàng"
                emoji="🛒"
                apps={shoppingApps}
                onSelectApp={onSelectApp}
              />
            </>
          )}
        </div>
      )}
    </main>
  );
}

/* ==================== MAIN APP ==================== */
export default function App() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedApp, setSelectedApp] = useState(null); // null = index, object = detail
  const [activeCategory, setActiveCategory] = useState('hot'); // Category filter

  useEffect(() => {
    fetchApps();
  }, []);

  // Handle browser back/forward
  useEffect(() => {
    function handlePop() {
      setSelectedApp(null);
    }
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  }, []);

  async function fetchApps() {
    setLoading(true);
    setError(null);
    try {
      // Try multiple sources in order
      const sources = [
        '/api/apps',                    // If proxied
        '/data/apps.json',              // Static file via nginx
        'http://localhost:5000/api/apps', // Direct API call
        `http://${window.location.hostname}:5000/api/apps`, // API on same host
      ];
      
      let data = null;
      for (const url of sources) {
        try {
          const res = await fetch(url, { timeout: 5000 });
          if (res.ok) {
            data = await res.json();
            console.log('Loaded apps from:', url);
            break;
          }
        } catch (e) {
          console.log('Failed to load from:', url);
        }
      }
      
      if (data) {
        setApps(data);
      } else {
        throw new Error('Could not load apps from any source');
      }
    } catch (err) {
      console.error('Fetch error:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectApp(app) {
    setSelectedApp(app);
    window.scrollTo(0, 0);
    window.history.pushState({ app: app.app_id }, '', `?app=${app.app_id}`);
  }

  function handleGoHome() {
    setSelectedApp(null);
    setSearchQuery('');
    setActiveCategory('hot');
    window.scrollTo(0, 0);
    window.history.pushState({}, '', '/');
  }

  function handleCategoryChange(category) {
    setActiveCategory(category);
    setSearchQuery('');
    if (selectedApp) setSelectedApp(null);
    window.scrollTo(0, 0);
  }

  // Get related apps (same-ish category, or just random others)
  const relatedApps = selectedApp
    ? apps.filter((a) => a.app_id !== selectedApp.app_id && a.apk_url).slice(0, 6)
    : [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-gray-50 to-red-50/20">
      <Header
        searchQuery={searchQuery}
        onSearch={(q) => { setSearchQuery(q); setActiveCategory('hot'); if (selectedApp) setSelectedApp(null); }}
        onGoHome={handleGoHome}
        activeCategory={activeCategory}
        onCategoryChange={handleCategoryChange}
      />

      {selectedApp ? (
        <AppDetailPage
          app={selectedApp}
          onBack={handleGoHome}
          relatedApps={relatedApps}
          onSelectApp={handleSelectApp}
        />
      ) : (
        <IndexPage
          apps={apps}
          loading={loading}
          error={error}
          searchQuery={searchQuery}
          onSearch={setSearchQuery}
          onRefresh={fetchApps}
          onSelectApp={handleSelectApp}
          activeCategory={activeCategory}
          onCategoryChange={handleCategoryChange}
        />
      )}

      <footer className="text-center py-8 mt-8 bg-gray-900 border-t border-gray-800">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-center gap-2 mb-3">
            <div className="w-8 h-8 bg-gradient-to-br from-red-500 to-red-600 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
            <span className="text-white font-bold text-lg">VesTool</span>
          </div>
          <p className="text-gray-400 text-sm mb-4">Kho ứng dụng APK lớn nhất - Tải miễn phí, an toàn 100%</p>
          <div className="flex justify-center gap-6 text-gray-500 text-xs mb-4">
            <span className="hover:text-red-400 cursor-pointer transition">Game</span>
            <span className="hover:text-red-400 cursor-pointer transition">Social Media</span>
            <span className="hover:text-red-400 cursor-pointer transition">Tools</span>
            <span className="hover:text-red-400 cursor-pointer transition">Liên hệ</span>
          </div>
          <p className="text-gray-600 text-xs">© 2024 VesTool. Powered by Telegram</p>
        </div>
      </footer>
    </div>
  );
}
