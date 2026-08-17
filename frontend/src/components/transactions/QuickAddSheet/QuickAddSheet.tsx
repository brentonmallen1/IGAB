import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { Camera, ChevronRight, FileText, Images, MessageSquareText, Sparkles, StickyNote, X } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { SelectionSheet, type SelectionSheetOption } from '../../common/SelectionSheet/SelectionSheet'
import { useCreateTransaction } from '../../../api/transactions'
import { confirmFutureOverspend } from '../../../api/budgets'
import { ATTACHMENT_ACCEPT, isAttachableFile, uploadFilesToTransaction } from '../../../api/attachments'
import { useAIStatus } from '../../../api/ai'
import { useSubmitReceipt } from '../../../api/aiJobs'
import { NLQuickEntry } from '../../ai/NLQuickEntry'
import { useCreatePayee, useNearbyPayees, usePayees } from '../../../api/payees'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useAccounts } from '../../../api/accounts'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useCurrentPosition } from '../../../hooks/useCurrentPosition'
import { useFormatters } from '../../../hooks/useFormatters'
import { getCurrencySymbol } from '../../../utils/money'
import {
  centsToInputString,
  evaluateExpressionCents,
  expressionToCents,
  isAmountExpression,
} from '../../../utils/amountExpression'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { today, yesterday } from '../../../utils/dates'
import { hapticTick } from '../../../utils/haptics'
import './QuickAddSheet.css'

type Direction = 'outflow' | 'inflow'

/**
 * The bottom-nav ＋ flow: fastest possible transaction entry at the checkout
 * line. Amount first, payee memory prefills the category, account sticks
 * across entries.
 */
