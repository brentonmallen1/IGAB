import { create } from 'zustand'
import { randomUUID } from '../utils/uuid'
import { canRemoveSplitLine } from '../utils/splits'
import { toAmountInput } from '../utils/amountExpression'

export type EditableField =
  | 'date'
  /** All-accounts register only — the account column is not drawn elsewhere,
   *  because in a single account's register the answer is the register. */
  | 'account'
  | 'payee'
  | 'category'
  | 'memo'
  | 'outflow'
  | 'inflow'

export interface SplitDraft {
  tempId: string
  amount: string
  categoryId: string | null
  memo: string
  /** The server line this draft edits; absent for a line not yet saved. */
  serverId?: string
}

interface TransactionEditState {
  editingField: { transactionId: string; field: EditableField } | null
  /** `loaded` is false while an existing split's lines are still being
   *  fetched — the editor must not offer a save until they arrive. */
  splitEditing: {
    transactionId: string
    totalAmount: number
    /** The total as typed, a magnitude — part of the draft like the lines.
     *  A saved split's total is corrected here (see SplitTransactionEditor);
     *  it starts as `totalAmount` and is reset whenever the editor opens. */
    totalInput: string
    splits: SplitDraft[]
    loaded: boolean
  } | null

  startEditing: (transactionId: string, field: EditableField) => void
  stopEditing: () => void
  /** `awaitLines` = the row is already split; its lines arrive via seedSplits.
   *  Does nothing for a row whose split is already being edited. */
  startSplitEditing: (transactionId: string, totalAmount: number, awaitLines?: boolean) => void
  seedSplits: (transactionId: string, splits: SplitDraft[]) => void
  updateSplit: (tempId: string, data: Partial<Omit<SplitDraft, 'tempId'>>) => void
  /** Replace the draft's lines whole — what the pure helpers in
   *  `utils/splits` return. */
  setSplits: (splits: SplitDraft[]) => void
  setSplitTotal: (totalInput: string) => void
  addSplit: () => void
  removeSplit: (tempId: string) => void
  stopSplitEditing: () => void
}

export const useTransactionEditStore = create<TransactionEditState>((set, get) => ({
  editingField: null,
  splitEditing: null,

  startEditing: (transactionId, field) => {
    set({ editingField: { transactionId, field }, splitEditing: null })
  },

  stopEditing: () => set({ editingField: null }),

  startSplitEditing: (transactionId, totalAmount, awaitLines = false) => {
    // Already open on this row: a second start would reset it to "awaiting
    // lines" and discard the draft in hand.
    if (get().splitEditing?.transactionId === transactionId) return
    const splits: SplitDraft[] = awaitLines
      ? []
      : [
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
        ]
    set({
      splitEditing: {
        transactionId,
        totalAmount,
        totalInput: toAmountInput(Math.abs(totalAmount)),
        splits,
        loaded: !awaitLines,
      },
      editingField: null,
    })
  },

  seedSplits: (transactionId, splits) => {
    const { splitEditing } = get()
    if (!splitEditing || splitEditing.transactionId !== transactionId || splitEditing.loaded) return
    set({ splitEditing: { ...splitEditing, splits, loaded: true } })
  },

  updateSplit: (tempId, data) => {
    const { splitEditing } = get()
    if (!splitEditing) return
    set({
      splitEditing: {
        ...splitEditing,
        splits: splitEditing.splits.map((s) => (s.tempId === tempId ? { ...s, ...data } : s)),
      },
    })
  },

  addSplit: () => {
    const { splitEditing } = get()
    if (!splitEditing) return
    set({
      splitEditing: {
        ...splitEditing,
        splits: [
          ...splitEditing.splits,
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
        ],
      },
    })
  },

  removeSplit: (tempId) => {
    const { splitEditing } = get()
    if (!splitEditing || !canRemoveSplitLine(splitEditing.splits.length)) return
    set({
      splitEditing: {
        ...splitEditing,
        splits: splitEditing.splits.filter((s) => s.tempId !== tempId),
      },
    })
  },

  setSplits: (splits) => {
    const { splitEditing } = get()
    if (!splitEditing) return
    set({ splitEditing: { ...splitEditing, splits } })
  },

  setSplitTotal: (totalInput) => {
    const { splitEditing } = get()
    if (!splitEditing) return
    set({ splitEditing: { ...splitEditing, totalInput } })
  },

  stopSplitEditing: () => set({ splitEditing: null }),
}))
