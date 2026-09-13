/**
 * The explorer's controls, turned into the question the server answers.
 *
 * Wiring only. An account type contributes its classification and the two
 * defaults a new account of that type would start with — the same defaults
 * the account forms reset to — and the reader may flip either. Nothing here
 * says what the move counts as; `POST guide/money-moves/explain` does.
 */
import type {
  AccountShapeIn,
  CategoryKind,
  MoneyMoveRequest,
  MoveDirection,
  MoveKind,
} from '../../../api/moneyRules'
import { BUILTIN_ACCOUNT_TYPES } from '../../../constants/accountTypes'

export interface TypeFacts {
  key: string
  label: string
  classification: 'asset' | 'liability'
  default_on_budget: boolean
  default_counts_as_savings: boolean
}

export interface SideState {
  typeKey: string
  onBudget: boolean
  countsAsSavings: boolean
}

export interface ExplorerState {
  kind: MoveKind
  from: SideState
  to: SideState
  direction: MoveDirection
  category: CategoryKind
}

/** The explorer always moves this much, so every answer reads in one unit. */
export const EXPLORER_AMOUNT = 1000

export function sideForType(type: TypeFacts): SideState {
  return {
    typeKey: type.key,
    onBudget: type.default_on_budget,
    countsAsSavings: type.default_counts_as_savings,
  }
}

function typeByKey(types: readonly TypeFacts[], key: string): TypeFacts | undefined {
  return types.find((t) => t.key === key)
}

function shape(types: readonly TypeFacts[], side: SideState): AccountShapeIn | null {
  const type = typeByKey(types, side.typeKey)
  if (!type) return null
  return {
    classification: type.classification,
    on_budget: side.onBudget,
    counts_as_savings: side.countsAsSavings,
  }
}

/** The request for these controls, or null while a chosen type is unknown
 * (a registry still loading, or a custom type deleted elsewhere). */
export function explorerRequest(
  state: ExplorerState,
  types: readonly TypeFacts[]
): MoneyMoveRequest | null {
  const account = shape(types, state.from)
  if (!account) return null
  if (state.kind === 'transaction') {
    return {
      kind: 'transaction',
      account,
      direction: state.direction,
      category: state.category,
      amount: EXPLORER_AMOUNT,
    }
  }
  const to = shape(types, state.to)
  if (!to) return null
  return {
    kind: 'transfer',
    account,
    to_account: to,
    category: state.category,
    amount: EXPLORER_AMOUNT,
  }
}

function builtin(key: string): TypeFacts {
  const type = BUILTIN_ACCOUNT_TYPES.find((t) => t.key === key)
  if (!type) throw new Error(`no built-in account type '${key}'`)
  return type
}

/** A starting point named by built-in type keys, with the on-budget flag
 * overridden where the example needs it. Built-ins exist in every budget. */
export function preset(
  kind: MoveKind,
  fromKey: string,
  toKey: string,
  options: {
    direction?: MoveDirection
    category?: CategoryKind
    fromOnBudget?: boolean
    toOnBudget?: boolean
  } = {}
): ExplorerState {
  const from = sideForType(builtin(fromKey))
  const to = sideForType(builtin(toKey))
  return {
    kind,
    from: { ...from, onBudget: options.fromOnBudget ?? from.onBudget },
    to: { ...to, onBudget: options.toOnBudget ?? to.onBudget },
    direction: options.direction ?? 'out',
    category: options.category ?? 'none',
  }
}

export const DEFAULT_EXPLORER: ExplorerState = preset('transfer', 'checking', 'investment')

/** The built-in shape of a type key, for the fixed worked month. */
export function builtinShape(key: string, onBudget?: boolean): AccountShapeIn {
  const type = builtin(key)
  return {
    classification: type.classification,
    on_budget: onBudget ?? type.default_on_budget,
    counts_as_savings: type.default_counts_as_savings,
  }
}
