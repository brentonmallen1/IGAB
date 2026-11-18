import { describe, expect, it } from 'vitest'
import { guessFill } from './categoryGuessFill'

const fresh = { current: null, autoFilled: null, userChose: false }

describe('guessFill', () => {
  it('fills an empty field', () => {
    expect(guessFill(fresh, 'groceries')).toBe('groceries')
    expect(guessFill({ ...fresh, current: '' }, 'groceries')).toBe('groceries')
  })

  it('leaves an empty field empty when the server would too', () => {
    expect(guessFill(fresh, null)).toBeUndefined()
  })

  it('follows the guess while the field still holds the one it wrote', () => {
    const ours = { current: 'groceries', autoFilled: 'groceries', userChose: false }
    expect(guessFill(ours, 'membership')).toBe('membership')
    expect(guessFill(ours, 'groceries')).toBeUndefined()
    // Blank is what Save would file, so a blank guess clears our own fill.
    expect(guessFill(ours, null)).toBeNull()
  })

  it('never touches a category the person chose', () => {
    const chose = { current: 'fun', autoFilled: null, userChose: true }
    expect(guessFill(chose, 'groceries')).toBeUndefined()
    // "No category" picked on purpose is a choice too.
    expect(guessFill({ ...chose, current: null }, 'groceries')).toBeUndefined()
  })

  it("leaves a category the form was opened with (the row's own, a context add)", () => {
    expect(
      guessFill({ current: 'rent', autoFilled: null, userChose: false }, 'groceries')
    ).toBeUndefined()
    expect(
      guessFill({ current: 'rent', autoFilled: 'groceries', userChose: false }, 'groceries')
    ).toBeUndefined()
  })
})
