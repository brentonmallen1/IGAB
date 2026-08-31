/**
 * Keeps the <meta name="theme-color"> tag in sync with the active theme so the
 * browser/OS chrome (status bar in installed PWA, tab bar on mobile) matches
 * the app header. Reads the computed value inside a rAF so the data-theme
 * attribute change has been applied before we sample it.
 */
export function syncThemeColorMeta(): void {
  requestAnimationFrame(() => {
    const value = getComputedStyle(document.documentElement).getPropertyValue('--header-bg').trim()
    if (!value) return
    let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'theme-color'
      document.head.appendChild(meta)
    }
    meta.content = value
  })
}
