import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Dialog } from './Dialog/Dialog'
import { Modal } from './Modal/Modal'
import { BottomSheet } from './BottomSheet/BottomSheet'
import { SideDrawer } from './SideDrawer/SideDrawer'

/**
 * The overlay exit contract, on a phone: every modal overlay has
 *   (a) a visible close control,
 *   (b) backdrop tap where it has a backdrop,
 *   (c) a gesture — drag-to-dismiss for sheets, swipe-down for the lightbox —
 *   (d) a history entry, so Android back and the installed PWA's edge swipe
 *       close it instead of leaving the page.
 *
 * Two halves. The primitives are tested directly for (a), (b) and (d). Then
 * a source scan holds every component that renders `role="dialog"` to
 * building on one of those primitives, or names why it does not — because
 * the contract is only as good as the count of things that go through it,
 * and nine overlays used to go around it.
 *
 * (c) is pinned for sheets in BottomSheet.test.tsx and for the lightbox in
 * useSwipeNavigation.test.tsx; a full-height sheet deliberately has no drag
 * (its header is a sliver and a drag there is usually a scroll — see
 * BottomSheet.tsx), which is why it always has (a).
 */

const isMobile = vi.hoisted(() => ({ value: true }))
vi.mock('../../hooks/useMediaQuery', () => ({
  useIsMobile: () => isMobile.value,
  useIsTouch: () => isMobile.value,
}))

const sheetKey = () => (window.history.state as { igabSheet?: string } | null)?.igabSheet

describe('the overlay primitives on a phone', () => {
  beforeEach(() => {
    isMobile.value = true
    window.matchMedia ??= (() => ({ matches: false })) as unknown as typeof window.matchMedia
    // A dialog opened by a previous test leaves its entry behind and closes
    // this one on mount — drain it.
    window.history.replaceState(null, '', '/')
  })
  afterEach(() => {
    window.history.replaceState(null, '', '/')
  })

  it('Dialog: a titled sheet with a close button and a history entry', () => {
    const onClose = vi.fn()
    render(
      <Dialog title="Edit thing" onClose={onClose} historyKey="thing">
        body
      </Dialog>
    )
    expect(screen.getByRole('dialog', { name: 'Edit thing' })).toBeInTheDocument()
    expect(sheetKey()).toBe('thing')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('Dialog: the footer stays reachable — a Save button placed there is rendered', () => {
    render(
      <Dialog title="Form" onClose={() => {}} historyKey="form" footer={<button>Save</button>}>
        body
      </Dialog>
    )
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('BottomSheet: backdrop tap closes it, and it carries a history entry', () => {
    const onClose = vi.fn()
    const { container } = render(
      <BottomSheet open onClose={onClose} title="Pick" historyKey="pick">
        body
      </BottomSheet>
    )
    expect(sheetKey()).toBe('pick')
    fireEvent.click(container.ownerDocument.querySelector('.bottom-sheet-backdrop')!)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('Modal: a history entry, and Escape reaches it', () => {
    const onClose = vi.fn()
    render(
      <Modal onClose={onClose} historyKey="plain">
        <div role="dialog" aria-label="Plain">
          <button onClick={onClose}>Done</button>
        </div>
      </Modal>
    )
    expect(sheetKey()).toBe('plain')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('SideDrawer: a close button, a history entry, and Escape', () => {
    const onClose = vi.fn()
    render(
      <SideDrawer title="Attachments" onClose={onClose} historyKey="attachments">
        body
      </SideDrawer>
    )
    expect(screen.getByRole('dialog', { name: 'Attachments' })).toBeInTheDocument()
    expect(sheetKey()).toBe('attachments')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

/**
 * Components allowed to render `role="dialog"` without importing a
 * primitive — each with the reason. An entry without one is a bug hiding
 * behind a list.
 */
const OWN_DIALOG: Record<string, string> = {
  'components/common/Dialog/Dialog.tsx': 'the primitive',
  'components/common/Modal/Modal.tsx': 'the primitive',
  'components/common/BottomSheet/BottomSheet.tsx': 'the primitive',
  'components/common/SideDrawer/SideDrawer.tsx':
    'the docked-drawer primitive: close button, Escape via the stack, history entry; no backdrop by design',
  'components/common/InfoPopover/InfoPopover.tsx':
    'light-dismiss anchored popover: outside-tap closes it and it has an X',
  'components/budget/MoveMoneyPopover/MoveMoneyPopover.tsx':
    'light-dismiss anchored popover placed by useAnchoredPosition; a sheet on phones',
  'components/budget/AssignDropdown/AssignDropdown.tsx':
    'light-dismiss anchored menu placed by useAnchoredPosition; a sheet on phones',
}

const SRC = join(dirname(fileURLToPath(import.meta.url)), '../..')
const PRIMITIVE_IMPORT =
  /from '[./]*\/common\/(Dialog\/Dialog|BottomSheet\/BottomSheet|Modal\/Modal)'/

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return tsxFiles(full)
    return full.endsWith('.tsx') && !full.endsWith('.test.tsx') ? [full] : []
  })
}

describe('every dialog is built on a primitive', () => {
  const dialogs = tsxFiles(SRC)
    .filter((f) => readFileSync(f, 'utf8').includes('role="dialog"'))
    .map((f) => ({ file: relative(SRC, f), src: readFileSync(f, 'utf8') }))

  it('finds the overlays (a green run must mean something)', () => {
    expect(dialogs.length).toBeGreaterThanOrEqual(8)
    const users = tsxFiles(SRC).filter((f) => PRIMITIVE_IMPORT.test(readFileSync(f, 'utf8')))
    expect(users.length).toBeGreaterThanOrEqual(30)
  })

  it('names no hand-rolled dialog', () => {
    const strays = dialogs
      .filter((d) => !PRIMITIVE_IMPORT.test(d.src) && !(d.file in OWN_DIALOG))
      .map((d) => d.file)
    expect(
      strays,
      `${strays.join(', ')}: renders role="dialog" without Dialog / BottomSheet / Modal. ` +
        `Build on a primitive, or add it to OWN_DIALOG with the reason it satisfies the contract itself.`
    ).toEqual([])
  })

  it('keeps every exemption honest', () => {
    for (const [file, reason] of Object.entries(OWN_DIALOG)) {
      const d = dialogs.find((x) => x.file === file)
      expect(d, `${file} (${reason}) no longer renders a dialog — stale entry`).toBeDefined()
    }
  })
})
