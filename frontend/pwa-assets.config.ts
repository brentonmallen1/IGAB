import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config'

// Derives all PWA icons mechanically from the existing brand mark (favicon.svg).
// Maskable/apple variants get the dark theme --bg-primary as background since
// those formats require an opaque, padded canvas. Run: npm run generate-pwa-assets
export default defineConfig({
  preset: {
    ...minimal2023Preset,
    maskable: {
      ...minimal2023Preset.maskable,
      resizeOptions: { background: '#0f1117' },
    },
    apple: {
      ...minimal2023Preset.apple,
      resizeOptions: { background: '#0f1117' },
    },
  },
  images: ['public/favicon.svg'],
})
