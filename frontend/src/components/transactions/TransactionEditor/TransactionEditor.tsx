import { useState, useRef, useEffect, useMemo } from 'react'
import { X, Trash2, Sparkles, Split, Plus, AlertTriangle, ChevronDown, ChevronUp, Paperclip } from 'lucide-react'
import { AttachmentPanel } from '../../attachments/AttachmentPanel'
import { ReceiptPane } from '../../ai/ReceiptPane'
import {
  useCreateTransaction,
  useUpdateTransaction,
  useDeleteTransaction,
  useConvertToSplit,
  usePayees,
  useSimilarTransactions,
} from '../../../api/transactions'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useAccounts } from '../../../api/accounts'
import { confirmFutureOverspend, type OverspendProbe } from '../../../api/budgets'
import { useAIStatus, useSuggestCategory } from '../../../api/ai'
import { useSubmitReceipt, type AIJob } from '../../../api/aiJobs'
import { ATTACHMENT_ACCEPT, isAttachableFile } from '../../../api/attachments'
import toast from 'react-hot-toast'
import { useAppStore } from '../../../stores/appStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useFormatters } from '../../../hooks/useFormatters'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import { today } from '../../../utils/dates'
import { fromCents, toCents } from '../../../utils/money'
import {
  expressionToCents,
  parseAmountExpressionInput,
  sumExpressionsToCents,
} from '../../../utils/amountExpression'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import type { Transaction, Payee } from '../../../types'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import './TransactionEditor.css'

/** Prefill for create mode — the shared shape every AI entry path (NL text,
 * voice) funnels into so there is exactly one add-transaction flow. */
export interface EditorDraft {
  date?: string
  payeeName?: string
  categoryId?: string | null
  memo?: string
  outflow?: string
  inflow?: string
  /** Links the saved transaction back to the AI job for the audit log. */
  aiJobId?: string
}

interface Props {
  budgetId: string
  /** Fixed account context (account page). Omit to let the user pick the
   * account in the editor — e.g. when adding from the budget view. */
  accountId?: string | null
  transaction: Transaction | null
  /** Pre-selected category for new transactions (budget-row add flow). */
  initialCategoryId?: string | null
  /** Create-mode prefill from an AI parse (NL/voice entry). */
  initialDraft?: EditorDraft | null
  /** Review mode: the AI job that produced `transaction` — shows the receipt
   * beside the form, the extraction banner, and the suggested-split action. */
  aiJob?: AIJob | null
  onClose: () => void
}

