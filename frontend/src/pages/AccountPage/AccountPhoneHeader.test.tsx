import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AccountPhoneHeader } from './AccountPhoneHeader'
import type { AccountNotice } from './accountNotices'

const money = (n: number) => `$${n.toFixed(2)}`

const dupes: AccountNotice = {
  kind: 'duplicates',
  tone: 'warning',
  title: '2 possible duplicates',
  detail: 'They may match transactions you entered by hand.',
}
const rows: AccountNotice = {
  kind: 'review',
  tone: 'info',
  title: '15 transactions to review',
  detail: '15 to approve',
}

function renderHeader(notices: AccountNotice[] = [], primary = { label: 'Reconcile' }) {
  const handlers = { onClick: vi.fn(), onOpenTools: vi.fn(), onOpenNotices: vi.fn() }
  render(
    <AccountPhoneHeader
      balance={6193.41}
      formatMoney={money}
      notices={notices}
      primary={{ label: primary.label, onClick: handlers.onClick }}
      onOpenTools={handlers.onOpenTools}
      onOpenNotices={handlers.onOpenNotices}
    />
  )
  return handlers
}

describe('AccountPhoneHeader', () => {
  it('shows the working balance once, and it opens Tools', () => {
    const { onOpenTools } = renderHeader()
    expect(screen.getAllByText('$6193.41')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /Working balance \$6193\.41/ }))
    expect(onOpenTools).toHaveBeenCalledOnce()
  })

  it('draws no pill when nothing is waiting', () => {
    renderHeader()
    expect(screen.queryByRole('button', { name: /need/ })).toBeNull()
  })

  // One pill for everything, not a chip per kind: the chips were the clunky
  // part of the first design.
  it('draws one pill for everything waiting, named for what it counts', () => {
    const { onOpenNotices } = renderHeader([dupes, rows])
    const pill = screen.getByRole('button', {
      name: '2 things need a look: 2 possible duplicates, 15 transactions to review',
    })
    expect(pill).toHaveTextContent('2')
    expect(pill).toHaveClass('account-phone-header__notice--warning')
    fireEvent.click(pill)
    expect(onOpenNotices).toHaveBeenCalledOnce()
  })

  it('is the calm colour when only rows to approve are waiting', () => {
    renderHeader([rows])
    expect(screen.getByRole('button', { name: /1 thing needs a look/ })).toHaveClass(
      'account-phone-header__notice--info'
    )
  })

  it('runs the account’s main action and opens Tools from its button', () => {
    const { onClick, onOpenTools } = renderHeader([], { label: 'Pay' })
    fireEvent.click(screen.getByRole('button', { name: 'Pay' }))
    expect(onClick).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Account tools' }))
    expect(onOpenTools).toHaveBeenCalledOnce()
  })
})
