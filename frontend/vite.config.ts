import { readFileSync } from 'node:fs';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';
import { MARKE, marke } from './marke';

// Entwicklung: Oberfläche auf 5530, Schnittstellen und Kanal vom Kern auf 8530
const kern = process.env.LEITSTELLE_KERN ?? 'http://127.0.0.1:8530';

// Fassung der gebauten Oberfläche aus der einzigen Quelle; weicht die des Kerns ab, lädt die Oberfläche neu (lib/fassung.svelte.ts)
const FASSUNG = (JSON.parse(readFileSync(new URL('../version.json', import.meta.url), 'utf-8')) as { version: string }).version;

export default defineConfig({
  plugins: [svelte(), marke()],
  define: { __FASSUNG__: JSON.stringify(FASSUNG), __MARKE__: JSON.stringify(MARKE) },
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
