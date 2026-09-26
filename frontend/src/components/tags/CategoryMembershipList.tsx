import { useId, useState } from 'react'
import type { MembershipCategory } from '../../api/tags'
import type { SavingsMode } from '../../types'
import { DEFAULT_MARKER, SAVINGS_MODE_OPTIONS, savingsModeShort } from '../../utils/savingsModes'
import {
  chooseMode,
  draftMode,
  drawsChecked,
  groupRows,
  isImplied,
  servedDefault,
  toggleChecked,
  type MembershipDraft,
} from './membershipList'
import './CategoryMembershipList.css'

interface Props {
  rows: readonly MembershipCategory[]
  draft: MembershipDraft
  onChange: (draft: MembershipDraft) => void
  /** The tag makes a category a savings category (served `savings_tag`), so
   *  each checked row says how its money counts as saved. */
  savingsTag: boolean
  /** Names the checklist for assistive tech: "Categories tagged Essential". */
  label: string
  /** The checklist is its dialog's whole body, so on a phone it fills the
   *  sheet rather than keeping the desktop footprint. Required, so each caller
   *  says which it is: one sharing its sheet with other sections keeps the
   *  footprint, or it would push them below a full screen of categories. */
  fillsSheet: boolean
}

/**
 * A tag's checklist: every taggable category, grouped as on the Budget page,
 * with a filter. Controlled — the dialog or picker holding it owns the draft
 * and sends `membershipDiff` on Save.
 *
 * The list scrolls inside a fixed-height region, so the dialog around it does
 * not grow with the budget and the filter stays in view; on a phone it fills
 * the sheet instead.
 *
 * A row counted through another tag (served `implied_by` — an Essential
 * category on the Cost of living checklist) is drawn ticked and locked, and
 * never enters the diff.
 */
export function CategoryMembershipList({
  rows,
  draft,
  onChange,
  savingsTag,
  label,
  fillsSheet,
}: Props) {
  const [filter, setFilter] = useState('')
  const base = useId()
  const groups = groupRows(rows, filter)

  return (
    <div className={`membership-list${fillsSheet ? ' membership-list--fill' : ''}`}>
      <label className="dialog-form__field membership-list__filter" htmlFor={`${base}-filter`}>
        Filter
        <input
          id={`${base}-filter`}
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Category or group"
          autoComplete="off"
        />
      </label>
      {savingsTag && (
        <p className="dialog-form__hint">
          Each checked envelope counts as saved while it’s in the budget, or when it leaves the
          budget.
        </p>
      )}
      <div
        className="membership-list__scroll surface surface--sunken"
        role="group"
        aria-label={label}
      >
        {groups.length === 0 ? (
          <p className="membership-list__empty">
            {rows.length === 0 ? 'No categories to tag yet.' : 'Nothing matches that filter.'}
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.groupId} className="membership-list__group">
              <div className="membership-list__group-name" aria-hidden>
                {group.groupName}
              </div>
              <ul className="membership-list__rows">
                {group.rows.map((row) => {
                  const id = `${base}-${row.id}`
                  const checked = drawsChecked(draft, row)
                  const implied = isImplied(row)
                  return (
                    <li key={row.id} className="membership-list__row">
                      <label
                        className={`membership-list__choice${implied ? ' membership-list__choice--implied' : ''}`}
                        htmlFor={id}
                      >
                        <input
                          id={id}
                          type="checkbox"
                          checked={checked}
                          disabled={implied}
                          onChange={() => {
                            if (!implied) onChange(toggleChecked(draft, row.id))
                          }}
                        />
                        <span className="membership-list__name">
                          {row.name}
                          <span className="sr-only">, {group.groupName}</span>
                        </span>
                        {/* The hidden commas keep the accessible name
                            "Rent, Bills, counted through Essential" — inline
                            spans are joined without a space. */}
                        {row.is_archived && (
                          <span className="membership-list__note">
                            <span className="sr-only">,</span> archived
                          </span>
                        )}
                        {implied && (
                          <span className="membership-list__note">
                            <span className="sr-only">,</span> counted through {row.implied_by}
                          </span>
                        )}
                      </label>
                      {savingsTag && checked && !implied && (
                        <ModeSelect
                          id={`${id}-mode`}
                          row={row}
                          draft={draft}
                          onChoose={(mode) => onChange(chooseMode(draft, row.id, mode))}
                        />
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function ModeSelect({
  id,
  row,
  draft,
  onChoose,
}: {
  id: string
  row: MembershipCategory
  draft: MembershipDraft
  onChoose: (mode: SavingsMode | null) => void
}) {
  const known = servedDefault(draft, row)
  const value = draftMode(draft, row) ?? ''
  return (
    <select
      id={id}
      className="membership-list__mode"
      aria-label={`${row.name} counts as saved`}
      value={value}
      onChange={(e) => onChoose(e.target.value === '' ? null : (e.target.value as SavingsMode))}
    >
      <option value="">{known ? `${savingsModeShort(known)} ${DEFAULT_MARKER}` : `default`}</option>
      {SAVINGS_MODE_OPTIONS.filter((o) => o.mode !== known).map((o) => (
        <option key={o.mode} value={o.mode}>
          {o.short}
        </option>
      ))}
    </select>
  )
}
