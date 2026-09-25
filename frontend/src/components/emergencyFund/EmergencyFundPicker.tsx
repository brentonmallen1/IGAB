import { useId, useState } from 'react'
import { useEmergencyFund, useSetEmergencyFund } from '../../api/emergencyFund'
import { useSetBinding } from '../../api/guide'
import { useTagMembership, useTags } from '../../api/tags'
import { apiErrorMessage } from '../../api/client'
import { Dialog } from '../common/Dialog/Dialog'
import { CategoryMembershipList } from '../tags/CategoryMembershipList'
import { initialDraft, type MembershipDraft } from '../tags/membershipList'
import { PickerAccounts } from './PickerAccounts'
import { PickerKeptElsewhere } from './PickerKeptElsewhere'
import {
  buildChoice,
  externalDraft,
  memberAccounts,
  parseExternal,
  type ExternalDraft,
} from './pickerChoice'
import { GuideTabLink } from '../guide/GuideTabLink'
import './EmergencyFundPicker.css'

export const PICKER_TITLE = 'What your emergency fund counts'

interface Props {
  budgetId: string
  /** "guide" adds the Guide's own "Don't track this" action. */
  from?: 'guide'
  onClose: () => void
}

/**
 * Choosing what the emergency fund counts: envelopes tagged Emergency fund
 * (with how each counts as saved), off-budget accounts, and an amount kept
 * elsewhere. Nothing is guessed. Save sends one PUT, written as one change —
 * one Cmd+Z undoes all of it.
 *
 * Opened from Settings → Tags, the tag notices, the Guide, and every report
 * that quotes the fund (`EmergencyFundCounting`).
 */
export function EmergencyFundPicker({ budgetId, from, onClose }: Props) {
  const picker = useEmergencyFund(budgetId)
  const { data: tags } = useTags(budgetId)
  const tagId = tags?.find((t) => t.system_key === 'emergency_fund')?.id ?? null
  const membership = useTagMembership(budgetId, tagId)
  const save = useSetEmergencyFund(budgetId)
  const dismiss = useSetBinding(budgetId)
  const formId = `ef-picker-${useId()}`

  // Each draft is null until touched, so it reads what was served until then —
  // seeded without an effect.
  const [envelopesTouched, setEnvelopes] = useState<MembershipDraft | null>(null)
  const [accountsTouched, setAccounts] = useState<Set<string> | null>(null)
  const [externalTouched, setExternal] = useState<ExternalDraft | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loaded = picker.data && membership.data
  const envelopes =
    envelopesTouched ?? (membership.data ? initialDraft(membership.data.categories) : null)
  const accounts =
    accountsTouched ?? (picker.data ? memberAccounts(picker.data.account_candidates) : null)
  const external =
    externalTouched ?? (picker.data ? externalDraft(picker.data.fund.external) : null)
  const parsed = external ? parseExternal(external) : null
  const amountError = parsed && 'error' in parsed ? parsed.error : null

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!membership.data || !envelopes || !accounts || !external) return
    setError(null)
    const built = buildChoice({
      rows: membership.data.categories,
      envelopes,
      accounts,
      external,
    })
    if ('error' in built) {
      setError('Fix the amount kept elsewhere first')
      return
    }
    try {
      await save.mutateAsync(built.choice)
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save what the fund counts'))
    }
  }

  async function stopTracking() {
    setError(null)
    try {
      await dismiss.mutateAsync({ conceptKey: 'emergency_fund', mode: 'dismissed' })
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not stop tracking this'))
    }
  }

  const failed = picker.isError || membership.isError

  return (
    <Dialog
      title={PICKER_TITLE}
      onClose={onClose}
      historyKey="emergency-fund-picker"
      footer={
        <div className="dialog-actions">
          {from === 'guide' && (
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={stopTracking}
              disabled={dismiss.isPending}
            >
              Don’t track this in the Guide
            </button>
          )}
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              form={formId}
              className="dialog-btn dialog-btn--primary"
              disabled={save.isPending}
            >
              Save
            </button>
          </div>
        </div>
      }
    >
      {failed ? (
        <p className="dialog-form__error" role="alert">
          {apiErrorMessage(picker.error ?? membership.error, 'Could not load the emergency fund')}
        </p>
      ) : !loaded || !envelopes || !accounts || !external ? (
        <p className="dialog-form__hint">Loading…</p>
      ) : (
        <form id={formId} className="dialog-form ef-picker" onSubmit={submit} noValidate>
          <p className="dialog-form__hint">
            Nothing is guessed: the fund is exactly what you choose here.{' '}
            <GuideTabLink tab="aside" anchor="emergency-fund">
              What counts
            </GuideTabLink>
          </p>
          <section className="ef-picker__section" aria-labelledby={`${formId}-envelopes`}>
            <h4 id={`${formId}-envelopes`} className="ef-picker__title">
              Envelopes
            </h4>
            <CategoryMembershipList
              rows={membership.data!.categories}
              draft={envelopes}
              onChange={setEnvelopes}
              savingsTag={membership.data!.tag.savings_tag}
              label="Envelopes tagged Emergency fund"
              // Accounts and kept-elsewhere share the sheet below it.
              fillsSheet={false}
            />
          </section>
          <PickerAccounts
            candidates={picker.data!.account_candidates}
            checked={accounts}
            onToggle={(id) => {
              const next = new Set(accounts)
              if (next.has(id)) next.delete(id)
              else next.add(id)
              setAccounts(next)
            }}
          />
          <PickerKeptElsewhere draft={external} onChange={setExternal} amountError={amountError} />
        </form>
      )}
    </Dialog>
  )
}
