import zhExcerpts from './excerpts.zh.json';

export type Locale = 'zh' | 'en';

const zh = {
  skip: '跳到最新状态', brand: 'Tibo重置助手', brandTag: 'CODEX 重置追踪', home: 'Tibo重置助手首页', navigation: '页面导航', historyNav: '重置记录',
  switchLanguage: 'Switch to English', languageButton: 'EN', lightMode: '切换浅色模式', darkMode: '切换深色模式',
  introKicker: 'TIBO 发动态，我们记下来。', headline: '额度重置了', headlineQuestion: '吗？', introBefore: '追踪 ', introAfter: ' 的 Codex 重置公告。',
  latest: '最近一次重置公告', disconnected: '未连接', reading: '读取中', delayed: '更新待恢复', tracking: '追踪中',
  just: '刚刚', justDetail: '刚刚发布了新的重置公告', minutesAgo: '分钟前', hoursAgo: '小时前', daysAgo: '天前', announcedAt: '公告发布于 {time}', hoursSince: '距公告发布已过 {hours} 小时 {minutes} 分钟', daysSince: '距公告发布已过 {days} 天 {hours} 小时',
  good: '好', news: '消息！', reset: '重置公告', regular: '直接重置', banked: '存储重置卡', beijing: '北京时间', viewOriginal: '查看原始公告',
  reactionThanks: '感谢', reactionBeg: '求重置', reactionThanksAria: '感谢这次重置', reactionBegAria: '请求一次重置', reactionUnavailable: '公共互动计数暂不可用', reactionCount: '本轮已有 {count} 次互动',
  loadingTitle: '正在读取最新重置记录', failedTitle: '暂时连不上数据源', loadingText: '每一次好消息，都值得记下来。', failedText: '稍后再试，确认后的记录会显示在这里。', checkedAt: '检查于 {time}', waitingFirst: '等待首次成功更新', checking: '检查中', checkUpdates: '检查更新', staleCached: '当前显示上次成功取得的记录。数据暂未更新，不代表没有新公告。', unavailable: '数据暂时不可用，请点击“检查更新”重试。', sourceDirect: 'X 公开动态直采', sourceFallback: '备用接口',
  statsAria: '历史统计', total: '累计重置', totalUnit: '次', totalCaption: '被记录的好消息', average: '平均间隔', daysUnit: '天', averageCaption: '按已有公告计算', longest: '最长间隔', longestCaption: '耐心也有了刻度',
  logKicker: '重置记录', logTitle: '每一次，都有记录', announcementCount: '{count} 条公告', all: '全部公告', emptyFilter: '暂时没有这一类公告。', recordsLoading: '记录加载后将在这里显示。', bankedHeadline: '把重置机会，留到需要的时候。', regularHeadline: '新的额度，继续写点好东西。', observed: '公开观察记录', author: '@thsottiaux', translationExcerpt: '中文译文', originalExcerpt: '英文原文', translationPending: '英文原文 · 译文待补', relatedOriginal: '查看关联原文', fullOriginal: '查看英文原文', loadSix: '再看 6 条', shown: '已显示 {shown} / {total} 条',
  aboutTitle: '好消息，我们一起等。', aboutText: '这里追踪公开公告，不读取你的个人账号额度。', copy: '分享助手', copied: '链接已复制', copySuccess: '链接已复制，可以分享给朋友了。', copyFailure: '浏览器未允许复制，你可以直接复制地址栏链接。',
  footerBrand: 'Tibo重置助手', footerTag: '重置 · 创作 · 再继续', sourceBefore: '主要监控 ', sourceAfter: ' 的公开动态。公告原文归原作者所有。独立制作，与 OpenAI 无隶属关系。', footerNote: '直接重置与存储重置卡不同，适用范围请查看对应公告。', backTop: '回到顶部',
  calendarTitle: 'Codex 重置历史', lastWeeks: '最近 26 周 · 北京时间', noRecord: '无记录', calendarRegion: '最近 26 周的重置日历，可横向滚动', loadingRecords: '记录加载中', noResetDay: '没有重置记录', clickOriginal: '，点击查看原文', observedNote: ' · 观察记录', noResetSentence: '这一天没有记录到重置公告。',
  documentTitle: 'Tibo重置助手 · Codex 重置公告追踪', documentDescription: '追踪 Tibo 的 Codex 重置公告，查看最新重置时间、存储重置卡、历史日历与原始消息。',
  postScreenshot: 'X 原页面截图', postScreenshotAlt: 'Tibo 的 X 推文页面截图', postEnlarge: '查看完整截图', postOpenImage: '打开原图', postClose: '关闭截图', postCaptured: '截图保存于 {time} · 北京时间',
  postTextAndTranslation: '正文 / 翻译', postFullOriginal: '英文全文', postFullTranslation: '中文全文翻译', postCapturedText: '已采集正文 · 完整性待核验', postTranslationPending: '中文全文翻译待补，下面保留英文正文。', postImageUnavailable: '截图暂时无法加载，已保留文字。', postArchiveNote: '截图和文字为采集时保存的内容。后续编辑、回复及互动数请查看 X 原页面。',
  miniProgramNav: '小程序', miniProgramLabel: '微信小程序', miniProgramCodeAlt: 'Tibo重置助手微信小程序码', miniProgramEnlarge: '查看小程序码大图',
  miniProgramScan: '微信扫一扫，查看重置公告和历史记录。', miniProgramSearch: '也可以在微信搜一搜：',
  wechatContactLabel: '添加微信', wechatContactCodeAlt: '微信好友二维码', wechatContactEnlarge: '查看微信二维码大图', wechatContactScan: '微信扫一扫，添加好友交流。',
} as const;

