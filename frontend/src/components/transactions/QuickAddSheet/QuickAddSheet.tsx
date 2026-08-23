import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { AlertTriangle, Camera, ChevronRight, FileText, Images, MessageSquareText, Plus, Sparkles, Split, StickyNote, Trash2, X } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { SelectionSheet, type SelectionSheetOption } from '../../common/SelectionSheet/SelectionSheet'
import { ConfirmSheet } from '../../common/ConfirmSheet/ConfirmSheet'
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
import { useIsTouch } from '../../../hooks/useMediaQuery'
import { useFormatters } from '../../../hooks/useFormatters'
import { getCurrencySymbol } from '../../../utils/money'
import {
  centsToInputString,
  evaluateExpressionCents,
  expressionToCents,
  isAmountExpression,
  sumExpressionsToCents,
} from '../../../utils/amountExpression'
import { randomUUID } from '../../../utils/uuid'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { today, yesterday } from '../../../utils/dates'
import { hapticTick } from '../../../utils/haptics'
import './QuickAddSheet.css'
import { apiErrorMessage } from '../../../api/client'

type Direction = 'outflow' | 'inflow'

/** Sentinel for the plain Category row, so one picker can also serve the
 *  split legs, which address themselves by tempId. */
const SINGLE_CATEGORY = '__single__'

