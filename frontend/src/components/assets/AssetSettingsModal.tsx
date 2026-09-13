import { useState } from 'react'
import toast from 'react-hot-toast'
import { useCreateAsset, useDeleteAsset, useUpdateAsset, type Asset } from '../../api/assets'
import { confirmAsync } from '../../stores/confirmStore'
import { parseAmountInput } from '../../utils/money'
import { Dialog } from '../common/Dialog/Dialog'

const TYPES = [
  { value: 'property', label: 'Property' },
  { value: 'vehicle', label: 'Vehicle' },
  { value: 'other', label: 'Something else' },
] as const

const FORM_ID = 'asset-settings-form'

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
    <Dialog
      title={asset ? asset.name : "Track an asset's value"}
      onClose={onClose}
      historyKey="asset"
      footer={
        <div className="dialog-actions">
          {asset && (
            <button
              type="button"
              className="dialog-btn dialog-btn--danger"
              onClick={handleDelete}
              disabled={deleteAsset.isPending}
            >
              Stop tracking
            </button>
          )}
          {error && <span className="dialog-form__error">{error}</span>}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            {/* The footer is pinned outside the form, so the submit button
                reaches it by id rather than by containment. */}
            <button
              type="submit"
              form={FORM_ID}
              className="dialog-btn dialog-btn--primary"
              disabled={pending}
            >
              {pending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      }
    >
      <form id={FORM_ID} className="dialog-form" onSubmit={handleSubmit}>
        <label className="dialog-form__field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus={!asset} />
        </label>
        <label className="dialog-form__field">
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
            <label className="dialog-form__field">
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
            <label className="dialog-form__field">
              <span>As of (optional — defaults to today)</span>
              <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </label>
          </>
        )}
      </form>
    </Dialog>
  )
}