export function TransactionEditor({
  budgetId,
  accountId: fixedAccountId = null,
  transaction,
  initialCategoryId = null,
  initialDraft = null,
  aiJob = null,
  onClose,
}: Props) {
  const createTxn = useCreateTransaction(budgetId)
  const updateTxn = useUpdateTransaction(budgetId)
  const deleteTxn = useDeleteTransaction(budgetId)
  const convertToSplit = useConvertToSplit(budgetId)
  const suggestCategory = useSuggestCategory(budgetId)

  const { data: payees = [] } = usePayees(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)

  const isMobile = useIsMobile()
  const { formatMoney } = useFormatters()
  // Android back / swipe-back cancels the editor instead of leaving the page
  useHistoryDismissable(isMobile, onClose, 'txn-editor')

  const isEdit = !!transaction
  // Review mode: an AI-created transaction being verified against its receipt
  const isReview = !!aiJob && isEdit

  // No fixed account (budget-view add): the user picks one, defaulting to the
  // same sticky "last used" account the quick-add flow remembers.
  const lastPickedAccountId = useAppStore((s) => s.lastQuickAddAccountId)
  const setLastPickedAccountId = useAppStore((s) => s.setLastQuickAddAccountId)
  const [pickedAccountId, setPickedAccountId] = useState('')
  const openAccounts = useMemo(() => accounts.filter((a) => !a.is_closed), [accounts])
  useEffect(() => {
    if (fixedAccountId || transaction || pickedAccountId || openAccounts.length === 0) return
    const preferred =
      lastPickedAccountId && openAccounts.some((a) => a.id === lastPickedAccountId)
        ? lastPickedAccountId
        : (openAccounts.find((a) => a.on_budget)?.id ?? openAccounts[0].id)
    setPickedAccountId(preferred)
  }, [fixedAccountId, transaction, pickedAccountId, openAccounts, lastPickedAccountId])
  const accountId = fixedAccountId ?? transaction?.account_id ?? pickedAccountId

  const [date, setDate] = useState(
    transaction?.date.slice(0, 10) ?? initialDraft?.date ?? today()
  )
  const [payeeQuery, setPayeeQuery] = useState(
    !transaction && initialDraft?.payeeName ? initialDraft.payeeName : ''
  )
  const [selectedPayeeId, setSelectedPayeeId] = useState<string | null>(
    transaction?.payee_id ?? null
  )
  const [categoryId, setCategoryId] = useState(
    transaction?.category_id ?? initialDraft?.categoryId ?? initialCategoryId ?? ''
  )
  const [memo, setMemo] = useState(transaction?.memo ?? initialDraft?.memo ?? '')
  const [outflow, setOutflow] = useState(() => {
    if (!transaction) return initialDraft?.outflow ?? ''
    if (Number(transaction.amount) >= 0) return ''
    return String(Math.abs(Number(transaction.amount)))
  })
  const [inflow, setInflow] = useState(() => {
    if (!transaction) return initialDraft?.inflow ?? ''
    if (Number(transaction.amount) < 0) return ''
    return String(Number(transaction.amount))
  })
  const [cleared, setCleared] = useState<'uncleared' | 'cleared'>(() => {
    // 'pending' belongs to bank sync and 'reconciled' to the reconciliation
    // flow — neither is user-settable via the API.
    if (transaction?.cleared === 'cleared' || transaction?.cleared === 'reconciled') {
      return 'cleared'
    }
    return 'uncleared'
  })
  const [isTransfer, setIsTransfer] = useState(!!transaction?.transfer_id)
  const [transferAccountId, setTransferAccountId] = useState('')
  const [showPayeeDropdown, setShowPayeeDropdown] = useState(false)
  const [showSimilar, setShowSimilar] = useState(false)
  const [showAttachments, setShowAttachments] = useState(false)
  const [isSplit, setIsSplit] = useState(false)
  const [splits, setSplits] = useState<SplitDraft[]>([
    { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' },
    { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' },
  ])

  const payeeRef = useRef<HTMLDivElement>(null)
  const payeeInitialized = useRef(false)
  const scanInputRef = useRef<HTMLInputElement>(null)

  // Desktop path to the receipt pipeline: pick a file here instead of the
  // mobile quick-add. Queues the same AI job; the editor closes and the
  // drafted transaction arrives for review.
  const aiAvailable = useAIStatus().data?.available === true
  const submitReceipt = useSubmitReceipt(budgetId)

  async function scanReceiptFile(list: FileList | null) {
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
      if (!fixedAccountId) setLastPickedAccountId(accountId)
      toast.success("Receipt queued — it'll appear for review shortly", { duration: 5000 })
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Failed to queue receipt')
    }
  }

  // Initialize payee query once payees are loaded (edit mode)
  useEffect(() => {
    if (!payeeInitialized.current && transaction?.payee_id && payees.length > 0) {
      const p = payees.find((p) => p.id === transaction.payee_id)
      if (p) {
        setPayeeQuery(p.name)
        payeeInitialized.current = true
      }
    }
  }, [payees, transaction?.payee_id])

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (payeeRef.current && !payeeRef.current.contains(e.target as Node)) {
        setShowPayeeDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filteredPayees = payeeQuery.length > 0
    ? payees.filter((p) => p.name.toLowerCase().includes(payeeQuery.toLowerCase())).slice(0, 8)
    : payees.slice(0, 8)

  const groupedCategories = categoryGroups
    .filter((g) => !g.is_hidden)
    .map((g) => ({
      group: g,
      cats: categories.filter(
        (c) => c.category_group_id === g.id && !c.is_hidden && !c.linked_account_id
      ),
    }))
    .filter((g) => g.cats.length > 0)

  const transferAccounts = accounts.filter((a) => a.id !== accountId)
  const transferTarget = accounts.find((a) => a.id === transferAccountId)
  // Off-budget transfers are real spending (YNAB semantics) and may carry a
  // category on the on-budget side
  const transferIsOffBudget = isTransfer && !!transferTarget && !transferTarget.on_budget

  function handlePayeeSelect(p: Payee) {
    setPayeeQuery(p.name)
    setSelectedPayeeId(p.id)
    setShowPayeeDropdown(false)
    if (p.default_category_id && !categoryId) {
      setCategoryId(p.default_category_id)
    }
  }

  function handlePayeeChange(e: React.ChangeEvent<HTMLInputElement>) {
    setPayeeQuery(e.target.value)
    setSelectedPayeeId(null)
    setShowPayeeDropdown(true)
  }

  function handleOutflowChange(v: string) {
    const cleaned = v.replace(/[^0-9.,+\-*/() ]/g, '')
    setOutflow(cleaned)
    if (cleaned) setInflow('')
  }

  function handleInflowChange(v: string) {
    const cleaned = v.replace(/[^0-9.,+\-*/() ]/g, '')
    setInflow(cleaned)
    if (cleaned) setOutflow('')
  }

  // AI-suggested split from receipt line items — offered, never auto-applied.
  // Lines resolved against live categories; a renamed category leaves that
  // line's picker empty for the user to fill.
  const suggestedSplit = isReview ? (aiJob?.result?.suggested_split ?? null) : null

  function applySuggestedSplit() {
    if (!suggestedSplit || suggestedSplit.length < 2) return
    setSplits(
      suggestedSplit.map((line) => {
        const cat = categories.find(
          (c) => c.name.toLowerCase() === line.category.toLowerCase()
        )
        return {
          tempId: crypto.randomUUID(),
          amount: Math.abs(parseFloat(line.amount)).toFixed(2),
          categoryId: cat?.id ?? null,
          memo: '',
        }
      })
    )
    setIsSplit(true)
  }

  function updateSplit(tempId: string, data: Partial<Omit<SplitDraft, 'tempId'>>) {
    setSplits((prev) => prev.map((s) => s.tempId === tempId ? { ...s, ...data } : s))
  }

  function addSplit() {
    setSplits((prev) => [...prev, { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' }])
  }

  function removeSplit(tempId: string) {
    setSplits((prev) => prev.length > 2 ? prev.filter((s) => s.tempId !== tempId) : prev)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!accountId) return
    const outflowVal = parseAmountExpressionInput(outflow) || 0
    const inflowVal = parseAmountExpressionInput(inflow) || 0
    const amount = outflowVal > 0 ? -outflowVal : inflowVal
    const sign = amount < 0 ? -1 : 1

    // Editing frees the old amount back to its category/month; only the net
    // change should count against a future month's available.
    const reversal: OverspendProbe[] = transaction?.category_id
      ? [
          {
            category_id: transaction.category_id,
            date: transaction.date.slice(0, 10),
            amount_delta: -Number(transaction.amount),
          },
        ]
      : []

    if (isSplit && !isTransfer) {
      const splitList = splits.map((s) => ({
        amount: (expressionToCents(s.amount) / 100) * sign,
        category_id: s.categoryId ?? undefined,
        memo: s.memo || undefined,
      }))
      const proceed = await confirmFutureOverspend(
        budgetId,
        [
          ...splitList
            .filter((s) => s.category_id)
            .map((s) => ({ category_id: s.category_id!, date, amount_delta: s.amount })),
          ...reversal,
        ],
        formatMoney
      )
      if (!proceed) return
      if (isEdit) {
        // Split in place: the row becomes the parent, keeping attachments and
        // AI links (a create+delete replacement would orphan the receipt).
        await updateTxn.mutateAsync({
          id: transaction!.id,
          date,
          amount,
          memo: memo || undefined,
          cleared,
          approved: true,
          payee_id: selectedPayeeId || undefined,
        })
        await convertToSplit.mutateAsync({ id: transaction!.id, splits: splitList })
      } else {
        await createTxn.mutateAsync({
          account_id: accountId,
          date,
          amount,
          memo: memo || undefined,
          cleared,
          approved: true,
          payee_id: selectedPayeeId || undefined,
          payee_name: !selectedPayeeId && payeeQuery ? payeeQuery : undefined,
          ai_job_id: initialDraft?.aiJobId,
          splits: splitList,
        })
        if (!fixedAccountId) setLastPickedAccountId(accountId)
      }
      onClose()
      return
    }

    const payload = {
      account_id: accountId,
      date,
      amount,
      memo: memo || undefined,
      cleared,
      approved: true,
      ...(isTransfer
        ? {
            transfer_account_id: transferAccountId,
            ...(transferIsOffBudget && categoryId ? { category_id: categoryId } : {}),
          }
        : {
            payee_id: selectedPayeeId || undefined,
            payee_name: !selectedPayeeId && payeeQuery ? payeeQuery : undefined,
            category_id: categoryId || undefined,
          }),
    }

    const savedCategoryId =
      'category_id' in payload && payload.category_id ? payload.category_id : null
    const proceed = await confirmFutureOverspend(
      budgetId,
      [
        ...(savedCategoryId
          ? [{ category_id: savedCategoryId, date, amount_delta: amount }]
          : []),
        ...reversal,
      ],
      formatMoney
    )
    if (!proceed) return

    if (isEdit) {
      await updateTxn.mutateAsync({ id: transaction!.id, ...payload })
    } else {
      await createTxn.mutateAsync({ ...payload, ai_job_id: initialDraft?.aiJobId })
      if (!fixedAccountId) setLastPickedAccountId(accountId)
    }
    onClose()
  }

  async function handleDelete() {
    if (!transaction) return
    if (!confirm('Delete this transaction?')) return
    await deleteTxn.mutateAsync({ id: transaction.id, accountId })
    onClose()
  }

  const isPending =
    createTxn.isPending || updateTxn.isPending || deleteTxn.isPending || convertToSplit.isPending

  const similarAmount = useMemo(() => {
    const o = parseAmountExpressionInput(outflow)
    const i = parseAmountExpressionInput(inflow)
    if (o > 0) return -o
    if (i > 0) return i
    return null
  }, [outflow, inflow])

  const { data: similarTxns = [] } = useSimilarTransactions(
    accountId,
    similarAmount,
    date || null,
    transaction?.id ?? null,
  )

  const splitIsValid = (() => {
    if (!isSplit) return true
    // Integer-cents comparison — float sums reject valid splits (0.10 issues)
    const totalCents = Math.abs(toCents(parseAmountExpressionInput(outflow || inflow) || 0)) || 0
    const splitCents = sumExpressionsToCents(splits.map((s) => s.amount))
    return (
      splitCents === totalCents &&
      splits.every((s) => {
        const cents = expressionToCents(s.amount)
        return s.categoryId && !isNaN(cents) && cents > 0
      })
    )
  })()

  return (
    <div
      className="txn-editor-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <form
        className={`txn-editor ${isReview ? 'txn-editor--review' : ''}`}
        role="dialog"
        aria-modal
        aria-labelledby="txn-editor-title"
        onSubmit={handleSubmit}
      >
        <div className="txn-editor__header">
          <span id="txn-editor-title" className="txn-editor__title">
            {isReview ? 'Review AI Transaction' : isEdit ? 'Edit Transaction' : 'Add Transaction'}
          </span>
          <button type="button" className="txn-editor__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {isReview && (
          <div
            className={`txn-editor__ai-banner ${aiJob!.status === 'error' ? 'txn-editor__ai-banner--error' : ''}`}
          >
            {aiJob!.status === 'error' ? (
              <>
                <AlertTriangle size={13} />
                <span>Scan failed — enter the details from the image, then approve.</span>
              </>
            ) : (
              <>
                <Sparkles size={13} />
                <span>
                  AI extracted from {aiJob!.kind === 'receipt' ? 'receipt' : 'text'}
                  {aiJob!.result?.draft
                    ? ` · ${Math.round((aiJob!.result.draft.confidence ?? 0) * 100)}% confidence`
                    : ''}
                </span>
              </>
            )}
            {suggestedSplit && suggestedSplit.length >= 2 && !isSplit && (
              <button
                type="button"
                className="txn-editor__ai-banner-action"
                onClick={applySuggestedSplit}
              >
                <Split size={12} />
                Apply suggested split ({suggestedSplit.length})
              </button>
            )}
          </div>
        )}

        {!isEdit && aiAvailable && (
          <div className="txn-editor__scan-row">
            <button
              type="button"
              className="txn-editor__scan-btn"
              onClick={() => scanInputRef.current?.click()}
              disabled={submitReceipt.isPending || !accountId}
              title="Upload a receipt image or PDF — AI drafts the transaction for review"
            >
              <Sparkles size={13} />
              {submitReceipt.isPending ? 'Queuing…' : 'Scan a receipt instead'}
            </button>
            <input
              ref={scanInputRef}
              type="file"
              accept={ATTACHMENT_ACCEPT}
              onChange={(e) => {
                void scanReceiptFile(e.target.files)
                e.target.value = ''
              }}
              style={{ display: 'none' }}
            />
          </div>
        )}

        <div className="txn-editor__main">
          {isReview && aiJob!.attachment_id && (
            <div className="txn-editor__receipt">
              <ReceiptPane
                attachmentId={aiJob!.attachment_id}
                contentType={aiJob!.payload.content_type ?? null}
              />
            </div>
          )}
          <div className="txn-editor__body">
          {!fixedAccountId && !isEdit && (
            <div className="txn-editor__field">
              <label className="txn-editor__label">Account</label>
              <select
                className="txn-editor__select"
                value={pickedAccountId}
                onChange={(e) => setPickedAccountId(e.target.value)}
                required
              >
                <option value="">Select account…</option>
                {openAccounts.some((a) => !a.on_budget) ? (
                  <>
                    <optgroup label="Budget accounts">
                      {openAccounts.filter((a) => a.on_budget).map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Tracking">
                      {openAccounts.filter((a) => !a.on_budget).map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </optgroup>
                  </>
                ) : (
                  openAccounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))
                )}
              </select>
            </div>
          )}
          <div className="txn-editor__row">
            <div className="txn-editor__field">
              <label className="txn-editor__label">Date</label>
              <input
                type="date"
                className="txn-editor__input"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div className="txn-editor__field">
              <label className="txn-editor__label">Cleared</label>
              <select
                className="txn-editor__select"
                value={cleared}
                onChange={(e) => setCleared(e.target.value as typeof cleared)}
              >
                <option value="uncleared">Uncleared</option>
                <option value="cleared">Cleared</option>
                <option value="reconciled">Reconciled</option>
              </select>
            </div>
          </div>

          <div className="txn-editor__field">
            <label className="txn-editor__label">Payee</label>
            <div className="txn-editor__payee-wrap" ref={payeeRef}>
              <input
                type="text"
                className="txn-editor__input"
                value={payeeQuery}
                onChange={handlePayeeChange}
                onFocus={() => setShowPayeeDropdown(true)}
                placeholder="Search or enter payee..."
                autoComplete="off"
              />
              {showPayeeDropdown && filteredPayees.length > 0 && (
                <div className="txn-editor__payee-dropdown">
                  {filteredPayees.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="txn-editor__payee-option"
                      onMouseDown={() => handlePayeeSelect(p)}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="txn-editor__toggle-row">
            <label className="txn-editor__toggle" aria-label="Transfer to account">
              <input
                type="checkbox"
                checked={isTransfer}
                onChange={(e) => setIsTransfer(e.target.checked)}
              />
              <span className="txn-editor__toggle-slider" />
            </label>
            <span className="txn-editor__toggle-label">Transfer to account</span>
          </div>

          {isTransfer ? (
            <>
              <div className="txn-editor__field">
                <label className="txn-editor__label">To Account</label>
                <select
                  className="txn-editor__select"
                  value={transferAccountId}
                  onChange={(e) => setTransferAccountId(e.target.value)}
                  required={isTransfer}
                >
                  <option value="">Select account…</option>
                  {transferAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
              {transferIsOffBudget && (
                <div className="txn-editor__field">
                  <label className="txn-editor__label">
                    Category
                    <span className="txn-editor__label-hint">
                      {' '}— transfers to off-budget accounts count as spending
                    </span>
                  </label>
                  <select
                    className="txn-editor__select"
                    value={categoryId}
                    onChange={(e) => setCategoryId(e.target.value)}
                  >
                    <option value="">No category</option>
                    {groupedCategories.map(({ group, cats }) => (
                      <optgroup key={group.id} label={group.name}>
                        {cats.map((c) => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
              )}
            </>
          ) : isSplit ? (
            <div className="txn-editor__field">
              <label className="txn-editor__label">
                Split Transaction
                <button
                  type="button"
                  className="txn-editor__ai-btn"
                  onClick={() => { setIsSplit(false); setCategoryId('') }}
                  title="Switch to single category"
                >
                  <X size={12} />
                  Cancel split
                </button>
              </label>
              <div className="txn-editor__splits">
                {splits.map((s) => (
                  <div key={s.tempId} className="txn-editor__split-row">
                    <select
                      className="txn-editor__select txn-editor__split-category"
                      value={s.categoryId ?? ''}
                      onChange={(e) => updateSplit(s.tempId, { categoryId: e.target.value || null })}
                    >
                      <option value="">Category…</option>
                      {groupedCategories.map(({ group, cats }) => (
                        <optgroup key={group.id} label={group.name}>
                          {cats.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    <AmountInput
                      className="txn-editor__input txn-editor__split-amount"
                      value={s.amount}
                      onValueChange={(v) => updateSplit(s.tempId, { amount: v })}
                      placeholder="0.00"
                    />
                    <button
                      type="button"
                      className="txn-editor__split-remove"
                      onClick={() => removeSplit(s.tempId)}
                      disabled={splits.length <= 2}
                      aria-label="Remove split"
                      title="Remove"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <div className="txn-editor__split-footer">
                  <button type="button" className="txn-editor__split-add" onClick={addSplit}>
                    <Plus size={12} /> Add split
                  </button>
                  {(() => {
                    const splitCents = sumExpressionsToCents(splits.map((s) => s.amount))
                    const totalCents =
                      Math.abs(toCents(parseAmountExpressionInput(outflow || inflow) || 0)) || 0
                    const remainingCents = totalCents - splitCents
                    return (
                      <span className={`txn-editor__split-remaining ${remainingCents === 0 ? 'txn-editor__split-remaining--done' : ''}`}>
                        {remainingCents === 0 ? 'Fully assigned' : `Remaining: $${fromCents(remainingCents).toFixed(2)}`}
                      </span>
                    )
                  })()}
                </div>
              </div>
            </div>
          ) : (
            <div className="txn-editor__field">
              <label className="txn-editor__label">
                Category
                <button
                  type="button"
                  className="txn-editor__ai-btn"
                  title="Split this transaction"
                  onClick={() => setIsSplit(true)}
                >
                  <Split size={12} />
                  Split
                </button>
                <button
                  type="button"
                  className="txn-editor__ai-btn"
                  title="AI suggest category"
                  disabled={suggestCategory.isPending}
                  onClick={async () => {
                    const outflowVal = parseAmountExpressionInput(outflow) || 0
                    const inflowVal = parseAmountExpressionInput(inflow) || 0
                    const amount = outflowVal > 0 ? -outflowVal : inflowVal
                    const result = await suggestCategory.mutateAsync({
                      payee_name: payeeQuery || 'Unknown',
                      amount,
                      memo: memo || undefined,
                    })
                    if (result.category_id) setCategoryId(result.category_id)
                  }}
                >
                  <Sparkles size={12} />
                  {suggestCategory.isPending ? 'Thinking…' : 'AI Suggest'}
                </button>
              </label>
              <select
                className="txn-editor__select"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
              >
                <option value="">No category</option>
                {groupedCategories.map(({ group, cats }) => (
                  <optgroup key={group.id} label={group.name}>
                    {cats.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          )}

          <div className="txn-editor__field">
            <label className="txn-editor__label">Memo</label>
            <input
              type="text"
              className="txn-editor__input"
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              placeholder="Optional note..."
            />
          </div>

          <div className="txn-editor__row">
            <div className="txn-editor__field">
              <label className="txn-editor__label">Outflow</label>
              <AmountInput
                className="txn-editor__input"
                value={outflow}
                onValueChange={handleOutflowChange}
                placeholder="0.00"
              />
            </div>
            <div className="txn-editor__field">
              <label className="txn-editor__label">Inflow</label>
              <AmountInput
                className="txn-editor__input"
                value={inflow}
                onValueChange={handleInflowChange}
                placeholder="0.00"
              />
            </div>
          </div>
          </div>
        </div>

        {similarTxns.length > 0 && (
          <div className="txn-editor__similar">
            <button
              type="button"
              className="txn-editor__similar-toggle"
              onClick={() => setShowSimilar((v) => !v)}
            >
              <AlertTriangle size={13} />
              {similarTxns.length} similar transaction{similarTxns.length !== 1 ? 's' : ''} found
              {showSimilar ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
            {showSimilar && (
              <ul className="txn-editor__similar-list">
                {similarTxns.map((t) => (
                  <li key={t.id} className="txn-editor__similar-item">
                    <span className="txn-editor__similar-date">{t.date}</span>
                    <span className={t.amount < 0 ? 'txn-outflow' : 'txn-inflow'}>
                      {t.amount < 0 ? `-$${Math.abs(t.amount).toFixed(2)}` : `$${t.amount.toFixed(2)}`}
                    </span>
                    <span className="txn-editor__similar-desc">
                      {t.import_description || t.memo || '—'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {isEdit && transaction && (
          <div className="txn-editor__attachments">
            <button
              type="button"
              className="txn-editor__similar-toggle"
              onClick={() => setShowAttachments((v) => !v)}
            >
              <Paperclip size={13} />
              Receipts & attachments
              {showAttachments ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
            {showAttachments && (
              <AttachmentPanel transactionId={transaction.id} embedded />
            )}
          </div>
        )}

        <div className="txn-editor__footer">
          {isEdit ? (
            <button
              type="button"
              className="txn-editor__btn txn-editor__btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              <Trash2 size={14} />
              Delete
            </button>
          ) : (
            <span />
          )}
          <div className="txn-editor__footer-actions">
            <button
              type="button"
              className="txn-editor__btn txn-editor__btn--secondary"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="txn-editor__btn txn-editor__btn--primary"
              disabled={isPending || !splitIsValid || !accountId}
            >
              {isReview ? 'Approve' : isEdit ? 'Save' : 'Add'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
