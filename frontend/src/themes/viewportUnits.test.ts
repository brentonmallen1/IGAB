import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { stripComments } from '../test-utils/cssRules'

/**
 * No stylesheet sizes anything in vh.
 *
 * vh, dvh and svh all describe a viewport the app does not use: none of
 * them shrinks for the on-screen keyboard on iOS, and in the installed PWA
 * every one comes back short by the status bar (see --app-h in base.css).
 * Six panels were 80vh/84vh/85vh and opened under the keyboard; five gaps
 * were 8vh/12vh/15vh. Everything derives from --app-h now — --panel-max-h
 * for a panel's height, --modal-top-gap for where one begins — and the
 * only vh left is the fallback --vvh reads before the hook has measured.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

const ALLOWED: Record<string, string> = {
  'themes/base.css': 'the --vvh fallback: what desktop, jsdom and the first paint see',
  'components/common/ErrorBoundary/ErrorBoundary.css':
    'renders outside the app, before the hook that publishes --app-h has mounted',
}

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return cssFiles(full)
    return full.endsWith('.css') ? [full] : []
  })
}

describe('viewport height units', () => {
  const uses = cssFiles(SRC)
    .map((f) => ({
      file: relative(SRC, f),
      hits: [...stripComments(readFileSync(f, 'utf8')).matchAll(/\d+(?:\.\d+)?[dsl]?vh\b/g)].map(
        (m) => m[0]
      ),
    }))
    .filter((u) => u.hits.length > 0)

  it('appear only where allowed', () => {
    const strays = uses
      .filter((u) => !(u.file in ALLOWED))
      .map((u) => `${u.file}: ${u.hits.join(', ')}`)
    expect(
      strays,
      `${strays.join('\n')}\nSize from --app-h (--panel-max-h, --modal-top-gap, or a calc() of it).`
    ).toEqual([])
  })

  it('keeps every allowance honest', () => {
    for (const file of Object.keys(ALLOWED)) {
      expect(
        uses.some((u) => u.file === file),
        `${file}: ${ALLOWED[file]} — stale entry`
      ).toBe(true)
    }
  })
})
