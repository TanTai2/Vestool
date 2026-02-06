import React from 'react';

const placeholderIcon = 'data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"80\" height=\"80\"><rect width=\"80\" height=\"80\" rx=\"10\" ry=\"10\" fill=\"%23e5e7eb\"/></svg>';
const mockApps = [
  { name: 'Liên Quân', category: 'Trò chơi', icon: placeholderIcon },
  { name: 'TikTok', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'Tool MMO', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'PUBG Mobile', category: 'Trò chơi', icon: placeholderIcon },
  { name: 'Facebook', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'Messenger', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'YouTube', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'Zalo', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'Genshin Impact', category: 'Trò chơi', icon: placeholderIcon },
  { name: 'Liên Minh Tốc Chiến', category: 'Trò chơi', icon: placeholderIcon },
  { name: 'Shopee', category: 'Ứng dụng', icon: placeholderIcon },
  { name: 'Lazada', category: 'Ứng dụng', icon: placeholderIcon },
];

function Header() {
  return (
    <header className="bg-white shadow-sm">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
        <div className="text-2xl font-bold text-[#ff0000]">VesTool</div>
        <div className="flex-1">
          <input
            type="text"
            placeholder="Tìm kiếm ứng dụng..."
            className="w-full rounded-full border border-gray-300 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-[#ff0000] bg-white"
          />
        </div>
        <button className="px-4 py-2 rounded-md bg-[#ff0000] text-white font-semibold hover:brightness-95">
          Đăng App
        </button>
      </div>
      <nav className="border-t">
        <div className="max-w-7xl mx-auto px-4">
          <ul className="flex gap-6 py-3 text-sm">
            <li className="text-black font-medium">Trang chủ</li>
            <li className="text-gray-600 hover:text-black cursor-pointer">Trò chơi</li>
            <li className="text-gray-600 hover:text-black cursor-pointer">Ứng dụng</li>
            <li className="text-gray-600 hover:text-black cursor-pointer">Khám phá</li>
          </ul>
        </div>
      </nav>
    </header>
  );
}

function AppCard({ app }) {
  return (
    <div className="bg-white rounded-lg shadow-sm p-4 flex items-center gap-4">
      <img src={app.icon} alt={app.name} className="w-16 h-16 rounded-md object-cover" />
      <div className="flex-1">
        <div className="text-sm text-gray-500">{app.category}</div>
        <div className="text-base font-semibold text-black">{app.name}</div>
      </div>
      <button className="px-3 py-1 rounded-md bg-[#ff0000] text-white text-sm hover:brightness-95">
        Tải về
      </button>
    </div>
  );
}

export default function App() {
  const mainApps = mockApps.slice(0, 9);
  const topApps = mockApps.slice(9);

  return (
    <div className="min-h-screen bg-[#f4f4f4]">
      <Header />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <section className="lg:col-span-3 space-y-4">
            {mainApps.map((app, idx) => (
              <AppCard key={idx} app={app} />
            ))}
          </section>
          <aside className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow-sm p-4">
              <div className="font-semibold mb-3">Top Tải Về</div>
              <div className="space-y-3">
                {topApps.map((app, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <img src={app.icon} alt={app.name} className="w-10 h-10 rounded-md object-cover" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-black">{app.name}</div>
                      <div className="text-xs text-gray-500">{app.category}</div>
                    </div>
                    <button className="px-2 py-1 rounded bg-[#ff0000] text-white text-xs">Tải</button>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
