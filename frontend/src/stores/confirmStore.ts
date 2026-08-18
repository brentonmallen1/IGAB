import { create } from 'zustand'

export interface ConfirmRequest {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
}

interface ConfirmState {
  request: (ConfirmRequest & { resolve: (ok: boolean) => void }) | null
  answer: (ok: boolean) => void
  ask: (req: ConfirmRequest) => Promise<boolean>
}

/**
 * Promise-based confirmation, so an async flow can await a real in-app sheet
 * instead of window.confirm.
 *
 * A native confirm is actively harmful mid-entry on touch: it blurs the
 * focused field, tears down the keyboard, retriggers a viewport resize in the
 * middle of whatever animation is running, and in an installed PWA renders
 * with the app's origin in the title. It also cannot be themed or styled.
 *
 * A second ask() while one is pending resolves the first as cancelled rather
 * than dropping its promise on the floor — an un-resolved await would hang the
 * caller's save path forever.
 */
export const useConfirmStore = create<ConfirmState>((set, get) => ({
  request: null,
  answer: (ok) => {
    const current = get().request
    set({ request: null })
    current?.resolve(ok)
  },
  ask: (req) =>
    new Promise<boolean>((resolve) => {
      const pending = get().request
      pending?.resolve(false)
      set({ request: { ...req, resolve } })
    }),
}))

/** Imperative entry point for non-React code paths (api/, utils/). */
export function confirmAsync(req: ConfirmRequest): Promise<boolean> {
  return useConfirmStore.getState().ask(req)
}