/** Two empty legs — a split of one is just a category. */
function freshSplits(): SplitDraft[] {
  return [
    { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
    { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
  ]
}

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
  const isTouch = useIsTouch()

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
  const [isSplit, setIsSplit] = useState(false)
  const [splits, setSplits] = useState<SplitDraft[]>(() => freshSplits())
  const [accountId, setAccountId] = useState<string | null>(null)
  const [date, setDate] = useState(today())
  const [memo, setMemo] = useState('')
  const [memoOpen, setMemoOpen] = useState(false)
  const [payeeSheetOpen, setPayeeSheetOpen] = useState(false)
  // Which category picker is open: SINGLE_CATEGORY for the plain row, or a
  // split leg's tempId. One sheet serves both — a second SelectionSheet
  // mounted over the first fights it for the viewport on a phone.
  const [categorySheetFor, setCategorySheetFor] = useState<string | null>(null)
  const [accountSheetOpen, setAccountSheetOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [nlEntryOpen, setNlEntryOpen] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  // Receipts whose upload failed. Held so the photo survives a bad
  // connection — clearing the file input would otherwise discard it.
  const [failedScans, setFailedScans] = useState<File[]>([])
  const [scanTotal, setScanTotal] = useState(0)
  const [scanDone, setScanDone] = useState(0)
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
    setIsSplit(false)
    setSplits(freshSplits())
    setMemo('')
    setMemoOpen(false)
    setDate(today())
    setSaving(false)
    setPendingFiles([])
    setDiscardOpen(false)
    setFailedScans([])
    setScanTotal(0)
    setScanDone(0)
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

  /**
   * Queue receipts for server-side extraction.
   *
   * Uploads sequentially rather than in one batch request: after downscaling
   * each file is small, so the round trips cost little, and one dropped
   * connection then loses one receipt instead of the whole stack. Anything
   * that fails is KEPT in `failedScans` so the user can retry it — the photo
   * is usually taken at a checkout on poor cellular, which is exactly when
   * silently discarding it would hurt most.
   */
  async function scanReceipts(files: File[]) {
    if (!accountId || files.length === 0) return

    const accepted: File[] = []
    for (const file of files) {
      if (!isAttachableFile(file)) {
        toast.error(`${file.name} is not an image or PDF`)
      } else if (file.size > 20 * 1024 * 1024) {
        toast.error(`${file.name} is too large (max 20MB)`)
      } else {
        accepted.push(file)
      }
    }
    if (accepted.length === 0) return

    setScanTotal(accepted.length)
    setScanDone(0)
    const failed: File[] = []
    let queued = 0
    let duplicates = 0

    for (const [i, original] of accepted.entries()) {
      setScanDone(i)
      try {
        // Downscale happens inside useSubmitReceipt now, for every caller.
        await submitReceipt.mutateAsync({ file: original, accountId })
        queued += 1
      } catch (err: unknown) {
        const response = (err as { response?: { status?: number } })?.response
        if (response?.status === 409) {
          // Already in the budget — nothing was lost, so don't offer a retry
          // that can only fail the same way.
          duplicates += 1
        } else {
          failed.push(original)
        }
      }
    }

    setScanTotal(0)
    setScanDone(0)
    setFailedScans(failed)

    if (queued > 0) {
      setLastAccountId(accountId)
      hapticTick()
      toast.success(
        queued === 1
          ? "Receipt queued — it'll show up in your transactions to review"
          : `${queued} receipts queued — they'll show up in your transactions to review`,
        { duration: 5000 }
      )
    }
    if (duplicates > 0) {
      toast(
        duplicates === 1
          ? "You've already added that receipt"
          : `${duplicates} of those receipts were already added`
      )
    }
    if (failed.length > 0) {
      toast.error(
        failed.length === 1
          ? "That receipt didn't upload — tap Retry to try again"
          : `${failed.length} receipts didn't upload — tap Retry to try again`
      )
      return // stay open so the retry affordance is reachable
    }
    closeQuickAdd()
  }

  // Expression-aware: "12.50+3.99" is valid the moment it's typed, no "=" needed
  const cents = expressionToCents(amount)
  const amountValid = !isNaN(cents) && cents > 0

  // Integer cents throughout — summing the legs as floats rejects valid splits
  // like 0.10 + 0.20. Same comparison the desktop editor makes.
  const splitCents = sumExpressionsToCents(splits.map((sp) => sp.amount))
  const remainingCents = (amountValid ? cents : 0) - splitCents
  const splitIsValid =
    !isSplit ||
    (amountValid &&
      remainingCents === 0 &&
      splits.every((sp) => {
        const legCents = expressionToCents(sp.amount)
        return sp.categoryId && !isNaN(legCents) && legCents > 0
      }))

  const canSave = amountValid && !!accountId && !saving && splitIsValid

  function updateSplit(tempId: string, data: Partial<Omit<SplitDraft, 'tempId'>>) {
    setSplits((prev) => prev.map((sp) => (sp.tempId === tempId ? { ...sp, ...data } : sp)))
  }

  function addSplit() {
    setSplits((prev) => [...prev, { tempId: randomUUID(), amount: '', categoryId: null, memo: '' }])
  }

  function removeSplit(tempId: string) {
    setSplits((prev) => (prev.length > 2 ? prev.filter((sp) => sp.tempId !== tempId) : prev))
  }

  /** Start a split from whatever is already on screen: the chosen category
   *  becomes the first leg, so tapping Split never throws away a pick. */
  function beginSplit() {
    hapticTick()
    const [first, ...rest] = freshSplits()
    setSplits([{ ...first, categoryId }, ...rest])
    setCategoryId(null)
    setIsSplit(true)
  }

  function cancelSplit() {
    setIsSplit(false)
    setSplits(freshSplits())
  }

  async function save(addAnother: boolean) {
    if (!canSave || !budgetId || !accountId) return
    const sign = direction === 'outflow' ? -1 : 1
    const signed = (cents / 100) * sign

    // Legs carry the categories when split, so the overspend check has to ask
    // about each of them rather than about a category the parent no longer has.
    const splitList = isSplit
      ? splits.map((sp) => ({
          amount: (expressionToCents(sp.amount) / 100) * sign,
          category_id: sp.categoryId ?? undefined,
          memo: sp.memo || undefined,
        }))
      : null
    const affected = splitList
      ? splitList
          .filter((sp) => sp.category_id)
          .map((sp) => ({ category_id: sp.category_id!, date, amount_delta: sp.amount }))
      : categoryId
        ? [{ category_id: categoryId, date, amount_delta: signed }]
        : []
    if (affected.length > 0) {
      const proceed = await confirmFutureOverspend(budgetId, affected, formatMoney)
      if (!proceed) return
    }
    setSaving(true)
    try {
      const txn = await createTxn.mutateAsync({
        account_id: accountId,
        date,
        amount: signed,
        payee_id: payeeId ?? undefined,
        // A split parent carries no category of its own; the legs do.
        category_id: splitList ? undefined : (categoryId ?? undefined),
        ...(splitList ? { splits: splitList } : {}),
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

      const where = isSplit
        ? ` · split ${splits.length} ways`
        : categoryName
          ? ` · ${categoryName}`
          : ''
      toast.success(
        `Added ${direction === 'outflow' ? '−' : ''}${formatMoney(cents / 100)}${where}`
      )
      hapticTick()
      if (addAnother) {
        setAmount('')
        setPayeeId(null)
        setCategoryId(null)
        setIsSplit(false)
        setSplits(freshSplits())
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
      toast.error(apiErrorMessage(err, 'Failed to add transaction'))
      setSaving(false)
    }
  }

  // Everything the user could have typed or picked. Account and date are
  // sticky across entries by design, so only a date moved off today counts.
  const isDirty =
    amount !== '' ||
    payeeId !== null ||
    categoryId !== null ||
    isSplit ||
    memo !== '' ||
    pendingFiles.length > 0 ||
    date !== today()

  // Runs before every dismissal path — close button, backdrop, Escape, swipe,
  // and the Android back gesture. Returning false holds the sheet open while
  // the discard confirmation is answered.
  function canClose() {
    if (!isDirty || saving) return true
    setDiscardOpen(true)
    return false
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
        canClose={canClose}
        closeLabel="Cancel"
        footer={
          <div className="quick-add__footer">
            <button
              className="quick-add__save-another press-scale"
              disabled={!canSave}
              onClick={() => save(true)}
            >
              Save & add another
            </button>
            <button className="quick-add__save press-scale" disabled={!canSave} onClick={() => save(false)}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        }
      >
        <div className="quick-add">
          <div className="quick-add__amount-block">
            {/* Autofocus only where there is no on-screen keyboard. On a phone
                the numpad opens over the sheet and buries Scan receipt /
                Describe it — the two things most likely to be wanted before an
                amount is typed. A label, not a div, so the whole 0.00 display
                raises the keypad now that focus isn't automatic. */}
            <label className={`quick-add__amount ${direction === 'outflow' ? 'quick-add__amount--out' : 'quick-add__amount--in'}`}>
              <span className="quick-add__amount-sign">
                {direction === 'outflow' ? '−' : '+'}
                {currencySymbol}
              </span>
              <AmountInput
                ref={amountInputRef}
                value={amount}
                onValueChange={setAmount}
                placeholder="0.00"
                autoFocus={!isTouch}
                enterKeyHint="done"
                aria-label="Amount"
                style={{ width: `${Math.max(4, amount.length + 1)}ch` }}
              />
            </label>
            {/* The mobile decimal keypad has no operator keys — these chips
                make receipt-summing ("12.50+3.99") possible on the phone.
                pointerdown is prevented so the chip never takes focus and the
                keyboard stays up. It must be pointerdown, not touchstart:
                cancelling touchstart suppresses the whole compatibility
                sequence including the click, which would break the chips
                outright on iOS. */}
            <div className="quick-add__calc-row" role="group" aria-label="Calculator">
              {(['+', '-', '*', '/'] as const).map((op) => (
                <button
                  key={op}
                  type="button"
                  className="quick-add__calc-btn"
                  aria-label={`Operator ${op}`}
                  onPointerDown={(e) => e.preventDefault()}
                  onClick={() => {
                  hapticTick()
                  setAmount((prev) => prev + op)
                }}
                >
                  {op === '*' ? '×' : op === '/' ? '÷' : op === '-' ? '−' : op}
                </button>
              ))}
              <button
                type="button"
                className="quick-add__calc-btn quick-add__calc-btn--eq"
                aria-label="Evaluate"
                onPointerDown={(e) => e.preventDefault()}
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
                onClick={() => {
                  hapticTick()
                  setDirection('outflow')
                }}
              >
                Spent
              </button>
              <button
                role="radio"
                aria-checked={direction === 'inflow'}
                className={`quick-add__direction-btn ${direction === 'inflow' ? 'quick-add__direction-btn--active' : ''}`}
                onClick={() => {
                  hapticTick()
                  setDirection('inflow')
                }}
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

            {isSplit ? (
              <div className="quick-add__split">
                <div className="quick-add__split-head">
                  <span className="quick-add__row-label">Split</span>
                  <button className="quick-add__split-cancel" onClick={cancelSplit}>
                    <X size={13} />
                    Cancel split
                  </button>
                </div>

                {splits.map((sp, i) => {
                  const legName = sp.categoryId
                    ? (categories.find((c) => c.id === sp.categoryId)?.name ?? '')
                    : ''
                  return (
                    <div key={sp.tempId} className="quick-add__split-leg">
                      <button
                        className="quick-add__split-category"
                        onClick={() => setCategorySheetFor(sp.tempId)}
                        aria-label={`Split ${i + 1} category`}
                      >
                        <span
                          className={`quick-add__row-value ${legName ? '' : 'quick-add__row-value--empty'}`}
                        >
                          {legName || 'Choose category'}
                        </span>
                        <ChevronRight size={15} className="quick-add__row-chevron" />
                      </button>
                      <AmountInput
                        className="quick-add__split-amount"
                        value={sp.amount}
                        onValueChange={(v) => updateSplit(sp.tempId, { amount: v })}
                        placeholder="0.00"
                        aria-label={`Split ${i + 1} amount`}
                      />
                      <button
                        className="quick-add__split-remove"
                        onClick={() => removeSplit(sp.tempId)}
                        disabled={splits.length <= 2}
                        aria-label={`Remove split ${i + 1}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )
                })}

                <div className="quick-add__split-foot">
                  <button className="quick-add__split-add" onClick={addSplit}>
                    <Plus size={13} />
                    Add split
                  </button>
                  <span
                    className={`quick-add__split-remaining ${
                      remainingCents === 0 ? 'quick-add__split-remaining--done' : ''
                    }`}
                    role="status"
                  >
                    {remainingCents === 0
                      ? 'Fully assigned'
                      : `${formatMoney(Math.abs(remainingCents) / 100)} ${
                          remainingCents > 0 ? 'left' : 'over'
                        }`}
                  </span>
                </div>
              </div>
            ) : (
              <div className="quick-add__row quick-add__row--category">
                <span className="quick-add__row-label">Category</span>
                <button
                  className="quick-add__row-pick"
                  onClick={() => setCategorySheetFor(SINGLE_CATEGORY)}
                  aria-label="Category"
                >
                  <span
                    className={`quick-add__row-value ${categoryName ? '' : 'quick-add__row-value--empty'}`}
                  >
                    {categoryName || 'Choose category'}
                  </span>
                  <ChevronRight size={16} className="quick-add__row-chevron" />
                </button>
                <button
                  className="quick-add__split-start"
                  onClick={beginSplit}
                  title="Split this across categories"
                >
                  <Split size={14} />
                  <span className="sr-only">Split across categories</span>
                </button>
              </div>
            )}

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
                  enterKeyHint="done"
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
            {/* AI entry paths lead; manual attach is the fallback row below.
                Scanning is gated on AI being CONFIGURED, not on the server
                answering a ping right now — the upload is queued and the
                worker retries, so a server that is briefly down or busy must
                not remove the user's ability to hand off a receipt and walk
                away. "Describe it" is synchronous and genuinely does need a
                live server, so it keeps the stricter gate. */}
            {aiStatus.data?.enabled && (
              <div className="quick-add__scan-row">
                <button
                  className="quick-add__scan-btn"
                  onClick={() => aiScanInputRef.current?.click()}
                  disabled={submitReceipt.isPending || !accountId}
                  title="AI reads the receipt and drafts the transaction for review"
                >
                  <Sparkles size={15} />
                  {scanTotal > 1
                    ? `Queuing ${scanDone + 1} of ${scanTotal}…`
                    : submitReceipt.isPending
                      ? 'Queuing…'
                      : 'Scan receipt'}
                </button>
                {aiStatus.data?.available && (
                  <button
                    className="quick-add__scan-btn"
                    onClick={() => setNlEntryOpen(true)}
                    title="Type or dictate the transaction — AI drafts it for you"
                  >
                    <MessageSquareText size={15} />
                    Describe it
                  </button>
                )}
              </div>
            )}
            {failedScans.length > 0 && (
              <div className="quick-add__scan-failed" role="status">
                <AlertTriangle size={14} />
                <span>
                  {failedScans.length === 1
                    ? "1 receipt didn't upload"
                    : `${failedScans.length} receipts didn't upload`}
                </span>
                <button
                  type="button"
                  className="quick-add__scan-retry"
                  onClick={() => {
                    const retrying = failedScans
                    setFailedScans([])
                    void scanReceipts(retrying)
                  }}
                >
                  Retry
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
            {/* No capture attr: the OS sheet offers both camera and library.
                `multiple` so a stack of receipts is one trip through the sheet
                — the model still processes them one at a time, but the user
                shouldn't have to. */}
            <input
              ref={aiScanInputRef}
              type="file"
              accept={ATTACHMENT_ACCEPT}
              multiple
              onChange={(e) => {
                void scanReceipts(Array.from(e.target.files ?? []))
                e.target.value = ''
              }}
              style={{ display: 'none' }}
            />
          </div>
        </div>
      </BottomSheet>

      <ConfirmSheet
        open={discardOpen}
        title="Discard this transaction?"
        message="What you've entered won't be saved."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        destructive
        onConfirm={() => {
          setDiscardOpen(false)
          closeQuickAdd()
        }}
        onCancel={() => setDiscardOpen(false)}
      />

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
        open={categorySheetFor !== null}
        onClose={() => setCategorySheetFor(null)}
        title={categorySheetFor === SINGLE_CATEGORY ? 'Category' : 'Split category'}
        options={categoryOptions}
        value={
          categorySheetFor === SINGLE_CATEGORY
            ? categoryId
            : (splits.find((sp) => sp.tempId === categorySheetFor)?.categoryId ?? null)
        }
        onChange={(id) => {
          if (categorySheetFor === SINGLE_CATEGORY) setCategoryId(id)
          else if (categorySheetFor) updateSplit(categorySheetFor, { categoryId: id })
        }}
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
