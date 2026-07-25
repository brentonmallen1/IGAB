/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // 'prompt': never silently reload a money app out from under the user;
      // UpdateToast surfaces the refresh instead.
      registerType: 'prompt',
      includeAssets: ['favicon.svg', 'favicon.ico', 'apple-touch-icon-180x180.png'],
      manifest: {
        name: "IGAB — I've Got A Budget",
        short_name: 'IGAB',
        description: 'Self-hosted envelope budgeting for your household',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        // Static bootstrap values from the default dark theme; themeColor.ts
        // keeps the live meta tag in sync with the active theme at runtime.
        background_color: '#0f1117',
        theme_color: '#13161f',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallback: '/index.html',
        // API responses are never served by the SW — the app is network-required.
        navigateFallbackDenylist: [/^\/api\//],
        // recharts chunk exceeds workbox's 2 MiB precache default
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  test: {
    environment: 'node',
  },
})
