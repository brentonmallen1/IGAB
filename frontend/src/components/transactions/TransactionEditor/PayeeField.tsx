import { useEffect, useRef, useState } from 'react'
import type { Account, Payee } from '../../../types'
import { payeeChoices } from './payeeChoices'

interface Props {
  value: string
  /** Typing: the box's text, which no longer names a picked payee. */
  onType: (value: string) => void
  payees: Payee[]
  accounts: Account[]
  /** The accounts this row may transfer to. */
  targets: Account[]
  /** What the box reads while it shows a transfer's destination, or null. */
  shownTransferLabel: string | null
  /** False where the transfer toggle is locked (a reconciled row): picking an
   *  account would turn it on. */
  offerTransfers: boolean
  onPickPayee: (payee: Payee) => void
  onPickTransfer: (accountId: string) => void
}

/** The editor's Payee field: a search box over payees, and the accounts a
 *  transfer could go to under their own heading (`payeeChoices`). */
export function PayeeField({
  value,
  onType,
  payees,
  accounts,
  targets,
  shownTransferLabel,
  offerTransfers,
  onPickPayee,
  onPickTransfer,
}: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const choices = payeeChoices({ query: value, payees, accounts, targets, shownTransferLabel })
  const transfers = offerTransfers ? choices.transfers : []

  return (
    <div className="txn-editor__field">
      <label className="txn-editor__label">Payee</label>
      <div className="txn-editor__payee-wrap" ref={ref}>
        <input
          type="text"
          className="txn-editor__input"
          value={value}
          onChange={(e) => {
            onType(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search or enter payee..."
          autoComplete="off"
        />
        {open && (choices.payees.length > 0 || transfers.length > 0) && (
          <div className="txn-editor__payee-dropdown">
            {choices.payees.map((p) => (
              <button
                key={p.id}
                type="button"
                className="txn-editor__payee-option"
                onMouseDown={() => {
                  setOpen(false)
                  onPickPayee(p)
                }}
              >
                {p.name}
              </button>
            ))}
            {transfers.length > 0 && (
              <div role="group" aria-label="Transfer to account">
                <div className="txn-editor__payee-heading">Transfer to account</div>
                {transfers.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className="txn-editor__payee-option"
                    onMouseDown={() => {
                      setOpen(false)
                      onPickTransfer(a.id)
                    }}
                  >
                    {a.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
