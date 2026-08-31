import { useCategoryClassification } from '../../../api/categories'
import { useFormatters } from '../../../hooks/useFormatters'
import { Tooltip } from '../../common/Tooltip/Tooltip'

interface Props {
  categoryId: string
}

/**
 * "Counts as Debt payment" on the category itself, before the user has
 * opened a report and wondered where the money went. Renders nothing for an
 * ordinary spending category — the badge is for the exceptions, and a chip
 * on every category would say nothing about any of them.
 */
export function ClassificationSection({ categoryId }: Props) {
  const { data } = useCategoryClassification(categoryId)
  const { formatMoney } = useFormatters()

  if (!data?.dominant || !data.dominant_label) return null

  const tooltip = (
    <span>
      {data.explanation}
      {data.classes.length > 1 && (
        <>
          <br />
          {data.classes.map((c) => `${c.label}: ${formatMoney(Number(c.total))}`).join(' · ')}
        </>
      )}
    </span>
  )

  return (
    <div className="inspector-section">
      <div className="inspector-section__title">Counts as</div>
      <Tooltip content={tooltip}>
        <span className="classification-badge">{data.dominant_label}</span>
      </Tooltip>
      <p className="classification-hint">
        Spending reports leave this out by default — it builds what you own or pays down what you
        owe.
      </p>
    </div>
  )
}
