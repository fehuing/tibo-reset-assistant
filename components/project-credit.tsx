'use client';

import { useState } from 'react';
import { Heart, Star, ArrowUpRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { siteConfig } from '@/lib/site-config';
import type { Locale } from '@/lib/i18n';

export function ProjectCredit({ locale }: { locale: Locale }) {
  const zh = locale === 'zh';
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState(0);
  const payment = [
    { title: zh ? '微信支付' : 'WeChat Pay', image: siteConfig.support.wechatPayCode },
    { title: zh ? '支付宝' : 'Alipay', image: siteConfig.support.alipayCode },
  ].filter(item => item.image);
  const supportReady = siteConfig.support.enabled && !!siteConfig.support.recipient.trim() && payment.length > 0;
  const selected = payment[method] ?? payment[0];
  return <>
    {siteConfig.douyin.qrCode && <aside className="mini-program-card paper-card" aria-labelledby="douyin-contact-title">
      <a className="mini-program-code" href={siteConfig.douyin.qrCode} target="_blank" rel="noopener noreferrer"><img src={siteConfig.douyin.qrCode} alt={zh ? '作者抖音二维码' : 'Author’s Douyin QR code'} width="660" height="660" loading="lazy" /></a>
      <div className="mini-program-copy"><p className="mini-program-label">{zh ? '关注抖音' : 'FOLLOW ON DOUYIN'}</p><h2 id="douyin-contact-title">{siteConfig.douyin.name}</h2><p>{zh ? '开发进展、更新记录和使用分享。' : 'Development updates and usage tips.'}</p></div>
    </aside>}
    <section className="project-credit paper-card" aria-labelledby="project-credit-title">
      <h2 id="project-credit-title">{zh ? '关于项目与作者' : 'About the project and author'}</h2>
      <p>{zh ? 'UI 视觉设计参考 ' : 'The UI visual design was inspired by '}<a href="https://codex-resets.com/" target="_blank" rel="noopener noreferrer">Codex Resets ↗</a>{zh ? '。本项目的页面业务、采集与服务逻辑为独立编写，未使用参考网站的源码。' : '. This project’s page logic, collector and backend were independently implemented without using the reference website’s source code.'}</p>
      <p className="support-note">{zh ? '业务代码按 MIT 开源。React、组件库等第三方依赖各自遵循其许可证；原始推文、头像和标识属于原权利人。' : 'Project code is open source under MIT. React and other third-party dependencies retain their own licenses; original posts, portraits and marks belong to their respective owners.'}</p>
      <p>{zh ? '如果这个项目对你有帮助，欢迎点个 Star、反馈问题或分享给朋友。' : 'If this project helps you, a star, bug report or share is appreciated.'}</p>
      <div className="project-links">
        <a className="press-button yellow" href="https://github.com/fehuing/tibo-reset-assistant" target="_blank" rel="noopener noreferrer"><Star size={17} /> GitHub</a>
        {siteConfig.wechatCode && <a className="press-button paper" href="#wechat">{zh ? '联系作者' : 'Contact author'} <ArrowUpRight size={16} /></a>}
        {siteConfig.douyin.url && <a className="press-button paper" href={siteConfig.douyin.url} target="_blank" rel="noopener noreferrer">{zh ? '关注抖音' : 'Douyin'} <ArrowUpRight size={16} /></a>}
        {supportReady && <Button className="press-button pink" onClick={() => setOpen(true)}><Heart size={17} />{zh ? '自愿支持作者' : 'Support the author'}</Button>}
      </div>
    </section>
    {supportReady && <Dialog open={open} onOpenChange={setOpen}><DialogContent className="support-dialog"><DialogHeader>
      <DialogTitle>{zh ? '自愿支持作者' : 'Support the author'}</DialogTitle>
      <DialogDescription>{zh ? '金额自选，完全自愿；不支付也可以完整使用开源功能。不承诺额度重置、优先采集或任何额外权益。' : 'Choose any amount, entirely voluntarily. All open-source features remain available without payment. Support does not promise quota resets, priority collection or extra benefits.'}</DialogDescription>
    </DialogHeader>
      <p>{zh ? '收款方：' : 'Recipient: '}{siteConfig.support.recipient}</p>
      <div className="support-options">{payment.map((item, index) => <Button key={item.title} variant="outline" aria-pressed={selected === item} onClick={() => setMethod(index)}>{item.title}</Button>)}</div>
      {selected && <a href={selected.image} target="_blank" rel="noopener noreferrer"><img className="support-code" src={selected.image} alt={(zh ? '收款码 · ' : 'Payment QR · ') + selected.title + ' · ' + siteConfig.support.recipient} /></a>}
      <p className="support-note">{zh ? '请在支付应用中核对收款方。本页只展示收款码，不读取支付结果或保存支付信息；联系二维码不是收款码。' : 'Confirm the recipient in your payment app. This page only displays a QR code; it does not read payment results or retain payment information. The contact QR is not a payment QR.'}</p>
    </DialogContent></Dialog>}
  </>;
}
