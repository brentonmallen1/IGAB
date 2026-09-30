import { fireEvent, screen } from '@testing-library/react'

type Part = 'category' | 'amount' | 'memo'

const LABEL: Record<Part | 'remove', (n: number) => string> = {
  category: (n) => `Split ${n} category`,
  amount: (n) => `Split ${n} amount`,
  memo: (n) => `Split ${n} memo`,
  remove: (n) => `Remove split ${n}`,
}

/**
 * A field of split line `n` (1-based) in the phone's SplitSheet, opening the
 * line first when it is folded. The sheet shows one line's fields at a time,
 * so a test that fills several lines goes through here rather than asking
 * for a label that only exists while its line is open.
 */
export function splitField<T extends HTMLElement = HTMLInputElement>(
  n: number,
  part: Part | 'remove'
): T {
  const label = LABEL[part](n)
  if (!screen.queryByLabelText(label)) {
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Split ${n}: `) }))
  }
  return screen.getByLabelText<T>(label)
}

/** The split's lines, folded or open — one list item each. */
export const splitLines = () => Array.from(document.querySelectorAll('.split-sheet__legs > li'))