export function QuickAddSheet() {
  const { formatMoney, settings } = useFormatters()
  const currencySymbol = getCurrencySymbol(settings.currencyCode).trim()
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
  const aiStatus = useAIStatus()
  const submitReceipt = useSubmitReceipt(budgetId ?? '')

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
  const [nlEntryOpen, setNlEntryOpen] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const libraryInputRef = useRef<HTMLInputElement>(null)
  const aiScanInputRef = useRef<HTMLInputElement>(null)
  const amountInputRef = useRef<HTMLInputElement>(null)

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

  // Most recently used payees — the checkout-line shortlist. Nearby (GPS) wins
  // the top slot when available; recent covers the no-location case.
  const recentOptions = useMemo<SelectionSheetOption[]>(() => {
    const nearbyIds = new Set(nearbyPayees.map((p) => p.id))
    return payees
      .filter((p) => !p.transfer_account_id && p.last_used && !nearbyIds.has(p.id))
      .sort((a, b) => b.last_used!.localeCompare(a.last_used!))
      .slice(0, 6)
      .map((p) => ({ id: p.id, label: p.name }))
  }, [payees, nearbyPayees])

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
      if (!isAttachableFile(file)) {
        toast.error(`${file.name} is not an image or PDF`)
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

  async function scanReceipt(list: FileList | null) {
    const file = list?.[0]
    if (!file || !accountId) return
    if (!isAttachableFile(file)) {
      toast.error(`${file.name} is not an image or PDF`)
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error(`${file.name} is too large (max 20MB)`)
      return
    }
    try {
      await submitReceipt.mutateAsync({ file, accountId })
      setLastAccountId(accountId)
      toast.success("Receipt queued — it'll appear for review shortly", { duration: 5000 })
      hapticTick()
      closeQuickAdd()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Failed to queue receipt')
    }
  }

  // Expression-aware: "12.50+3.99" is valid the moment it's typed, no "=" needed
  const cents = expressionToCents(amount)
  const amountValid = !isNaN(cents) && cents > 0
  const canSave = amountValid && !!accountId && !saving

  async function save(addAnother: boolean) {
    if (!canSave || !budgetId || !accountId) return
    const signed = (cents / 100) * (direction === 'outflow' ? -1 : 1)
    if (categoryId) {
      const proceed = await confirmFutureOverspend(
        budgetId,
        [{ category_id: categoryId, date, amount_delta: signed }],
        formatMoney
      )
      if (!proceed) return
    }
    setSaving(true)
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
      hapticTick()
      if (addAnother) {
        setAmount('')
        setPayeeId(null)
        setCategoryId(null)
        setMemo('')
        setMemoOpen(false)
        setPendingFiles([])
        setSaving(false)
        // Keep the keyboard up for rapid-fire entry — refocus after the reset renders
        requestAnimationFrame(() => amountInputRef.current?.focus())
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
              <span className="quick-add__amount-sign">
                {direction === 'outflow' ? '−' : '+'}
                {currencySymbol}
              </span>
              <AmountInput
                ref={amountInputRef}
                value={amount}
                onValueChange={setAmount}
                placeholder="0.00"
                autoFocus
                aria-label="Amount"
                style={{ width: `${Math.max(4, amount.length + 1)}ch` }}
              />
            </div>
            {/* The mobile decimal keypad has no operator keys — these chips
                make receipt-summing ("12.50+3.99") possible on the phone.
                onMouseDown is prevented so tapping never dismisses the keyboard. */}
            <div className="quick-add__calc-row" role="group" aria-label="Calculator">
              {(['+', '-', '*', '/'] as const).map((op) => (
                <button
                  key={op}
                  type="button"
                  className="quick-add__calc-btn"
                  aria-label={`Operator ${op}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setAmount((prev) => prev + op)}
                >
                  {op === '*' ? '×' : op === '/' ? '÷' : op === '-' ? '−' : op}
                </button>
              ))}
              <button
                type="button"
                className="quick-add__calc-btn quick-add__calc-btn--eq"
                aria-label="Evaluate"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  if (!isAmountExpression(amount)) return
                  const evaluated = evaluateExpressionCents(amount)
                  if (evaluated !== null && evaluated >= 0) setAmount(centsToInputString(evaluated))
                }}
              >
                =
              </button>
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
              <div className="quick-add__date-chips" role="group" aria-label="Quick date">
                <button
                  className={`quick-add__date-chip ${date === today() ? 'quick-add__date-chip--active' : ''}`}
                  onClick={() => setDate(today())}
                >
                  Today
                </button>
                <button
                  className={`quick-add__date-chip ${date === yesterday() ? 'quick-add__date-chip--active' : ''}`}
                  onClick={() => setDate(yesterday())}
                >
                  Yesterday
                </button>
              </div>
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
                    {pendingFiles[i]?.type === 'application/pdf' ? (
                      <div className="quick-add__receipt-thumb-pdf" title={pendingFiles[i].name}>
                        <FileText size={18} />
                        <span>PDF</span>
                      </div>
                    ) : (
                      <img src={url} alt={`Receipt ${i + 1}`} loading="lazy" />
                    )}
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
            {/* AI entry paths lead; manual attach is the fallback row below */}
            {aiStatus.data?.available && (
              <div className="quick-add__scan-row">
                <button
                  className="quick-add__scan-btn"
                  onClick={() => aiScanInputRef.current?.click()}
                  disabled={submitReceipt.isPending || !accountId}
                  title="AI reads the receipt and drafts the transaction for review"
                >
                  <Sparkles size={15} />
                  {submitReceipt.isPending ? 'Queuing…' : 'Scan receipt'}
                </button>
                <button
                  className="quick-add__scan-btn"
                  onClick={() => setNlEntryOpen(true)}
                  title="Type or dictate the transaction — AI drafts it for you"
                >
                  <MessageSquareText size={15} />
                  Describe it
                </button>
              </div>
            )}
            <div className="quick-add__receipt-actions">
              <button onClick={() => cameraInputRef.current?.click()}>
                <Camera size={15} />
                Attach photo
              </button>
              <button onClick={() => libraryInputRef.current?.click()}>
                <Images size={15} />
                Attach from library
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
              accept={ATTACHMENT_ACCEPT}
              multiple
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
              style={{ display: 'none' }}
            />
            {/* No capture attr: the OS sheet offers both camera and library */}
            <input
              ref={aiScanInputRef}
              type="file"
              accept={ATTACHMENT_ACCEPT}
              onChange={(e) => {
                void scanReceipt(e.target.files)
                e.target.value = ''
              }}
              style={{ display: 'none' }}
            />
          </div>
        </div>
      </BottomSheet>

      {nlEntryOpen && budgetId && (
        <NLQuickEntry
          budgetId={budgetId}
          accountId={accountId}
          onClose={() => {
            setNlEntryOpen(false)
            closeQuickAdd()
          }}
        />
      )}

      <SelectionSheet
        open={payeeSheetOpen}
        onClose={() => setPayeeSheetOpen(false)}
        title="Payee"
        options={payeeOptions}
        value={payeeId}
        onChange={handlePayeePicked}
        topSection={[
          { label: 'Nearby', options: nearbyOptions },
          { label: 'Recent', options: recentOptions },
        ]}
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
