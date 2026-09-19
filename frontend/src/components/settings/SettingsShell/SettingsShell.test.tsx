/**
 * One section at a time.
 *
 * The shell used to scroll every section in one column; now the address
 * names one and the shell shows only it. What has to hold: a bare path on
 * a desktop opens the first section rather than an empty column, the old
 * `#hash` addresses still land, a phone gets the list first, the search
 * narrows the nav, and a section that is named but not visible does not get
 * bounced away before it can become visible.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { visibleSettingsSections } from '../../../pages/SettingsPage/settingsSections'
import { SettingsShell } from './SettingsShell'

const mobile = vi.hoisted(() => ({ value: false }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsMobile: () => mobile.value,
}))

const sections = visibleSettingsSections({ budgetId: 'b1', isAdmin: false, page: 'settings' })

function Where() {
  const { pathname } = useLocation()
  return <output data-testid="where">{pathname}</output>
}

function renderShell(path: string, visible = sections) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/settings/:section?"
          element={
            <>
              <SettingsShell
                page="settings"
                sections={visible}
                navLabel="Settings sections"
                hints={{ appearance: 'Nord', 'api-keys': '2 keys' }}
                panels={{
                  appearance: { body: <div>appearance body</div> },
                  budget: { body: <div>budget body</div>, actions: <button>Rename</button> },
                  account: { body: <div>account body</div> },
                }}
              />
              <Where />
            </>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mobile.value = false
})

describe('on a desktop', () => {
  it('shows only the section the address names', () => {
    renderShell('/settings/budget')
    expect(screen.getByRole('heading', { level: 1, name: 'Budget' })).toBeInTheDocument()
    expect(screen.getByText('budget body')).toBeInTheDocument()
    expect(screen.queryByText('appearance body')).not.toBeInTheDocument()
  })

  it('says what the section is for, under its title', () => {
    renderShell('/settings/budget')
    expect(screen.getByText(/The budget you have open/)).toBeInTheDocument()
  })

  it('opens the first section for a bare path', () => {
    renderShell('/settings')
    expect(screen.getByTestId('where')).toHaveTextContent('/settings/appearance')
    expect(screen.getByText('appearance body')).toBeInTheDocument()
  })

  it('still lands the old #hash addresses', () => {
    // The palette, the budget picker and anything bookmarked spelled them.
    renderShell('/settings#budget')
    expect(screen.getByTestId('where')).toHaveTextContent('/settings/budget')
  })

  it('does not bounce a named section that is not visible yet', () => {
    // Admin sections arrive after /auth/me resolves; forwarding a deep link
    // away in the meantime would lose it.
    renderShell(
      '/settings/tags',
      sections.filter((s) => s.id !== 'tags')
    )
    expect(screen.getByTestId('where')).toHaveTextContent('/settings/tags')
    expect(screen.getByText(/There is no “tags” here/)).toBeInTheDocument()
  })

  it('groups the nav and carries a fact per section', () => {
    renderShell('/settings/budget')
    expect(screen.getByText('Personal')).toBeInTheDocument()
    expect(screen.getByText('This budget')).toBeInTheDocument()
    expect(screen.getByText('Data & access')).toBeInTheDocument()
    expect(screen.getByText('Nord')).toBeInTheDocument()
    expect(screen.getByText('2 keys')).toBeInTheDocument()
  })

  it('puts a section’s action beside its title', () => {
    renderShell('/settings/budget')
    expect(screen.getByRole('button', { name: 'Rename' })).toBeInTheDocument()
  })

  it('links to the neighbours at the foot', async () => {
    renderShell('/settings/budget')
    const pager = screen.getByRole('navigation', { name: 'Neighbouring sections' })
    expect(within(pager).getByRole('link', { name: 'Account' })).toBeInTheDocument()
    await userEvent.click(within(pager).getByRole('link', { name: 'Accounts' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/settings/accounts')
  })

  it('narrows the nav by search, and Enter opens the first match', async () => {
    renderShell('/settings/budget')
    const search = screen.getByRole('searchbox')
    await userEvent.type(search, 'snapshot')
    expect(screen.getByRole('link', { name: /Budget Backups/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Appearance/ })).not.toBeInTheDocument()
    await userEvent.type(search, '{Enter}')
    expect(screen.getByTestId('where')).toHaveTextContent('/settings/budget-backups')
  })
})

describe('navHeader', () => {
  it("renders above the search box when given one — System's way back", () => {
    render(
      <MemoryRouter initialEntries={['/settings/budget']}>
        <Routes>
          <Route
            path="/settings/:section?"
            element={
              <SettingsShell
                page="settings"
                sections={sections}
                navLabel="Settings sections"
                navHeader={<a href="/system">‹ Budget settings</a>}
                panels={{ budget: { body: <div>budget body</div> } }}
              />
            }
          />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByRole('link', { name: /Budget settings/ })).toBeInTheDocument()
  })

  it('is absent when nothing is passed — Settings has no page-level banner', () => {
    renderShell('/settings/budget')
    expect(screen.queryByText(/Budget settings/)).not.toBeInTheDocument()
  })
})

describe('on a phone', () => {
  beforeEach(() => {
    mobile.value = true
  })

  it('a bare path is the list, not a redirect', () => {
    renderShell('/settings')
    expect(screen.getByTestId('where')).toHaveTextContent('/settings')
    expect(screen.getByRole('link', { name: 'Budget' })).toBeInTheDocument()
    expect(screen.queryByText('appearance body')).not.toBeInTheDocument()
  })

  it('a section is the screen after it, with a way back', () => {
    renderShell('/settings/account')
    expect(screen.getByText('account body')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Settings/ })).toHaveAttribute('href', '/settings')
  })
})
