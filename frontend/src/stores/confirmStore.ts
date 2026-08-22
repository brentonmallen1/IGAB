import { create } from 'zustand'

export interface ConfirmRequest {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
}

export interface ChoiceOption {
  /** Returned by chooseAsync when picked. */
  id: string
  label: string
  /** One line under the label saying what this choice actually does. */
  description?: string
  destructive?: boolean
}

export interface ChoiceRequest {
  title: string
  message?: string
  options: ChoiceOption[]
  cancelLabel?: string
}

interface ConfirmState {
  request: (ConfirmRequest & { resolve: (ok: boolean) => void }) | null
  answer: (ok: boolean) => void
  ask: (req: ConfirmRequest) => Promise<boolean>
  choice: (ChoiceRequest & { resolve: (id: string | null) => void }) | null
  pick: (id: string | null) => void
  choose: (req: ChoiceRequest) => Promise<string | null>
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

  choice: null,
  pick: (id) => {
    const current = get().choice
    set({ choice: null })
    current?.resolve(id)
  },
  choose: (req) =>
    new Promise<string | null>((resolve) => {
      const pending = get().choice
      pending?.resolve(null)
      set({ choice: { ...req, resolve } })
    }),
}))

/** Imperative entry point for non-React code paths (api/, utils/). */
export function confirmAsync(req: ConfirmRequest): Promise<boolean> {
  return useConfirmStore.getState().ask(req)
}

/**
 * Same flow for a question with more than two answers, resolving the chosen
 * option's id (or null if dismissed).
 *
 * Deleting an account that tracks a debt is the case that needed it: "keep the
 * debt" and "delete both" are different outcomes, not yes and no, and a
 * boolean confirm would have had to pick one of them silently. Widening
 * ConfirmRequest was the wrong shape — three outcomes is a different
 * component, not a bigger boolean — but the promise-based pattern is the same
 * one, so it lives here rather than as another modal flag.
 */
export function chooseAsync(req: ChoiceRequest): Promise<string | null> {
  return useConfirmStore.getState().choose(req)
}
