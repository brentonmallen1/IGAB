import { useState } from 'react'
import toast from 'react-hot-toast'
import { useCreateAsset, useDeleteAsset, useUpdateAsset, type Asset } from '../../api/assets'
import { confirmAsync } from '../../stores/confirmStore'
import { parseAmountInput } from '../../utils/money'
import { Dialog } from '../common/Dialog/Dialog'
import './AssetSettingsModal.css'

const TYPES = [
  { value: 'property', label: 'Property' },
  { value: 'vehicle', label: 'Vehicle' },
  { value: 'other', label: 'Something else' },
] as const

interface Props {
  budgetId: string
  /** Null = create. */
  asset: Asset | null
  onClose: () => void
  onDeleted?: () => void
}

/**
 * Name and kind of a thing the household owns — and, on create, its first
 * value point, because an asset with no point contributes nothing to net
 * worth and a create that quietly produced an invisible asset would read as
 * a failed save.
 */
export function AssetSettingsModal({ budgetId, asset, onClose, onDeleted }: Props) {
  const createAsset = useCreateAsset(budgetId)
  const updateAsset = useUpdateAsset(budgetId)
  const deleteAsset = useDeleteAsset(budgetId)

  const [name, setName] = useState(asset?.name ?? '')
  const [assetType, setAssetType] = useState<string>(asset?.asset_type ?? 'property')
  const [value, setValue] = useState('')
  const [asOf, setAsOf] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setError('Give it a name')
      return
    }
    setError(null)
    try {
      if (asset) {
        await updateAsset.mutateAsync({ id: asset.id, name: name.trim(), asset_type: assetType })
      } else {
        const parsed = value ? parseAmountInput(value) : NaN
        await createAsset.mutateAsync({
          name: name.trim(),
          asset_type: assetType,
          ...(isNaN(parsed) ? {} : { value: parsed, value_as_of: asOf || null }),
        })
      }
      onClose()
    } catch {
      setError('Could not save')
    }
  }

  async function handleDelete() {
    if (!asset) return
    const ok = await confirmAsync({
      title: `Stop tracking ${asset.name}?`,
      message:
        'Its value leaves net worth, and any debt linked to it is unlinked. The history is kept.',
      confirmLabel: 'Stop tracking',
      destructive: true,
    })
    if (!ok) return
    await deleteAsset.mutateAsync(asset.id)
    toast.success('No longer tracked')
    onClose()
    onDeleted?.()
  }

  const pending = createAsset.isPending || updateAsset.isPending

  return (
    <Dialog title={asset ? asset.name : 'Track an asset'} onClose={onClose} historyKey="asset">
      <form className="asset-modal" onSubmit={handleSubmit}>
        <label className="asset-modal__field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus={!asset} />
        </label>
        <label className="asset-modal__field">
          <span>Kind</span>
          <select value={assetType ?? 'other'} onChange={(e) => setAssetType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        {!asset && (
          <>
            <label className="asset-modal__field">
              <span>What is it worth?</span>
              <input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Optional — you can add this later"
              />
            </label>
            <label className="asset-modal__field">
              <span>As of (optional — defaults to today)</span>
              <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </label>
          </>
        )}
        {error && <p className="asset-modal__error">{error}</p>}
        <div className="asset-modal__actions">
          {asset && (
            <button
              type="button"
              className="asset-modal__delete"
              onClick={handleDelete}
              disabled={deleteAsset.isPending}
            >
              Stop tracking
            </button>
          )}
          <button type="button" className="asset-modal__cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="asset-modal__submit" disabled={pending}>
            {pending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}
