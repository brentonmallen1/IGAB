import { useState } from 'react'
import {
  useLinkSimpleFINAccount,
  useSimpleFINRemoteAccounts,
  useUnlinkSimpleFINAccount,
} from '../../api/simplefin'
import type { Account } from '../../types'
import './AccountLinking.css'

interface Props {
  account: Account
  connectionId: string | null
}

export function AccountLinking({ account, connectionId }: Props) {
  const [open, setOpen] = useState(false)
  const [linkError, setLinkError] = useState<string | null>(null)
  const { data: remoteAccounts = [] } = useSimpleFINRemoteAccounts(open ? connectionId : null)
  const link = useLinkSimpleFINAccount(account.id)
  const unlink = useUnlinkSimpleFINAccount(account.id)

  const isLinked = !!account.simplefin_account_id

  if (!connectionId) return null

  return (
    <div className="acc-linking">
      {isLinked ? (
        <div className="acc-linking__linked">
          <span className="acc-linking__tag">Linked: {account.simplefin_account_id}</span>
          <button
            className="acc-linking__btn acc-linking__btn--danger"
            onClick={() => unlink.mutate()}
            disabled={unlink.isPending}
          >
            Unlink
          </button>
        </div>
      ) : (
        <>
          {!open ? (
            <button className="acc-linking__btn" onClick={() => setOpen(true)}>
              Link to SimpleFIN
            </button>
          ) : (
            <div className="acc-linking__picker">
              <select
                className="acc-linking__select"
                defaultValue=""
                disabled={link.isPending}
                onChange={async (e) => {
                  if (!e.target.value) return
                  setLinkError(null)
                  const selected = remoteAccounts.find((ra) => ra.id === e.target.value)
                  try {
                    await link.mutateAsync({ id: e.target.value, name: selected?.name ?? null })
                  } catch {
                    setLinkError('Failed to link account — please try again')
                  }
                }}
              >
                <option value="">
                  {link.isPending ? 'Linking…' : 'Select account…'}
                </option>
                {remoteAccounts.map((ra) => (
                  <option key={ra.id} value={ra.id}>
                    {ra.name ?? ra.id}
                  </option>
                ))}
              </select>
              <button className="acc-linking__btn" onClick={() => { setOpen(false); setLinkError(null) }}>
                Cancel
              </button>
              {linkError && <span className="acc-linking__error">{linkError}</span>}
            </div>
          )}
        </>
      )}
    </div>
  )
}
