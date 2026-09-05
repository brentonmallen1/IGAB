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
    // Same-origin /api in dev, mirroring production nginx: phones and other
    // LAN devices hit the Vite origin and get proxied to the backend, instead
    // of a baked-in localhost URL that only resolves on the dev machine.
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    // jsdom for component tests; pure-function suites run there unchanged
    environment: 'jsdom',
    setupFiles: ['./src/test-utils/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      include: ['src/**'],
      exclude: [
        'src/**/*.d.ts',
        'src/main.tsx',
        'src/test-utils/**',
        // Hand-written mirrors of server schemas — declarations, no behaviour.
        'src/types/**',
      ],
      // Thresholds are per-glob ON PURPOSE, and the split is the repo's own
      // architecture rather than a concession.
      //
      // CLAUDE.md puts the rules in pure modules and leaves the wiring in
      // components: "Logic that can only be exercised by mounting a component
      // will not get the tests that keep copies from re-appearing." So the
      // pure homes are held high, and a single global 90% is NOT the goal —
      // reaching it would mean thousands of mount-and-assert component tests,
      // which is the kind of suite that scores well and catches little.
      //
      // Every number here is a RATCHET set just under what the tree already
      // scores. Raise them when the real figure rises; never lower one to make
      // a red build green.
      thresholds: {
        // Cross-feature pure logic — `frontend/src/utils/` in the rule table.
        'src/utils/**': { statements: 85, branches: 85 },
        // Feature-local pure modules (reviewSection.ts, budgetTotals.ts, …),
        // colocated beside the .tsx they serve. The best-covered code here.
        'src/components/**/*.ts': { statements: 88, branches: 85 },
        'src/pages/**/*.ts': { statements: 85, branches: 80 },
        // Low, and the five hooks at 0% are why: useShortcut, usePinchZoom,
        // useSwipeNavigation, useCurrentPosition, useSyncAllAccounts. Raise
        // this as they get covered — it is the most reachable ratchet here.
        'src/hooks/**': { statements: 63, branches: 46 },
        // The floor for everything else — components, stores, api wrappers.
        // Honest about what is tested today, not a target. `include: src/**`
        // means a new untested file LOWERS this, which is the point: without
        // it the metric only counts files a test already imports, and adding
        // dead-untested code would leave the number flattering and unchanged.
        statements: 41,
        branches: 36,
      },
    },
  },
})
