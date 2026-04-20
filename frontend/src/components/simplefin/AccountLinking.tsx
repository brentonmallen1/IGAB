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
                onChange={async (e) => {
                  if (e.target.value) {
                    await link.mutateAsync(e.target.value)
                    setOpen(false)
                  }
                }}
              >
                <option value="">Select account…</option>
                {remoteAccounts.map((ra) => (
                  <option key={ra.id} value={ra.id}>
                    {ra.name ?? ra.id}
                  </option>
                ))}
              </select>
              <button className="acc-linking__btn" onClick={() => setOpen(false)}>
                Cancel
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
