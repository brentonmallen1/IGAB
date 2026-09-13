import { useMemo } from 'react'
import { useAccountTypes } from '../../../api/accountTypes'
import {
  useExplainMove,
  type CategoryKind,
  type MoneyRulesResponse,
  type MoveExplanation,
} from '../../../api/moneyRules'
import { BUILTIN_ACCOUNT_TYPES } from '../../../constants/accountTypes'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'
import { isTrackedAsset } from '../../../utils/accountKinds'
import { budgetEffectLines } from '../../../utils/moneyMoves'
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { ClassChip } from './ClassChip'
import {
  EXPLORER_AMOUNT,
  explorerRequest,
  sideForType,
  type ExplorerState,
  type SideState,
  type TypeFacts,
} from './explorerMove'
import { familyList, figureLines, netWorthLine, signedMoney } from './moveAnswer'
import './MoneyExplorer.css'

const tagName = (key: string) => SYSTEM_TAG_HELP.find((t) => t.key === key)?.name ?? key

const CATEGORY_OPTIONS: { value: CategoryKind; label: string }[] = [
  { value: 'none', label: 'No category' },
  { value: 'ordinary', label: 'An ordinary category' },
  { value: 'savings', label: `A category tagged ${tagName('savings')}` },
  { value: 'debt_principal', label: `A category tagged ${tagName('debt_principal')}` },
  { value: 'income', label: 'Your income group (Ready to Assign)' },
]

interface Props {
  state: ExplorerState
  onChange: (next: ExplorerState) => void
  families: MoneyRulesResponse['report_families']
}

/** Move $1,000 and see what it counts as — every answer served by the rules
 * the reports run (`POST guide/money-moves/explain`). */
