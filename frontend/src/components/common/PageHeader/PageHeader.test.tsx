import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PAGE_HEADER_SLOT_ID, PageHeader } from './PageHeader'

const isMobile = vi.hoisted(() => ({ value: false }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsMobile: () => isMobile.value,
  useIsTouch: () => isMobile.value,
}))

function renderAt(path: string, ui: React.ReactElement, withSlot: boolean) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      {withSlot && <div id={PAGE_HEADER_SLOT_ID} data-testid="slot" />}
      <main data-testid="page">{ui}</main>
    </MemoryRouter>
  )
}

describe('PageHeader on a desktop', () => {
  beforeEach(() => {
    isMobile.value = false
  })

  it('is a band in the page: title, meta, subtitle, actions', () => {
    renderAt(
      '/accounts',
      <PageHeader
        title="Accounts"
        meta={<span>3 accounts</span>}
        subtitle="All of them"
        actions={<button>Add</button>}
      />,
      true
    )
    const page = screen.getByTestId('page')
    expect(page.querySelector('h1')?.textContent).toBe('Accounts')
    expect(page.textContent).toContain('3 accounts')
    expect(page.textContent).toContain('All of them')
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
    expect(screen.getByTestId('slot').childElementCount).toBe(0)
  })

  it('shows a back link derived from the route on a drill-in page', () => {
    renderAt('/accounts/acc-1', <PageHeader title="Checking" back />, true)
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/accounts')
  })
})

describe('PageHeader on a phone', () => {
  beforeEach(() => {
    isMobile.value = true
  })

  it('moves the title and back chevron into the app header slot', async () => {
    renderAt('/accounts/acc-1', <PageHeader title="Checking" back />, true)
    const slot = screen.getByTestId('slot')
    // The slot is found on the next frame, so the first paint is the band.
    await waitFor(() => expect(slot.querySelector('h1')?.textContent).toBe('Checking'))
    expect(slot.querySelector('a')).toHaveAttribute('href', '/accounts')
    // Nothing else to say, so the page spends no band at all.
    expect(screen.getByTestId('page').querySelector('.page-header')).toBeNull()
  })

  it('keeps only the actions in the page band', async () => {
    renderAt('/accounts', <PageHeader title="Accounts" actions={<button>Add</button>} />, true)
    await waitFor(() =>
      expect(screen.getByTestId('slot').querySelector('h1')?.textContent).toBe('Accounts')
    )
    const band = screen.getByTestId('page').querySelector('.page-header')
    expect(band).not.toBeNull()
    expect(band!.querySelector('h1')).toBeNull()
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
  })

  it('falls back to the in-page band where there is no slot (outside the shell)', () => {
    renderAt(
      '/system',
      <PageHeader title="System" back={{ to: '/settings', label: 'Settings' }} />,
      false
    )
    const page = screen.getByTestId('page')
    expect(page.querySelector('h1')?.textContent).toBe('System')
    expect(screen.getByRole('link', { name: /Settings/ })).toHaveAttribute('href', '/settings')
  })
})
