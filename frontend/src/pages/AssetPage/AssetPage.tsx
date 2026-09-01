import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowUpRight, Pencil, Settings2, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  useAddAssetValue,
  useAssetValues,
  useAssets,
  useDeleteAssetValue,
  useUpdateAssetValue,
} from '../../api/assets'
import { useLiabilities } from '../../api/liabilities'
import { useLiabilitiesReport } from '../../api/reports'
import { AssetSettingsModal } from '../../components/assets/AssetSettingsModal'
import { DatedAmountForm } from '../../components/common/DatedAmountForm/DatedAmountForm'
import { Pill } from '../../components/common/Pill/Pill'
import { Surface } from '../../components/common/Surface'
import { MetricCard } from '../../components/reports/MetricCard'
import { MetricRow } from '../../components/reports/MetricRow'
import { ChartTooltip } from '../../components/reports/charts/ChartTooltip'
import { CHART_COLORS, COLOR_NEGATIVE } from '../../components/reports/charts/chartColors'
import { useFormatters } from '../../hooks/useFormatters'
import { useAppStore } from '../../stores/appStore'
import { confirmAsync } from '../../stores/confirmStore'
import { equityOf, liabilitiesSecuredBy } from '../../utils/equity'
import { isStaleValue } from '../../utils/assetValues'
import { parseAmountInput } from '../../utils/money'
import './AssetPage.css'

const TYPE_LABEL: Record<string, string> = {
  property: 'Property',
  vehicle: 'Vehicle',
  other: 'Asset',
}

/**
 * One thing the household owns: its stated value over time, the debts
 * secured against it, and the equity between the two.
 *
 * Mirrors LiabilityPage section for section, with one deliberate departure
 * in the chart: PaydownChart joins solid fact to a dashed forecast at a
 * "Today" line, and the value chart has NO forecast half at all — projecting
 * appreciation would invent exactly the kind of unverified number the app
 * refuses everywhere else. The line simply stops at the last recorded point.
 */
