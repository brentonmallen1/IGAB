import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ContextMenu, type ContextMenuItem } from './ContextMenu'

/**
 * The filter exists because a menu's length can be the user's data rather
 * than the app's design: "Move to group" lists every category group a budget
 * has, and scrolling forty of them to find one is not finding it.
 */

const GROUPS: ContextMenuItem[] = [
  'Housing',
  'Utilities',
  'Groceries',
  'Transport',
  'Insurance',
  'Subscriptions',
  'Giving',
  'Travel',
  'Home upkeep',
].map((label) => ({ id: label.toLowerCase(), label }))

function open(items = GROUPS, props: Partial<Parameters<typeof ContextMenu>[0]> = {}) {
  const onSelect = vi.fn()
  const onClose = vi.fn()
  render(
    <ContextMenu
      items={items}
      onSelect={onSelect}
      onClose={onClose}
      anchor={{ x: 100, y: 100 }}
      searchable
      searchPlaceholder="Search groups…"
      {...props}
    />
  )
  return { onSelect, onClose }
}

const names = () => screen.getAllByRole('menuitem').map((b) => b.textContent)

describe('ContextMenu search', () => {
  it('narrows the list as you type', async () => {
    open()
    await userEvent.type(screen.getByLabelText('Search groups…'), 'ins')
    expect(names()).toEqual(['Insurance'])
  })

  it('matches anywhere in the label, not just the start', async () => {
    open()
    await userEvent.type(screen.getByLabelText('Search groups…'), 'keep')
    expect(names()).toEqual(['Home upkeep'])
  })

  it('ignores case', async () => {
    open()
    await userEvent.type(screen.getByLabelText('Search groups…'), 'TRAV')
    expect(names()).toEqual(['Travel'])
  })

  it('says so when nothing matches, rather than showing an empty box', async () => {
    open()
    await userEvent.type(screen.getByLabelText('Search groups…'), 'zzz')
    expect(screen.queryAllByRole('menuitem')).toHaveLength(0)
    expect(screen.getByText('Nothing by that name')).toBeInTheDocument()
  })

  it('takes the only match on Enter', async () => {
    const { onSelect, onClose } = open()
    await userEvent.type(screen.getByLabelText('Search groups…'), 'ins{Enter}')
    expect(onSelect).toHaveBeenCalledWith('insurance')
    expect(onClose).toHaveBeenCalled()
  })

  it('does nothing on Enter when nothing matches', async () => {
    const { onSelect } = open()
    await userEvent.type(screen.getByLabelText('Search groups…'), 'zzz{Enter}')
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('leaves a short menu alone', () => {
    // A filter over five things costs more attention than it saves, so asking
    // for one on a short menu is quietly ignored.
    open(GROUPS.slice(0, 5))
    expect(screen.queryByLabelText('Search groups…')).toBeNull()
    expect(names()).toHaveLength(5)
  })

  it('offers no filter unless asked, however long the menu', () => {
    open(GROUPS, { searchable: false })
    expect(screen.queryByLabelText('Search groups…')).toBeNull()
    expect(names()).toHaveLength(GROUPS.length)
  })

  it('drops separators once filtering starts', async () => {
    // They group a list nobody is reading any more.
    const withRule = [
      ...GROUPS.slice(0, 4),
      { id: 'sep', label: '', separator: true },
      ...GROUPS.slice(4),
    ]
    // The menu portals to <body>, so that is where the rule is.
    const separators = () => document.body.querySelectorAll('.context-menu__separator')
    open(withRule)
    expect(separators()).toHaveLength(1)

    await userEvent.type(screen.getByLabelText('Search groups…'), 'trav')
    expect(names()).toEqual(['Travel'])
    expect(separators()).toHaveLength(0)
  })
})
