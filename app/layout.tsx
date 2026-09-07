import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(process.env.PUBLIC_SITE_URL || 'http://localhost:8080/'),
  title: 'Tibo重置助手 · Codex 重置公告追踪',
  description: '中英文追踪 Tibo 的 Codex 重置公告、最新重置时间、存储重置卡、历史日历与原始消息。',
  openGraph: { type: 'website', url: '/', title: 'Tibo重置助手', description: '追踪 Codex 重置公告 · 原文截图 · 中文阅读 · 历史记录', images: [{ url: '/radar/share-cover.jpg', width: 1200, height: 630, alt: 'Tibo重置助手 · 追踪 Codex 重置公告' }] },
  twitter: { card: 'summary_large_image', title: 'Tibo重置助手', description: '追踪 Codex 重置公告', images: ['/radar/share-cover.jpg'] },
  icons: {
    icon: [{ url: '/radar/tibo-favicon.png', type: 'image/png', sizes: '64x64' }],
    apple: '/radar/tibo-avatar.jpg',
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
