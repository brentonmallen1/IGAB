import { useState } from 'react'
import { Home, TrendingUp } from 'lucide-react'
import { Dialog } from '../common/Dialog/Dialog'
import { AddAccountModal } from '../accounts/AddAccountModal'
import { AssetSettingsModal } from './AssetSettingsModal'
import { useAppStore } from '../../stores/appStore'
import './AddAssetFlow.css'

interface Props {
  onClose: () => void
}

type Step = 'choose' | 'balance' | 'value'

/**
 * The one way in to adding something the household owns.
 *
 * "Asset" means two different things here, and they were reached by two
 * different doors with no word about the difference: the sidebar's + opened
 * the New Account form, and the Assets page's button opened the valued-asset
 * form — a pared-down dialog with no type picker that read like a broken copy
 * of the first. Both were right about what they made; neither said so.
 *
 * An account has transactions and a balance that is their sum (a brokerage, a
 * 401k). A valued asset has no transactions, only a worth stated over time (a
 * home, a vehicle) — deliberately not an account, see `Asset` in db/models.py.
 * Every entry point opens this, so the choice is asked once, in words, before
 * either form.
 */
export function AddAssetFlow({ onClose }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [step, setStep] = useState<Step>('choose')

  if (step === 'balance') return <AddAccountModal initialTypeKey="investment" onClose={onClose} />
  if (step === 'value' && budgetId) {
    return <AssetSettingsModal budgetId={budgetId} asset={null} onClose={onClose} />
  }

  return (
    <Dialog title="Add an asset" onClose={onClose} historyKey="add-asset">
      <div className="add-asset">
        <button type="button" className="add-asset__option" onClick={() => setStep('balance')}>
          <TrendingUp size={18} aria-hidden className="add-asset__icon" />
          <span className="add-asset__text">
            <span className="add-asset__name">Track its balance</span>
            <span className="add-asset__desc">
              An account with transactions — a brokerage, 401k, HSA or crypto wallet. Its balance is
              the sum of what moves in and out. You choose its type next.
            </span>
          </span>
        </button>
        <button
          type="button"
          className="add-asset__option"
          onClick={() => setStep('value')}
          disabled={!budgetId}
        >
          <Home size={18} aria-hidden className="add-asset__icon" />
          <span className="add-asset__text">
            <span className="add-asset__name">Track its value</span>
            <span className="add-asset__desc">
              Something you own and put a worth on yourself — a home or a vehicle. No transactions:
              you update its value when it changes, and a loan can be linked to show equity.
            </span>
          </span>
        </button>
      </div>
    </Dialog>
  )
}
