import { useSavingsContributors, type SavingsContributor } from '../../api/reports'
import { useFormatters } from '../../hooks/useFormatters'
import { SYSTEM_TAG_HELP } from '../settings/TagsPanel/systemTagHelp'
import { Dialog } from '../common/Dialog/Dialog'
import { ReportErrorState } from './ReportErrorState'
import { sharePhrase } from './drillDownTotals'
import { pct } from './charts/savingsRateView'
import { foldIncomeSources, rateFormula } from './savingsRateBreakdown'
import { DetailFigure, DetailFigures, DetailRow, DetailRows, DetailSection } from './ReportDetail'
import './SavingsRateDialog.css'

const SAVINGS_TAG = SYSTEM_TAG_HELP.find((t) => t.key === 'savings')?.name ?? 'Savings'

interface Props {
  budgetId: string
  /** The window of the card that opened this — its totals are that card's. */
  startDate: string
  endDate: string
  /** The rate the opening card shows, served by its own endpoint. Not
   *  recomputed here: the dialog explains the card's figure, it does not
   *  offer a second one. */
  rate: number | null
  /** The Savings Rate tab's "Include debt payments". */
  withDebt: boolean
  onClose: () => void
}

/**
 * What a savings rate was made of — opened from the Overview's Savings Rate
 * card and the Savings Rate tab's summary card. Mounted only while open, so
 * the contributors are fetched only when someone asks.
 */
export function SavingsRateDialog({
  budgetId,
  startDate,
  endDate,
  rate,
  withDebt,
  onClose,
}: Props) {
  const title = withDebt ? 'Savings rate (with debt)' : 'Savings rate'
  const { data, isLoading, isError, error, refetch } = useSavingsContributors(
    budgetId,
    startDate,
    endDate
  )

  return (
    <Dialog title={title} onClose={onClose} historyKey="savings-rate-contributors">
      {isLoading ? (
        <p className="dialog__body dialog__body--muted">Loading…</p>
      ) : isError ? (
        <ReportErrorState error={error} onRetry={() => refetch()} />
      ) : data ? (
        <Contributors data={data} rate={rate} withDebt={withDebt} />
      ) : null}
    </Dialog>
  )
}

function Contributors({
  data,
  rate,
  withDebt,
}: {
  data: NonNullable<ReturnType<typeof useSavingsContributors>['data']>
  rate: number | null
  withDebt: boolean
}) {
  const { formatMoney } = useFormatters()
  const noIncome = data.income <= 0
  const income = foldIncomeSources(data.income_sources, data.income)
  const debtSection = (
    <ContributorSection
      title="Where the debt principal went"
      contributors={data.debt_contributors}
      whole={data.debt_principal}
      shareLabel="of debt principal"
      empty="No debt principal paid in this period."
      note={withDebt ? null : 'Not part of this rate.'}
    />
  )

  return (
    <>
      {noIncome ? (
        <p className="dialog__body">No income recorded, so there is no rate to explain.</p>
      ) : (
        <div className="savings-rate-dialog__rate">
          <span className="savings-rate-dialog__value">{pct(rate)}</span>
          <span className="savings-rate-dialog__formula">{rateFormula(withDebt)}</span>
        </div>
      )}

      <DetailFigures>
        <DetailFigure label="Income" value={formatMoney(data.income)} />
        <DetailFigure label="Saved" value={formatMoney(data.savings)} />
        <DetailFigure label="Debt principal" value={formatMoney(data.debt_principal)} />
      </DetailFigures>

      <ContributorSection
        title="Where the savings went"
        contributors={data.savings_contributors}
        whole={data.savings}
        shareLabel="of savings"
        empty="Nothing moved into savings in this period."
        note={null}
      />
      {withDebt && debtSection}

      <DetailSection title="Top income sources">
        {income.shown.length > 0 ? (
          <DetailRows>
            {income.shown.map((s) => (
              <DetailRow
                key={s.payee_id ?? 'none'}
                name={s.payee_name}
                amount={formatMoney(s.total)}
                amountNote={sharePhrase(s.total, data.income, 'of income')}
              />
            ))}
            {income.rest && (
              <DetailRow
                name={`${income.rest.count} other ${income.rest.count === 1 ? 'source' : 'sources'}`}
                amount={formatMoney(income.rest.total)}
                amountNote={sharePhrase(income.rest.total, data.income, 'of income')}
              />
            )}
          </DetailRows>
        ) : (
          <p className="dialog__body dialog__body--muted">No income in this period.</p>
        )}
      </DetailSection>

      {!withDebt && debtSection}

      <DetailSection title="What does not count">
        <p className="dialog__body">
          Growth or loss inside a tracked account — market movement, dividends — is not saving, and
          neither is moving money between two of your budget accounts. Spending is not part of the
          rate at all.
        </p>
        <p className="dialog__body">
          To count money as saved, transfer it to a tracked (off-budget) account that counts as
          savings, or tag the category it leaves from {SAVINGS_TAG}. Buying or selling something
          tracked that does not count as savings — a car, a house — is spending or income instead.
        </p>
      </DetailSection>
    </>
  )
}

function ContributorSection({
  title,
  contributors,
  whole,
  shareLabel,
  empty,
  note,
}: {
  title: string
  contributors: SavingsContributor[]
  whole: number
  shareLabel: string
  empty: string
  note: string | null
}) {
  const { formatMoney } = useFormatters()
  return (
    <DetailSection title={title}>
      {note && <p className="dialog__body dialog__body--muted">{note}</p>}
      {contributors.length > 0 ? (
        <DetailRows>
          {contributors.map((c) => (
            <DetailRow
              key={`${c.kind}:${c.id}`}
              name={c.name}
              nameNote={c.reason_label}
              amount={formatMoney(c.total)}
              amountNote={sharePhrase(c.total, whole, shareLabel)}
            />
          ))}
        </DetailRows>
      ) : (
        <p className="dialog__body dialog__body--muted">{empty}</p>
      )}
    </DetailSection>
  )
}
