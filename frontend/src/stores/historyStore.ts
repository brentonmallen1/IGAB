import { create } from 'zustand'

export interface HistoryEntry {
  transactionId: string
  field: string
  before: unknown
}

interface HistoryStore {
  stack: HistoryEntry[]
  push: (entry: HistoryEntry) => void
  undo: () => HistoryEntry | undefined
  clear: () => void
}

export const useHistoryStore = create<HistoryStore>((set, get) => ({
  stack: [],

  push: (entry) => set((s) => ({ stack: [...s.stack.slice(-49), entry] })),

  undo: () => {
    const { stack } = get()
    if (!stack.length) return undefined
    const entry = stack[stack.length - 1]
    set({ stack: stack.slice(0, -1) })
    return entry
  },

  clear: () => set({ stack: [] }),
}))
