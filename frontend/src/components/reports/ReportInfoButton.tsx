import { InfoPopover } from '../common/InfoPopover/InfoPopover'
import type { ReportTab } from '../../stores/reportStore'
import { reportScopeOf, type ReportSectionId } from './reportCatalog'
import { SCOPE_COPY } from './reportScope'

interface Props {
  title: string
  children: React.ReactNode
}

/**
 * An ⓘ button beside a report's title.
 *
 * A thin naming layer over the shared InfoPopover so every "how does this
 * work?" in the app behaves the same way; the scope notes below are what
 * makes this one report-specific.
 */
export function ReportInfoButton({ title, children }: Props) {
  return (
    <InfoPopover title={title} label={`About the ${title} report`}>
      {children}
    </InfoPopover>
  )
}

/** One standard line in every report's info panel stating which accounts the
 * report considers — the scoping is deliberate and should never be a
 * surprise the user has to reverse-engineer from the numbers. The scope is
 * the report's catalog entry, so this line and the Reports overview say the
 * same thing. */
export function ReportScopeNote({ report }: { report: ReportTab | ReportSectionId }) {
  return <p className="info-pop__note">Accounts: {SCOPE_COPY[reportScopeOf(report)]}</p>
}

/** Stated on every report that now means spending in the narrow sense. Moving
 *  money to a tracked account used to count as spending here — it no longer
 *  does, and a number that changed under the user deserves saying so out
 *  loud rather than being noticed later and distrusted. */
export function SpendingClassNote() {
  return (
    <p className="info-pop__note">
      Counts spending only. Money moved into savings or investments, or used to pay down a tracked
      debt, leaves your budget but stays yours — so it is not counted here. Open any transaction to
      see how it is classified and why.
    </p>
  )
}