export function MoneyExplorer({ state, onChange, families }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: registry } = useAccountTypes(budgetId)
  const types: TypeFacts[] = registry ?? BUILTIN_ACCOUNT_TYPES
  const { formatMoney } = useFormatters()

  const request = useMemo(() => explorerRequest(state, types), [state, types])
  const { data, isFetching, isError, isPlaceholderData } = useExplainMove(budgetId, request)
  // Read only from an answer to THESE controls: the previous answer, kept on
  // screen while the next loads, may be about a pair that could carry one.
  const categoryBlocked = !isPlaceholderData && data?.category_role === null

  const labelOf = (key: string) => types.find((t) => t.key === key)?.label ?? key

  return (
    <div className="tool money-explorer">
      <div className="money-explorer__controls">
        <div className="guide-viewswitch" role="group" aria-label="Kind of move">
          {(
            [
              ['transfer', 'Transfer between accounts'],
              ['transaction', 'Money in or out'],
            ] as const
          ).map(([kind, label]) => (
            <button
              key={kind}
              type="button"
              className={`guide-viewswitch__button ${state.kind === kind ? 'guide-viewswitch__button--active' : ''}`}
              aria-pressed={state.kind === kind}
              onClick={() => onChange({ ...state, kind })}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="tool__grid">
          <Side
            title={state.kind === 'transfer' ? 'From' : 'Account'}
            side={state.from}
            types={types}
            onChange={(from) => onChange({ ...state, from })}
          />
          {state.kind === 'transfer' ? (
            <Side
              title="To"
              side={state.to}
              types={types}
              onChange={(to) => onChange({ ...state, to })}
            />
          ) : (
            <label className="tool__field">
              <span>Direction</span>
              <select
                value={state.direction}
                onChange={(e) =>
                  onChange({ ...state, direction: e.target.value as ExplorerState['direction'] })
                }
              >
                <option value="in">Money in</option>
                <option value="out">Money out</option>
              </select>
            </label>
          )}
          <div className="tool__field">
            <label htmlFor="money-explorer-category">Category</label>
            <select
              id="money-explorer-category"
              value={categoryBlocked ? 'none' : state.category}
              disabled={categoryBlocked}
              aria-describedby={categoryBlocked ? 'money-explorer-no-category' : undefined}
              onChange={(e) => onChange({ ...state, category: e.target.value as CategoryKind })}
            >
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            {categoryBlocked && (
              <span id="money-explorer-no-category" className="tool__hint">
                Neither side can hold a category: only a budget account’s row can, and on a transfer
                only when the other account is off budget.
              </span>
            )}
          </div>
        </div>
      </div>

      {isError ? (
        <p className="money-explorer__status">The answer could not be loaded.</p>
      ) : !data ? (
        <p className="money-explorer__status">Working it out…</p>
      ) : (
        <Answer
          data={data}
          stale={isFetching}
          amount={formatMoney(EXPLORER_AMOUNT)}
          legLabel={(role) =>
            role === 'to' ? labelOf(state.to.typeKey) : labelOf(state.from.typeKey)
          }
          families={families}
        />
      )}
    </div>
  )
}

function Side({
  title,
  side,
  types,
  onChange,
}: {
  title: string
  side: SideState
  types: TypeFacts[]
  onChange: (next: SideState) => void
}) {
  const type = types.find((t) => t.key === side.typeKey)
  const tracked =
    type && isTrackedAsset({ on_budget: side.onBudget, classification: type.classification })
  return (
    <fieldset className="tool__field money-explorer__side">
      <legend>{title}</legend>
      <select
        aria-label={`${title} account type`}
        value={side.typeKey}
        onChange={(e) => {
          const next = types.find((t) => t.key === e.target.value)
          if (next) onChange(sideForType(next))
        }}
      >
        {types.map((t) => (
          <option key={t.key} value={t.key}>
            {t.label}
          </option>
        ))}
      </select>
      <label className="tool__field--inline money-explorer__toggle">
        <input
          type="checkbox"
          checked={side.onBudget}
          onChange={(e) => onChange({ ...side, onBudget: e.target.checked })}
        />
        On budget
      </label>
      {tracked && (
        <label className="tool__field--inline money-explorer__toggle">
          <input
            type="checkbox"
            checked={side.countsAsSavings}
            onChange={(e) => onChange({ ...side, countsAsSavings: e.target.checked })}
          />
          Counts as savings
        </label>
      )}
    </fieldset>
  )
}

function Answer({
  data,
  stale,
  amount,
  legLabel,
  families,
}: {
  data: MoveExplanation
  stale: boolean
  amount: string
  legLabel: (role: MoveExplanation['legs'][number]['role']) => string
  families: MoneyRulesResponse['report_families']
}) {
  const { formatMoney } = useFormatters()
  const figures = figureLines(data.figures)
  return (
    <div
      className={`tool__results money-explorer__answer ${stale ? 'tool__results--stale' : ''}`}
      aria-live="polite"
    >
      <h4 className="money-explorer__heading">Moving {amount}</h4>
      <ul className="money-explorer__legs">
        {data.legs.map((leg) => (
          <li key={leg.role} className="money-explorer__leg surface surface--sunken">
            <div className="money-explorer__leg-head">
              <span className="money-explorer__leg-name">
                {legLabel(leg.role)}
                <span className="money-explorer__leg-side">
                  {leg.on_budget ? 'on budget' : 'off budget'}
                </span>
              </span>
              <ClassChip cls={leg.cls} label={leg.class_label} />
            </div>
            <p className="money-explorer__why">Because {leg.reason_text}.</p>
            <p className="money-explorer__counted">
              {leg.counted_in.length > 0
                ? `Counted in: ${familyList(leg.counted_in, families)}`
                : leg.on_budget
                  ? 'Not counted in income, spending or the savings rate'
                  : 'Off budget, so no report counts this side'}
            </p>
            {leg.planned_spend_by_tag && (
              <p className="money-explorer__counted">
                Budget vs Actual still counts it as spent from the category.
              </p>
            )}
          </li>
        ))}
      </ul>

      <dl className="money-explorer__effects">
        <div>
          <dt>Budget</dt>
          <dd>{budgetEffectLines(data.budget_terms, formatMoney).join('. ')}</dd>
        </div>
        <div>
          <dt>Reports</dt>
          <dd>
            {figures.length === 0
              ? 'No income, spending or saving'
              : figures.map((f) => `${f.label} ${signedMoney(f.value, formatMoney)}`).join(' · ')}
          </dd>
        </div>
        <div>
          <dt>Net worth</dt>
          <dd>{netWorthLine(data, formatMoney)}</dd>
        </div>
      </dl>
      <p className="money-explorer__assumption">{data.assumption}</p>
    </div>
  )
}
