import { useId, type ReactNode } from 'react'
import { Surface } from '../common/Surface'
import './ReportDetail.css'

/**
 * The pieces a report card's explanatory dialog is laid out from: a well of
 * labelled figures, titled sections, and a ranked list of named amounts.
 *
 * Written once for the Overview's means dialog and the savings-rate dialog.
 * The means dialog had them privately, and a second dialog copying its
 * stylesheet is two sets of spacing and two heading sizes by the third.
 * Presentation only — every figure passed in is served and pre-formatted.
 */

export function DetailFigures({ children }: { children: ReactNode }) {
  return (
    <Surface as="dl" variant="sunken" className="report-detail__figures">
      {children}
    </Surface>
  )
}

export function DetailFigure({
  label,
  value,
  strong,
}: {
  label: string
  value: string
  strong?: boolean
}) {
  return (
    <div className={`report-detail__figure${strong ? ' report-detail__figure--strong' : ''}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

/** A titled section, named by its heading for assistive technology. */
export function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section className="report-detail__section" aria-labelledby={id}>
      <h4 id={id} className="report-detail__heading">
        {title}
      </h4>
      {children}
    </section>
  )
}

export function DetailRows({ children }: { children: ReactNode }) {
  return <ol className="report-detail__rows">{children}</ol>
}

/** One named amount: the name with a muted note under it (a group, a reason),
 *  and the amount with a muted note under it (a share). */
export function DetailRow({
  name,
  nameNote,
  amount,
  amountNote,
}: {
  name: string
  nameNote?: string
  amount: string
  amountNote?: string | null
}) {
  return (
    <li className="report-detail__row">
      <span className="report-detail__name">
        {name}
        {nameNote && <span className="report-detail__note">{nameNote}</span>}
      </span>
      <span className="report-detail__amount">
        {amount}
        {amountNote && <span className="report-detail__note">{amountNote}</span>}
      </span>
    </li>
  )
}
