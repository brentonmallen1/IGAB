import { create } from 'zustand'

type EditableField = 'date' | 'payee' | 'category' | 'memo' | 'outflow' | 'inflow'

export interface SplitDraft {
  tempId: string
  amount: string
  categoryId: string | null
  memo: string
}

interface TransactionEditState {
  editingField: { transactionId: string; field: EditableField } | null
  splitEditing: { transactionId: string; totalAmount: number; splits: SplitDraft[] } | null

  startEditing: (transactionId: string, field: EditableField) => void
  stopEditing: () => void
  startSplitEditing: (transactionId: string, totalAmount: number, existingSplits?: SplitDraft[]) => void
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

  startSplitEditing: (transactionId, totalAmount, existingSplits) => {
    const splits: SplitDraft[] = existingSplits ?? [
      { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' },
      { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' },
    ]
    set({ splitEditing: { transactionId, totalAmount, splits }, editingField: null })
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
        splits: [...splitEditing.splits, { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' }],
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
