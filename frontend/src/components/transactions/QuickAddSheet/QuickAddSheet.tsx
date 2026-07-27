import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { Camera, ChevronRight, Images, StickyNote, X } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { SelectionSheet, type SelectionSheetOption } from '../../common/SelectionSheet/SelectionSheet'
import { useCreateTransaction, usePayees } from '../../../api/transactions'
import { uploadFilesToTransaction } from '../../../api/attachments'
import { useCreatePayee, useNearbyPayees } from '../../../api/payees'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useAccounts } from '../../../api/accounts'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useCurrentPosition } from '../../../hooks/useCurrentPosition'
import { useFormatters } from '../../../hooks/useFormatters'
import { toCents } from '../../../utils/money'
import { today } from '../../../utils/dates'
import './QuickAddSheet.css'

type Direction = 'outflow' | 'inflow'

/**
 * The bottom-nav ＋ flow: fastest possible transaction entry at the checkout
 * line. Amount first, payee memory prefills the category, account sticks
 * across entries.
 */
export function QuickAddSheet() {
  const { formatMoney } = useFormatters()
  const open = useUIStore((s) => s.quickAddOpen)
  const closeQuickAdd = useUIStore((s) => s.closeQuickAdd)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const lastAccountId = useAppStore((s) => s.lastQuickAddAccountId)
  const setLastAccountId = useAppStore((s) => s.setLastQuickAddAccountId)
  const locationEnabled = useAppStore((s) => s.locationEnabled)

  // Opt-in: one-shot fix while the sheet is open; silent null on denial/timeout
  const coords = useCurrentPosition(open && locationEnabled)

  const { data: payees = [] } = usePayees(open ? budgetId : null)
  const { data: categories = [] } = useCategories(open ? budgetId : null)
  const { data: categoryGroups = [] } = useCategoryGroups(open ? budgetId : null)
  const { data: accounts = [] } = useAccounts(open ? budgetId : null)
  const createTxn = useCreateTransaction(budgetId ?? '')
  const createPayee = useCreatePayee(budgetId ?? '')
  const { data: nearbyPayees = [] } = useNearbyPayees(open ? budgetId : null, coords)

  const [amount, setAmount] = useState('')
  const [direction, setDirection] = useState<Direction>('outflow')
  const [payeeId, setPayeeId] = useState<string | null>(null)
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [accountId, setAccountId] = useState<string | null>(null)
  const [date, setDate] = useState(today())
  const [memo, setMemo] = useState('')
  const [memoOpen, setMemoOpen] = useState(false)
  const [payeeSheetOpen, setPayeeSheetOpen] = useState(false)
  const [categorySheetOpen, setCategorySheetOpen] = useState(false)
  const [accountSheetOpen, setAccountSheetOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const libraryInputRef = useRef<HTMLInputElement>(null)

  // Object URLs for receipt previews, revoked when files change/unmount
  const previews = useMemo(() => pendingFiles.map((f) => URL.createObjectURL(f)), [pendingFiles])
  useEffect(() => {
    return () => previews.forEach((url) => URL.revokeObjectURL(url))
  }, [previews])

  const openAccounts = useMemo(() => accounts.filter((a) => !a.is_closed), [accounts])
  const defaultAccountId = useMemo(() => {
    if (lastAccountId && openAccounts.some((a) => a.id === lastAccountId)) return lastAccountId
    return openAccounts.find((a) => a.on_budget)?.id ?? openAccounts[0]?.id ?? null
  }, [lastAccountId, openAccounts])

  // Fresh entry each time the sheet opens; account and date are sticky choices
  useEffect(() => {
    if (!open) return
    setAmount('')
    setDirection('outflow')
    setPayeeId(null)
    setCategoryId(null)
    setMemo('')
    setMemoOpen(false)
    setDate(today())
    setSaving(false)
    setPendingFiles([])
  }, [open])

  useEffect(() => {
    if (open && accountId === null && defaultAccountId) setAccountId(defaultAccountId)
  }, [open, accountId, defaultAccountId])

  const payeeOptions = useMemo<SelectionSheetOption[]>(
    () => payees.filter((p) => !p.transfer_account_id).map((p) => ({ id: p.id, label: p.name })),
    [payees]
  )

  const nearbyOptions = useMemo<SelectionSheetOption[]>(
    () =>
      nearbyPayees.map((p) => ({
        id: p.id,
        label: p.name,
        hint: p.distance_m < 950 ? `~${Math.round(p.distance_m / 10) * 10} m` : `~${(p.distance_m / 1000).toFixed(1)} km`,
      })),
    [nearbyPayees]
  )

  const categoryOptions = useMemo<SelectionSheetOption[]>(() => {
    const groupName = new Map(categoryGroups.map((g) => [g.id, g.name]))
    return categories
      .filter((c) => !c.is_hidden && !c.linked_account_id)
      .map((c) => ({ id: c.id, label: c.name, group: groupName.get(c.category_group_id) ?? '' }))
  }, [categories, categoryGroups])

  const accountOptions = useMemo<SelectionSheetOption[]>(
    () =>
      openAccounts.map((a) => ({
        id: a.id,
        label: a.name,
        group: a.on_budget ? 'Budget accounts' : 'Tracking',
      })),
    [openAccounts]
  )

  const payeeName = payeeId ? (payees.find((p) => p.id === payeeId)?.name ?? '') : ''
  const categoryName = categoryId
    ? (categories.find((c) => c.id === categoryId)?.name ?? '')
    : ''
  const accountName = accountId ? (accounts.find((a) => a.id === accountId)?.name ?? '') : ''

  function handlePayeePicked(id: string | null) {
    setPayeeId(id)
    if (id) {
      // Payee memory: prefill the learned default category, still overridable.
      // Nearby entries carry their own default_category_id from the endpoint.
      const defaultCategory =
        payees.find((p) => p.id === id)?.default_category_id ??
        nearbyPayees.find((p) => p.id === id)?.default_category_id
      if (defaultCategory && !categoryId) {
        setCategoryId(defaultCategory)
      }
    }
  }

  function addFiles(list: FileList | null) {
    if (!list) return
    const accepted: File[] = []
    for (const file of Array.from(list)) {
      if (!file.type.startsWith('image/')) {
        toast.error(`${file.name} is not an image`)
        continue
      }
      if (file.size > 20 * 1024 * 1024) {
        toast.error(`${file.name} is too large (max 20MB)`)
        continue
      }
      accepted.push(file)
    }
    if (accepted.length) setPendingFiles((prev) => [...prev, ...accepted])
  }

  const cents = toCents(amount)
  const amountValid = !isNaN(cents) && cents > 0
  const canSave = amountValid && !!accountId && !saving

  async function save(addAnother: boolean) {
    if (!canSave || !budgetId || !accountId) return
    setSaving(true)
    const signed = (cents / 100) * (direction === 'outflow' ? -1 : 1)
    try {
      const txn = await createTxn.mutateAsync({
        account_id: accountId,
        date,
        amount: signed,
        payee_id: payeeId ?? undefined,
        category_id: categoryId ?? undefined,
        memo: memo || undefined,
        cleared: 'uncleared',
        approved: true,
        ...(coords ? { latitude: coords.latitude, longitude: coords.longitude } : {}),
      })
      setLastAccountId(accountId)

      // Transaction first, receipts second — the money record always wins.
      // Failed photos stay in the camera roll; retry from the editor.
      if (pendingFiles.length > 0) {
        const { failed } = await uploadFilesToTransaction(txn.id, pendingFiles)
        if (failed.length > 0) {
          toast.error(
            `Saved. ${failed.length} of ${pendingFiles.length} receipt${pendingFiles.length !== 1 ? 's' : ''} failed to upload — retry from the transaction.`,
            { duration: 6000 }
          )
        }
      }

      toast.success(
        `Added ${direction === 'outflow' ? '−' : ''}${formatMoney(cents / 100)}${categoryName ? ` · ${categoryName}` : ''}`
      )
      if (addAnother) {
        setAmount('')
        setPayeeId(null)
        setCategoryId(null)
        setMemo('')
        setMemoOpen(false)
        setPendingFiles([])
        setSaving(false)
      } else {
        closeQuickAdd()
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Failed to add transaction')
      setSaving(false)
    }
  }

  if (!budgetId) return null

  return (
    <>
      <BottomSheet
        open={open}
        onClose={closeQuickAdd}
        title="Add Transaction"
        height="full"
        historyKey="quick-add"
        footer={
          <div className="quick-add__footer">
            <button
              className="quick-add__save-another"
              disabled={!canSave}
              onClick={() => save(true)}
            >
              Save & add another
            </button>
            <button className="quick-add__save" disabled={!canSave} onClick={() => save(false)}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        }
      >
        <div className="quick-add">
          <div className="quick-add__amount-block">
            <div className={`quick-add__amount ${direction === 'outflow' ? 'quick-add__amount--out' : 'quick-add__amount--in'}`}>
              <span className="quick-add__amount-sign">{direction === 'outflow' ? '−$' : '+$'}</span>
              <input
                type="text"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                autoFocus
                aria-label="Amount"
              />
            </div>
            <div className="quick-add__direction" role="radiogroup" aria-label="Direction">
              <button
                role="radio"
                aria-checked={direction === 'outflow'}
                className={`quick-add__direction-btn ${direction === 'outflow' ? 'quick-add__direction-btn--active' : ''}`}
                onClick={() => setDirection('outflow')}
              >
                Spent
              </button>
              <button
                role="radio"
                aria-checked={direction === 'inflow'}
                className={`quick-add__direction-btn ${direction === 'inflow' ? 'quick-add__direction-btn--active' : ''}`}
                onClick={() => setDirection('inflow')}
              >
                Received
              </button>
            </div>
          </div>

          <div className="quick-add__rows">
            <button className="quick-add__row" onClick={() => setPayeeSheetOpen(true)}>
              <span className="quick-add__row-label">Payee</span>
              <span className={`quick-add__row-value ${payeeName ? '' : 'quick-add__row-value--empty'}`}>
                {payeeName || 'Choose payee'}
              </span>
              <ChevronRight size={16} className="quick-add__row-chevron" />
            </button>

            <button className="quick-add__row" onClick={() => setCategorySheetOpen(true)}>
              <span className="quick-add__row-label">Category</span>
              <span className={`quick-add__row-value ${categoryName ? '' : 'quick-add__row-value--empty'}`}>
                {categoryName || 'Choose category'}
              </span>
              <ChevronRight size={16} className="quick-add__row-chevron" />
            </button>

            <button className="quick-add__row" onClick={() => setAccountSheetOpen(true)}>
              <span className="quick-add__row-label">Account</span>
              <span className={`quick-add__row-value ${accountName ? '' : 'quick-add__row-value--empty'}`}>
                {accountName || 'Choose account'}
              </span>
              <ChevronRight size={16} className="quick-add__row-chevron" />
            </button>

            <div className="quick-add__row quick-add__row--date">
              <span className="quick-add__row-label">Date</span>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                aria-label="Date"
              />
            </div>

            {memoOpen ? (
              <div className="quick-add__row quick-add__row--memo">
                <span className="quick-add__row-label">Memo</span>
                <input
                  type="text"
                  value={memo}
                  onChange={(e) => setMemo(e.target.value)}
                  placeholder="Optional note…"
                  autoFocus
                  aria-label="Memo"
                />
              </div>
            ) : (
              <button className="quick-add__add-memo" onClick={() => setMemoOpen(true)}>
                <StickyNote size={14} />
                Add memo
              </button>
            )}
          </div>

          <div className="quick-add__receipts">
            {previews.length > 0 && (
              <div className="quick-add__receipt-thumbs">
                {previews.map((url, i) => (
                  <div key={url} className="quick-add__receipt-thumb">
                    <img src={url} alt={`Receipt ${i + 1}`} />
                    <button
                      onClick={() => setPendingFiles((prev) => prev.filter((_, idx) => idx !== i))}
                      aria-label={`Remove receipt ${i + 1}`}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="quick-add__receipt-actions">
              <button onClick={() => cameraInputRef.current?.click()}>
                <Camera size={15} />
                Take photo
              </button>
              <button onClick={() => libraryInputRef.current?.click()}>
                <Images size={15} />
                Add from library
              </button>
            </div>
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
              style={{ display: 'none' }}
            />
            <input
              ref={libraryInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
              style={{ display: 'none' }}
            />
          </div>
        </div>
      </BottomSheet>

      <SelectionSheet
        open={payeeSheetOpen}
        onClose={() => setPayeeSheetOpen(false)}
        title="Payee"
        options={payeeOptions}
        value={payeeId}
        onChange={handlePayeePicked}
        topSection={nearbyOptions.length > 0 ? { label: 'Nearby', options: nearbyOptions } : undefined}
        onCreateNew={async (name) => {
          const payee = await createPayee.mutateAsync(name)
          // Mirror handlePayeePicked's memory prefill for brand-new payees
          setPayeeId(payee.id)
          if (payee.default_category_id && !categoryId) setCategoryId(payee.default_category_id)
          return { id: payee.id, label: payee.name }
        }}
        placeholder="Search or create payee…"
      />

      <SelectionSheet
        open={categorySheetOpen}
        onClose={() => setCategorySheetOpen(false)}
        title="Category"
        options={categoryOptions}
        value={categoryId}
        onChange={setCategoryId}
        allowNone
        noneLabel="No category"
        placeholder="Search categories…"
      />

      <SelectionSheet
        open={accountSheetOpen}
        onClose={() => setAccountSheetOpen(false)}
        title="Account"
        options={accountOptions}
        value={accountId}
        onChange={(id) => id && setAccountId(id)}
        placeholder="Search accounts…"
      />
    </>
  )
}