type MessageKey = keyof typeof zh;
const en: Record<MessageKey, string> = {
  skip: 'Skip to latest status', brand: 'Tibo重置助手', brandTag: 'CODEX RESET RADAR', home: 'Tibo重置助手 home', navigation: 'Page navigation', historyNav: 'Reset history',
  switchLanguage: '切换为中文', languageButton: '中文', lightMode: 'Switch to light mode', darkMode: 'Switch to dark mode',
  introKicker: 'TIBO POSTS. WE KEEP THE RECEIPTS.', headline: 'Limits reset', headlineQuestion: 'yet?', introBefore: 'Tracking Codex reset announcements from ', introAfter: '.',
  latest: 'Latest reset announcement', disconnected: 'Offline', reading: 'Loading', delayed: 'Update delayed', tracking: 'Tracking',
  just: 'Just', justDetail: 'A new reset announcement was just posted', minutesAgo: 'minutes ago', hoursAgo: 'hours ago', daysAgo: 'days ago', announcedAt: 'Announced at {time}', hoursSince: '{hours}h {minutes}m since the announcement', daysSince: '{days}d {hours}h since the announcement',
  good: 'GOOD', news: 'NEWS!', reset: 'Reset announcement', regular: 'Regular reset', banked: 'Banked reset', beijing: 'Beijing time', viewOriginal: 'View original post',
  reactionThanks: 'thanks', reactionBeg: 'reset pls', reactionThanksAria: 'Say thanks for this reset', reactionBegAria: 'Ask for another reset', reactionUnavailable: 'Public reaction count unavailable', reactionCount: '{count} reactions in this cycle',
  loadingTitle: 'Loading the latest reset record', failedTitle: 'The data source is temporarily unavailable', loadingText: 'Every bit of good news deserves a record.', failedText: 'Try again later. Confirmed records will appear here.', checkedAt: 'Checked {time}', waitingFirst: 'Waiting for the first successful update', checking: 'Checking', checkUpdates: 'Check updates', staleCached: 'Showing the last successful record. The feed is delayed; this does not mean there are no new announcements.', unavailable: 'Data is temporarily unavailable. Select “Check updates” to retry.', sourceDirect: 'Direct public X feed', sourceFallback: 'Fallback feed',
  statsAria: 'Historical statistics', total: 'Total resets', totalUnit: '', totalCaption: 'Good news on record', average: 'Average wait', daysUnit: 'days', averageCaption: 'Calculated from existing announcements', longest: 'Longest wait', longestCaption: 'Patience, measured',
  logKicker: 'THE RESET LOG', logTitle: 'Every reset, on record', announcementCount: '{count} announcements', all: 'All announcements', emptyFilter: 'No announcements in this category yet.', recordsLoading: 'Records will appear here after loading.', bankedHeadline: 'Save the reset for when you need it.', regularHeadline: 'Fresh limits. Keep building.', observed: 'Public observation', author: '@thsottiaux', translationExcerpt: 'Chinese translation', originalExcerpt: 'Original excerpt', translationPending: 'Original English · Translation pending', relatedOriginal: 'View related post', fullOriginal: 'View full post', loadSix: 'Show 6 more', shown: 'Showing {shown} / {total}',
  aboutTitle: 'We wait for good news together.', aboutText: 'This site tracks public announcements. It cannot read your personal usage limits.', copy: 'Share assistant', copied: 'Link copied', copySuccess: 'Link copied. Ready to share.', copyFailure: 'Copy was blocked by the browser. Copy the address-bar link instead.',
  footerBrand: 'Tibo重置助手', footerTag: 'RESET. BUILD. REPEAT.', sourceBefore: 'Primary monitoring reads public posts from ', sourceAfter: '. Original posts belong to their author. Independently built and not affiliated with OpenAI.', footerNote: 'Regular and banked resets work differently. Check the corresponding announcement for scope.', backTop: 'Back to top',
  calendarTitle: 'Codex reset history', lastWeeks: 'Last 26 weeks · Beijing time', noRecord: 'No reset', calendarRegion: 'Reset calendar for the last 26 weeks; scroll horizontally', loadingRecords: 'Records loading', noResetDay: 'No reset recorded', clickOriginal: ', select to view the original post', observedNote: ' · Observed', noResetSentence: 'No reset announcement was recorded on this day.',
  documentTitle: 'Tibo重置助手 · Codex reset announcement tracker', documentDescription: 'Track Tibo’s Codex reset announcements, including the latest reset, banked resets, history, and original posts.',
  postScreenshot: 'Original X page capture', postScreenshotAlt: 'Captured X post by Tibo', postEnlarge: 'View full capture', postOpenImage: 'Open original image', postClose: 'Close image', postCaptured: 'Captured {time} · Beijing time',
  postTextAndTranslation: 'Text / Translation', postFullOriginal: 'Full original text', postFullTranslation: 'Full Chinese translation', postCapturedText: 'Captured text · Completeness unverified', postTranslationPending: 'Full Chinese translation is pending. The English text is preserved below.', postImageUnavailable: 'Image unavailable. The text is still available.', postArchiveNote: 'Text and images are saved at capture time. Visit X for later edits, replies and current engagement counts.',
  miniProgramNav: 'WeChat', miniProgramLabel: 'WECHAT MINI PROGRAM', miniProgramCodeAlt: 'WeChat Mini Program code for Tibo重置助手', miniProgramEnlarge: 'View larger code',
  miniProgramScan: 'Scan with WeChat to view reset announcements and history.', miniProgramSearch: 'Or search in WeChat for: ',
  wechatContactLabel: 'WECHAT CONTACT', wechatContactCodeAlt: 'WeChat contact QR code', wechatContactEnlarge: 'View larger WeChat QR code', wechatContactScan: 'Scan with WeChat to add as a friend.',
};

