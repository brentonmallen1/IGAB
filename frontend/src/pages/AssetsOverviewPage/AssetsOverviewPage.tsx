import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Link2, Plus } from 'lucide-react'
import { useAssets, type Asset } from '../../api/assets'
import { useLiabilities } from '../../api/liabilities'
import { AssetSettingsModal } from '../../components/assets/AssetSettingsModal'
import { useFormatters } from '../../hooks/useFormatters'
import { useAppStore } from '../../stores/appStore'
import { equityOf, liabilitiesSecuredBy } from '../../utils/equity'
import { isStaleValue } from '../../utils/assetValues'
import './AssetsOverviewPage.css'

const TYPE_LABEL: Record<string, string> = {
  property: 'Property',
  vehicle: 'Vehicle',
  other: 'Asset',
}

/** The mirror of LiabilitiesOverviewPage: everything the household owns and
 *  has stated a worth for, each card leading to the asset's own page. */
export function AssetsOverviewPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const navigate = useNavigate()
  const { formatMoney, formatDate } = useFormatters()
  const { data: assets = [], isLoading } = useAssets(budgetId)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const [creating, setCreating] = useState(false)

  if (!budgetId) return null

  const totalValue = assets.reduce((sum, a) => sum + (a.current_value ?? 0), 0)

  return (
    <div className="assets-page">
      <div className="assets-page__header">
        <div>
          <h1 className="assets-page__title">Assets</h1>
          {assets.length > 0 && (
            <div className="assets-page__total">
              {formatMoney(totalValue)} across {assets.length} asset
              {assets.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
        <button className="assets-page__add" onClick={() => setCreating(true)}>
          <Plus size={14} />
          Track an asset
        </button>
      </div>

      {isLoading ? (
        <div className="assets-page__empty">Loading…</div>
      ) : assets.length === 0 ? (
        <div className="assets-page__empty">
          <p>No assets tracked yet.</p>
          <p className="assets-page__empty-sub">
            A home, a vehicle — anything whose worth you'd state rather than transact. Its value
            joins net worth from the date you record it, and linking a debt to it shows the equity
            between the two.
          </p>
          <button className="assets-page__add" onClick={() => setCreating(true)}>
            <Plus size={14} />
            Track an asset
          </button>
        </div>
      ) : (
        <div className="assets-page__grid">
          {assets.map((asset: Asset) => {
            const secured = liabilitiesSecuredBy(asset.id, liabilities)
            const equity = equityOf(asset.current_value, asset.id, liabilities)
            const stale = isStaleValue(asset.value_as_of)
            return (
              <button
                key={asset.id}
                className="assets-page__card"
                onClick={() => navigate(`/assets/${asset.id}`)}
              >
                <div className="assets-page__card-top">
                  <span className="assets-page__card-name">{asset.name}</span>
                  <span className="assets-page__card-type">
                    {TYPE_LABEL[asset.asset_type ?? 'other'] ?? 'Asset'}
                  </span>
                </div>
                <div className="assets-page__card-value tabular">
                  {asset.current_value === null ? 'No value yet' : formatMoney(asset.current_value)}
                </div>
                <div className="assets-page__card-sub">
                  {asset.value_as_of ? (
                    <span className={stale ? 'assets-page__stale' : ''}>
                      as of {formatDate(asset.value_as_of)}
                      {stale ? ' — over a year old' : ''}
                    </span>
                  ) : (
                    'Record a value to count it in net worth'
                  )}
                </div>
                {secured.length > 0 && (
                  <div className="assets-page__card-equity">
                    <Link2 size={11} />
                    {equity === null ? '—' : `${formatMoney(equity)} equity`} · {secured.length}{' '}
                    debt{secured.length !== 1 ? 's' : ''}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}

      {creating && (
        <AssetSettingsModal budgetId={budgetId} asset={null} onClose={() => setCreating(false)} />
      )}
    </div>
  )
}
