import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig } from 'vite';

// Optional hot reload: first run the local Python service on port 8080.
export default defineConfig({
  css: { postcss: { plugins: [tailwindcss()] } },
  plugins: [vinext()],
  server: { host: '127.0.0.1', port: 4175, strictPort: true, proxy: {
    '^/(radar/)?(api/|data\\.json|post-images/)': 'http://127.0.0.1:8080',
  } },
});
