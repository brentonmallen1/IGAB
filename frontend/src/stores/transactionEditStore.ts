import { create } from 'zustand'
import { randomUUID } from '../utils/uuid'

export type EditableField = 'date' | 'payee' | 'category' | 'memo' | 'outflow' | 'inflow'

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
    splits: SplitDraft[]
    loaded: boolean
  } | null

  startEditing: (transactionId: string, field: EditableField) => void
  stopEditing: () => void
  /** `awaitLines` = the row is already split; its lines arrive via seedSplits. */
  startSplitEditing: (transactionId: string, totalAmount: number, awaitLines?: boolean) => void
  seedSplits: (transactionId: string, splits: SplitDraft[]) => void
  updateSplit: (tempId: string, data: Partial<Omit<SplitDraft, 'tempId'>>) => void
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
    const splits: SplitDraft[] = awaitLines
      ? []
      : [
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
        ]
    set({
      splitEditing: { transactionId, totalAmount, splits, loaded: !awaitLines },
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
        splits: splitEditing.splits.map((s) => s.tempId === tempId ? { ...s, ...data } : s),
      },
    })
  },

  addSplit: () => {
    const { splitEditing } = get()
    if (!splitEditing) return
    set({
      splitEditing: {
        ...splitEditing,
        splits: [...splitEditing.splits, { tempId: randomUUID(), amount: '', categoryId: null, memo: '' }],
      },
    })
  },

  removeSplit: (tempId) => {
    const { splitEditing } = get()
    if (!splitEditing || splitEditing.splits.length <= 2) return
    set({
      splitEditing: {
        ...splitEditing,
        splits: splitEditing.splits.filter((s) => s.tempId !== tempId),
      },
    })
  },

  stopSplitEditing: () => set({ splitEditing: null }),
}))