export const messages: Record<Locale, Record<MessageKey, string>> = { zh, en };

export function text(locale: Locale, key: MessageKey, values: Record<string, string | number> = {}) {
  return messages[locale][key].replace(/\{(\w+)\}/g, (match, name) => values[name] === undefined ? match : String(values[name]));
}

export function formatStamp(value: string, locale: Locale, short = false) {
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-GB', {
    timeZone: 'Asia/Shanghai', year: short ? undefined : 'numeric', month: locale === 'zh' ? '2-digit' : 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(new Date(value));
}

export function formatElapsed(value: string, now: number, locale: Locale) {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60000));
  if (minutes < 1) return { value: text(locale, 'just'), unit: locale === 'en' ? 'now' : '', detail: text(locale, 'justDetail') };
  if (minutes < 60) return { value: String(minutes), unit: text(locale, 'minutesAgo'), detail: text(locale, 'announcedAt', { time: formatStamp(value, locale) }) };
  if (minutes < 1440) return { value: String(Math.floor(minutes / 60)), unit: text(locale, 'hoursAgo'), detail: text(locale, 'hoursSince', { hours: Math.floor(minutes / 60), minutes: minutes % 60 }) };
  return { value: String(Math.floor(minutes / 1440)), unit: text(locale, 'daysAgo'), detail: text(locale, 'daysSince', { days: Math.floor(minutes / 1440), hours: Math.floor(minutes % 1440 / 60) }) };
}

export function resetLabel(locale: Locale, kind: string) {
  return text(locale, kind === 'regular' ? 'regular' : kind === 'banked' ? 'banked' : 'reset');
}

export function localizedExcerpt(locale: Locale, id: string, original: string) {
  const translation = (zhExcerpts as Record<string, string>)[id];
  return { value: locale === 'zh' && translation ? translation : original, translated: locale === 'zh' && !!translation };
}