export function AssetPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const navigate = useNavigate()
  const { formatMoney, formatDate } = useFormatters()

  const { data: assets = [], isLoading } = useAssets(budgetId)
  const asset = assets.find((a) => a.id === assetId) ?? null
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const { data: values = [] } = useAssetValues(budgetId, assetId ?? null)

  const addValue = useAddAssetValue(budgetId ?? '')
  const updateValue = useUpdateAssetValue(budgetId ?? '')
  const deleteValue = useDeleteAssetValue(budgetId ?? '')

  const [showValueForm, setShowValueForm] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const secured = useMemo(
    () => (asset ? liabilitiesSecuredBy(asset.id, liabilities) : []),
    [asset, liabilities]
  )
  const { data: liabReport } = useLiabilitiesReport(budgetId)

  // Value points oldest-first for the chart; the register reads newest-first.
  // With secured debts, rows ride the liabilities report's monthly series so
  // the Owed line can sit beneath the value — the gap between the two IS the
  // equity, read directly off the chart. The value steps: each month shows
  // the latest point on or before it, the same step rule net worth uses.
  const chartData = useMemo(() => {
    const points = [...values].reverse()
    const balances = liabReport?.balance_over_time ?? []
    if (secured.length === 0 || balances.length === 0) {
      return points.map((v) => ({ date: v.date, Value: v.value as number | null }))
    }
    const steppedValue = (d: string): number | null => {
      let latest: number | null = null
      for (const v of points) {
        if (v.date <= d) latest = v.value
        else break
      }
      return latest
    }
    return balances.map((pt) => ({
      date: pt.date,
      Value: steppedValue(pt.date),
      Owed: secured.reduce((sum, l) => sum + Number(pt.per_liability[l.id] ?? 0), 0),
    }))
  }, [values, secured, liabReport])

  if (!budgetId || !assetId) return null
  if (isLoading) {
    return (
      <div className="asset-page">
        <div className="asset-page__empty">Loading…</div>
      </div>
    )
  }
  if (!asset) {
    return (
      <div className="asset-page">
        <div className="asset-page__empty">
          This asset isn't tracked anymore. <Link to="/assets">Back to assets</Link>
        </div>
      </div>
    )
  }

  const equity = equityOf(asset.current_value, asset.id, liabilities)
  const stale = isStaleValue(asset.value_as_of)
  const firstValue = values.length > 0 ? values[values.length - 1].value : null
  const change =
    asset.current_value !== null && firstValue !== null ? asset.current_value - firstValue : null

  async function handleAddValue(value: number, date: string | null) {
    await addValue.mutateAsync({ assetId: asset!.id, value, ...(date ? { date } : {}) })
    toast.success('Value recorded')
    setShowValueForm(false)
  }

  async function commitEdit(valueId: string) {
    const parsed = parseAmountInput(editValue)
    if (!isNaN(parsed) && parsed >= 0) {
      await updateValue.mutateAsync({ assetId: asset!.id, valueId, value: parsed })
    }
    setEditingId(null)
  }

  async function handleDeletePoint(valueId: string, dateLabel: string) {
    const ok = await confirmAsync({
      title: `Remove the ${dateLabel} value?`,
      message: 'Net worth falls back to the point before it from that date on.',
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (ok) await deleteValue.mutateAsync({ assetId: asset!.id, valueId })
  }

  return (
    <div className="asset-page">
      <div className="asset-page__header">
        <div className="asset-page__header-left">
          <h1 className="asset-page__name">{asset.name}</h1>
          <Pill>{TYPE_LABEL[asset.asset_type ?? 'other'] ?? 'Asset'}</Pill>
          <button
            className="asset-page__settings"
            onClick={() => setShowSettings(true)}
            title="Asset settings"
            aria-label="Asset settings"
          >
            <Settings2 size={15} />
          </button>
        </div>
        <div className="asset-page__header-actions">
          <button className="asset-page__action" onClick={() => setShowValueForm(true)}>
            Update value
          </button>
        </div>
      </div>

      <MetricRow>
        <MetricCard
          label="Current value"
          value={asset.current_value === null ? '—' : formatMoney(asset.current_value)}
          sub={
            asset.value_as_of ? (
              <span className={stale ? 'asset-page__asof asset-page__asof--stale' : ''}>
                as of {formatDate(asset.value_as_of)}
                {stale ? ' — over a year old' : ''}
              </span>
            ) : (
              'No value recorded yet'
            )
          }
          variant="raised"
        />
        {change !== null && values.length > 1 && (
          <MetricCard
            label="Change since first recorded"
            value={`${change >= 0 ? '+' : ''}${formatMoney(change)}`}
            sub={`from ${formatDate(values[values.length - 1].date)}`}
            variant="raised"
          />
        )}
        {secured.length > 0 && (
          <MetricCard
            label="Equity"
            value={equity === null ? '—' : formatMoney(equity)}
            sub={`value − ${formatMoney(secured.reduce((s, l) => s + l.current_balance, 0))} owed`}
            variant="raised"
          />
        )}
      </MetricRow>

      {chartData.length > 1 && (
        <Surface variant="raised" className="asset-page__section">
          <div className="asset-page__section-header">
            <h2>Value over time</h2>
          </div>
          {/* No forecast half, deliberately: the line stops at the last
              recorded point. The Owed line beneath makes the gap between
              the two READ as the equity. */}
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis
                tickFormatter={(v) => formatMoney(v)}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={90}
              />
              <Tooltip
                content={<ChartTooltip showTotal={false} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <Line
                type="stepAfter"
                dataKey="Value"
                stroke={CHART_COLORS[0]}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
              {secured.length > 0 && (
                <Line
                  type="monotone"
                  dataKey="Owed"
                  stroke={COLOR_NEGATIVE}
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </Surface>
      )}

      <Surface variant="raised" className="asset-page__section">
        <div className="asset-page__section-header">
          <h2>Value register</h2>
          <span className="asset-page__section-sub">
            Every value this asset was ever given — reviewable, correctable.
          </span>
        </div>
        {values.length === 0 ? (
          <p className="asset-page__empty-note">
            No values recorded. Until one is, this asset contributes nothing to net worth — there is
            no honest number to show.
          </p>
        ) : (
          <table className="asset-page__register">
            <thead>
              <tr>
                <th scope="col">As of</th>
                <th scope="col" className="asset-page__num">
                  Value
                </th>
                <th scope="col" className="asset-page__num">
                  Change
                </th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {values.map((v, i) => {
                const prev = values[i + 1]
                const delta = prev ? v.value - prev.value : null
                return (
                  <tr key={v.id}>
                    <td>{formatDate(v.date)}</td>
                    <td className="asset-page__num tabular">
                      {editingId === v.id ? (
                        <input
                          className="asset-page__edit-input"
                          type="number"
                          min="0"
                          step="0.01"
                          inputMode="decimal"
                          value={editValue}
                          autoFocus
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={() => commitEdit(v.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitEdit(v.id)
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                        />
                      ) : (
                        formatMoney(v.value)
                      )}
                    </td>
                    <td className="asset-page__num tabular asset-page__delta">
                      {delta === null ? '—' : `${delta >= 0 ? '+' : ''}${formatMoney(delta)}`}
                    </td>
                    <td className="asset-page__row-actions">
                      <button
                        title="Correct this value"
                        aria-label={`Correct the ${v.date} value`}
                        onClick={() => {
                          setEditingId(v.id)
                          setEditValue(String(v.value))
                        }}
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        title="Remove this point"
                        aria-label={`Remove the ${v.date} value`}
                        onClick={() => handleDeletePoint(v.id, formatDate(v.date))}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Surface>

      <Surface variant="raised" className="asset-page__section">
        <div className="asset-page__section-header">
          <h2>Secured debts</h2>
        </div>
        {secured.length === 0 ? (
          <p className="asset-page__empty-note">
            No debt is linked to this asset. Link one from its liability page and the equity shows
            up here.
          </p>
        ) : (
          <ul className="asset-page__debts">
            {secured.map((l) => (
              <li key={l.id}>
                <Link to={`/liabilities/${l.id}`} className="asset-page__debt-link">
                  {l.name}
                  <span className="tabular">{formatMoney(l.current_balance)} owed</span>
                  <ArrowUpRight size={12} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Surface>

      {showValueForm && (
        <DatedAmountForm
          title="Update value"
          amountLabel="What is it worth?"
          placeholder={asset.current_value !== null ? String(asset.current_value) : undefined}
          pending={addValue.isPending}
          onSubmit={handleAddValue}
          onClose={() => setShowValueForm(false)}
        />
      )}

      {showSettings && (
        <AssetSettingsModal
          budgetId={budgetId}
          asset={asset}
          onClose={() => setShowSettings(false)}
          onDeleted={() => navigate('/assets')}
        />
      )}
    </div>
  )
}
