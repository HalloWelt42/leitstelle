import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// Entwicklung: Oberfläche auf 5530, Schnittstellen und Kanal vom Kern auf 8530
const kern = process.env.LEITSTELLE_KERN ?? 'http://127.0.0.1:8530';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5530,
    strictPort: true,
    proxy: {
      '/api/kanal': { target: kern, ws: true },
      '/api': kern,
      '/v1': kern,
      '/gesundheit': kern,
    },
  },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
