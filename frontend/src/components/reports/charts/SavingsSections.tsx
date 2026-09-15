import type { ReactNode } from 'react'
import type { SavingsEnvelope, SavingsSaved, SavingsSection, SavingsTarget } from '../../../types'
import { accountTypeLabel } from '../../../constants/accountTypes'
import { BADGE_LABELS } from '../../budget/targetTooltip'
import { useFormatters } from '../../../hooks/useFormatters'

/**
 * The Savings report's three sections. Every figure is served
 * (`services/savings_report.py`): which envelope sits where, the totals and
 * the target verdicts. Nothing here adds a section to another.
 */

interface SectionFrameProps {
  id: string
  title: string
  total: number
  lede: ReactNode
  children: ReactNode
}

function SectionFrame({ id, title, total, lede, children }: SectionFrameProps) {
  const { formatMoney } = useFormatters()
  return (
    <section className="savings-section" aria-labelledby={id}>
      <header className="savings-section__head">
        <h3 id={id} className="savings-section__title">
          {title}
        </h3>
        <span className="savings-section__total tabular">{formatMoney(total)}</span>
      </header>
      <p className="savings-section__lede">{lede}</p>
      {children}
    </section>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="savings-section__empty">{children}</p>
}

/** The Budget page's pill, in its words: the page shows overfunded as funded. */
function statusLabel(target: SavingsTarget): string {
  return target.status === 'overfunded' ? BADGE_LABELS.funded : BADGE_LABELS[target.status]
}

function TargetCell({ target }: { target: SavingsTarget | null }) {
  const { formatMoney, formatDate } = useFormatters()
  if (!target) return <span className="savings-section__muted">No target</span>
  const pct =
    target.progress === null ? null : Math.round(Math.min(1, Math.max(0, target.progress)) * 100)
  return (
    <div className="savings-target">
      <span>
        {pct !== null ? `${pct}% of ` : ''}
        {formatMoney(target.amount)}
        {target.target_date ? ` by ${formatDate(target.target_date)}` : ''} · {statusLabel(target)}
      </span>
      {pct !== null && (
        <div
          className="savings-target__bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label={`${pct}% of target`}
        >
          <div className="savings-target__fill" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

function EnvelopeTable({
  caption,
  envelopes,
  withTarget,
}: {
  caption: string
  envelopes: SavingsEnvelope[]
  withTarget: boolean
}) {
  const { formatMoney } = useFormatters()
  return (
    <div className="savings-section__table-wrap">
      <table className="report-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" style={{ textAlign: 'left' }}>
              Envelope
            </th>
            <th scope="col" style={{ textAlign: 'left' }}>
              Group
            </th>
            <th scope="col" style={{ textAlign: 'right' }}>
              Available
            </th>
            {withTarget ? (
              <th scope="col" style={{ textAlign: 'left' }}>
                Target
              </th>
            ) : (
              <th scope="col" style={{ textAlign: 'right' }}>
                Assigned
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {envelopes.map((e) => (
            <tr key={e.category_id}>
              <td>{e.category_name}</td>
              <td className="savings-section__muted">{e.group_name}</td>
              <td style={{ textAlign: 'right' }} className="tabular">
                {formatMoney(e.current_balance)}
              </td>
              {withTarget ? (
                <td>
                  <TargetCell target={e.target} />
                </td>
              ) : (
                <td style={{ textAlign: 'right' }} className="tabular">
                  {formatMoney(e.total_inflow)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SavedSection({ saved }: { saved: SavingsSaved }) {
  const { formatMoney } = useFormatters()
  const empty = saved.envelopes.length === 0 && saved.accounts.length === 0
  return (
    <SectionFrame
      id="savings-saved"
      title="Saved"
      total={saved.total}
      lede={
        <>
          Kept-here Savings and Emergency fund envelopes, plus off-budget accounts that count as
          savings. Moving money from one to the other doesn&apos;t change this total.
        </>
      }
    >
      {empty ? (
        <Empty>
          Nothing saved here yet. Set a Savings envelope to <strong>kept here</strong>, tag an
          envelope <strong>Emergency fund</strong>, or mark an off-budget account{' '}
          <strong>Counts as savings</strong>.
        </Empty>
      ) : (
        <>
          {saved.envelopes.length > 0 && (
            <EnvelopeTable caption="Saved envelopes" envelopes={saved.envelopes} withTarget />
          )}
          {saved.accounts.length > 0 && (
            <div className="savings-section__table-wrap">
              <table className="report-table">
                <caption className="sr-only">Off-budget savings accounts</caption>
                <thead>
                  <tr>
                    <th scope="col" style={{ textAlign: 'left' }}>
                      Account
                    </th>
                    <th scope="col" style={{ textAlign: 'left' }}>
                      Type
                    </th>
                    <th scope="col" style={{ textAlign: 'right' }}>
                      Balance
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {saved.accounts.map((a) => (
                    <tr key={a.account_id}>
                      <td>{a.name}</td>
                      <td className="savings-section__muted">{accountTypeLabel(a.account_type)}</td>
                      <td style={{ textAlign: 'right' }} className="tabular">
                        {formatMoney(a.current_balance)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="savings-section__split tabular">
            Envelopes {formatMoney(saved.envelopes_total)} · Accounts{' '}
            {formatMoney(saved.accounts_total)}
          </p>
        </>
      )}
    </SectionFrame>
  )
}

export function OnTheWaySection({ section }: { section: SavingsSection }) {
  return (
    <SectionFrame
      id="savings-on-the-way"
      title="On the way to savings"
      total={section.total}
      lede={
        <>
          What sent-out Savings envelopes hold until the money leaves. It counts as saved when it is
          sent, so it isn&apos;t added to Saved.
        </>
      }
    >
      {section.envelopes.length === 0 ? (
        <Empty>No sent-out Savings envelopes.</Empty>
      ) : (
        <EnvelopeTable
          caption="Envelopes on the way to savings"
          envelopes={section.envelopes}
          withTarget={false}
        />
      )}
    </SectionFrame>
  )
}

export function SinkingFundsSection({ section }: { section: SavingsSection }) {
  return (
    <SectionFrame
      id="savings-sinking-funds"
      title="Sinking funds"
      total={section.total}
      lede={
        <>
          Envelopes tagged Long-term expense: money spoken for by a planned bill. Never added to
          Saved.
        </>
      }
    >
      {section.envelopes.length === 0 ? (
        <Empty>
          No sinking funds. Tag an envelope <strong>Long-term expense</strong>, ideally with a
          target, and it shows here.
        </Empty>
      ) : (
        <EnvelopeTable caption="Sinking funds" envelopes={section.envelopes} withTarget />
      )}
    </SectionFrame>
  )
}
