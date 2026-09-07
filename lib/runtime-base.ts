export function runtimeBase(pathname?: string) {
  const current = pathname ?? (typeof window === 'undefined' ? '/radar/' : window.location.pathname);
  return current === '/' || current === '/index.html' ? '' : '/radar';
}
