import { groupedCategorySections } from '../../../utils/categoryPickers'
import { useState, useRef, useEffect, useMemo } from 'react'
import { X, Trash2, Sparkles, Split, Plus, AlertTriangle, ChevronDown, ChevronUp, MessageSquareText, Paperclip, ReceiptText, RefreshCw, Lock } from 'lucide-react'
import { AttachmentPanel } from '../../attachments/AttachmentPanel'
import { NLEntryForm } from '../../ai/NLEntryForm'
import { ReceiptPane } from '../../ai/ReceiptPane'
import { ReceiptScanTab } from './ReceiptScanTab'
import {
  useTransactionClassification,
  useCreateTransaction,
  useUpdateTransaction,
  useDeleteTransaction,
  useConvertToSplit,
  useReplaceSplits,
  useTransactionSplits,
  usePayees,
  useSimilarTransactions,
  useTransaction,
  useTransferCandidates,
} from '../../../api/transactions'
import toast from 'react-hot-toast'
import { apiErrorMessage } from '../../../api/client'
import { confirmDeleteTransaction } from '../../../api/attachments'
import { useCategories, useCategoryGroups, useRecentPayeeForCategory } from '../../../api/categories'
import { useAccounts } from '../../../api/accounts'
import { confirmFutureOverspend, type OverspendProbe } from '../../../api/budgets'
import { useAIStatus, useSuggestCategory } from '../../../api/ai'
import { type AIJob } from '../../../api/aiJobs'
import { useAppStore } from '../../../stores/appStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useFormatters } from '../../../hooks/useFormatters'
import { Link } from 'react-router-dom'
import { useReprocessAIJob } from '../../../api/aiJobs'
import { Modal } from '../../common/Modal/Modal'
import { isConfigFailure, scanFailureReason } from './scanFailure'
import { today } from '../../../utils/dates'
import { useToastUndo } from '../../../utils/toastUndo'
import { fromCents, parseApiDecimal, toCents } from '../../../utils/money'
import {
  expressionToCents,
  parseAmountExpressionInput,
} from '../../../utils/amountExpression'
import { checkSplit, draftsFromLines } from '../../../utils/splits'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { CategoryCombobox } from '../../common/CategoryCombobox/CategoryCombobox'
import type { Transaction, Payee } from '../../../types'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import { randomUUID } from '../../../utils/uuid'
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

/** Sentinel partner choice: "none of these — write the far leg". */
const CREATE_NEW_PARTNER = '__create__'

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
  // accountId for undo resolved after hooks; toastUndo called with final value
  const showUndo = useToastUndo(budgetId)
  const convertToSplit = useConvertToSplit(budgetId)
  const replaceSplits = useReplaceSplits(budgetId)
  const suggestCategory = useSuggestCategory(budgetId)

  const { data: payees = [] } = usePayees(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)

  const isMobile = useIsMobile()
  // Clamp the full-screen editor above the iOS keyboard so the footer stays reachable
  const { formatMoney, formatDate } = useFormatters()
  // Android back / swipe-back cancels the editor instead of leaving the page

  const isEdit = !!transaction
  // Why this row counts the way it does in reports. Only for saved rows — a
  // draft has no classification yet, and the endpoint derives it per row.
  const { data: classification } = useTransactionClassification(transaction?.id ?? null)
  // Review mode: an AI-created transaction being verified against its receipt
  const isReview = !!aiJob && isEdit
  const reprocess = useReprocessAIJob(budgetId)

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
  // Reconciled: the money is locked — amount, date, cleared state — and
  // everything else stays editable (domain/reconciliation.py, one rule).
  // The locked fields are shown disabled and left out of the PATCH.
  const isReconciled = transaction?.cleared === 'reconciled'
  const [cleared, setCleared] = useState<'uncleared' | 'cleared' | 'reconciled'>(() => {
    // 'pending' belongs to bank sync and 'reconciled' to the reconciliation
    // flow — neither is user-settable via the API.
    if (transaction?.cleared === 'reconciled') return 'reconciled'
    if (transaction?.cleared === 'cleared') return 'cleared'
    return 'uncleared'
  })
  // counterpart_account_id, not transfer_id: an unpaired leg (the importer's
  // leftovers) is still a transfer, and it is the one most in need of this
  // editor. Opening one used to show the toggle off and no destination.
  const [isTransfer, setIsTransfer] = useState(!!transaction?.counterpart_account_id)
  const [transferAccountId, setTransferAccountId] = useState(
    transaction?.counterpart_account_id ?? ''
  )
  /** Which existing row to adopt as the far leg (the ambiguity answer), or
   *  CREATE_NEW_PARTNER for "none of these". */
  const [partnerChoice, setPartnerChoice] = useState<string | null>(null)
  const wasTransfer = !!transaction?.counterpart_account_id
  const [showPayeeDropdown, setShowPayeeDropdown] = useState(false)
  const [showSimilar, setShowSimilar] = useState(false)
  const [showAttachments, setShowAttachments] = useState(false)
  // An existing split opens AS a split, with its lines from the server —
  // the register never holds them, and an editor that opened flat over a
  // split was the only way to "see" one: by not seeing it at all.
  const editingExistingSplit = !!transaction?.is_split
  const { data: splitLines } = useTransactionSplits(transaction?.id ?? null, editingExistingSplit)
  const [isSplit, setIsSplit] = useState(editingExistingSplit)
  const [splits, setSplits] = useState<SplitDraft[]>(() =>
    editingExistingSplit
      ? []
      : [
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
          { tempId: randomUUID(), amount: '', categoryId: null, memo: '' },
        ]
  )
  // Seed once, as a render-phase state adjustment (the pattern Combobox
  // uses for an outside value change): no effect, no ref read in render.
  const [linesSeeded, setLinesSeeded] = useState(false)
  if (splitLines && !linesSeeded) {
    setLinesSeeded(true)
    setSplits(draftsFromLines(splitLines))
  }
  const splitLinesPending = editingExistingSplit && !linesSeeded

  // Tab state: entry method in add mode
  const [activeTab, setActiveTab] = useState<'manual' | 'describe' | 'receipt'>('manual')
  const showTabs = !isEdit

  // AI provenance: set by an initialDraft (mobile quick entry) or by the
  // Describe tab; links the created transaction back to its ai_jobs row.
  const [aiJobId, setAiJobId] = useState<string | undefined>(initialDraft?.aiJobId)
  const [aiDrafted, setAiDrafted] = useState(!!initialDraft?.aiJobId)

  // Review handoff: when an AI job completes, we render a nested TransactionEditor
  const [reviewJob, setReviewJob] = useState<AIJob | null>(null)
  const { data: reviewTxn } = useTransaction(reviewJob?.transaction_id ?? null)

  const payeeRef = useRef<HTMLDivElement>(null)
  const payeeInitialized = useRef(false)

  const aiAvailable = useAIStatus().data?.available === true

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

  // Category-context add: prefill the most recent payee for this category
  // (fully editable — just a head start). Never overwrite anything the user
  // or an AI draft already put in the field.
  const { data: recentPayee } = useRecentPayeeForCategory(
    budgetId,
    !isEdit && !initialDraft?.payeeName && initialCategoryId ? initialCategoryId : null
  )
  useEffect(() => {
    if (!recentPayee || payeeInitialized.current) return
    payeeInitialized.current = true
    if (payeeQuery || selectedPayeeId) return
    setPayeeQuery(recentPayee.name)
    setSelectedPayeeId(recentPayee.payee_id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recentPayee])

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

  const groupedCategories = groupedCategorySections(
    categories.filter((c) => c.is_categorizable),
    categoryGroups
  )

  const transferAccounts = accounts.filter((a) => a.id !== accountId)
  const transferTarget = accounts.find((a) => a.id === transferAccountId)
  // Only for a row that isn't linked yet — an already-linked leg has its
  // partner, and retargeting moves that partner rather than adopting another.
  const needsPartner = isEdit && isTransfer && !transaction?.transfer_id && !!transferAccountId
  const { data: partnerCandidates = [] } = useTransferCandidates(
    budgetId,
    needsPartner ? (transaction?.id ?? null) : null,
    needsPartner ? transferAccountId : null
  )
  // The question is only answerable by a person, and the server refuses a
  // submit without an answer — so Save waits for one rather than sending a
  // request that can only fail.
  const needsPartnerChoice = needsPartner && partnerCandidates.length > 0 && !partnerChoice
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

  // Describe tab handoff: the parsed draft fills the manual form for review —
  // the user lands on familiar fields with everything editable.
  function applyNLDraft(d: EditorDraft) {
    if (d.date) setDate(d.date)
    setPayeeQuery(d.payeeName ?? '')
    setSelectedPayeeId(null)
    payeeInitialized.current = true
    setCategoryId(d.categoryId ?? '')
    setMemo(d.memo ?? '')
    setOutflow(d.outflow ?? '')
    setInflow(d.inflow ?? '')
    setAiJobId(d.aiJobId)
    setAiDrafted(true)
    setActiveTab('manual')
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
          tempId: randomUUID(),
          amount: Math.abs(parseApiDecimal(line.amount)).toFixed(2),
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
    setSplits((prev) => [...prev, { tempId: randomUUID(), amount: '', categoryId: null, memo: '' }])
  }

  function removeSplit(tempId: string) {
    setSplits((prev) => prev.length > 2 ? prev.filter((s) => s.tempId !== tempId) : prev)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    try {
      await doSubmit()
    } catch (err) {
      // The mutations here define no onError, so without this catch a server
      // refusal — an unanswered transfer-partner question, a reconciled-row
      // guard — simply vanished: Save re-enabled, nothing saved, nothing
      // said. The editor stays open with the user's input intact.
      toast.error(apiErrorMessage(err, 'Could not save'))
    }
  }

  async function doSubmit() {
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
        id: s.serverId,
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
      if (isEdit && editingExistingSplit) {
        // Lines in place: named lines update, new ones append, missing ones
        // go. The parent's amount is the lines' sum and is not sent.
        await updateTxn.mutateAsync({
          id: transaction!.id,
          ...(isReconciled ? {} : { date, cleared }),
          memo: memo || undefined,
          approved: true,
          payee_id: selectedPayeeId || undefined,
        })
        await replaceSplits.mutateAsync({ id: transaction!.id, splits: splitList })
      } else if (isEdit) {
        // Split in place: the row becomes the parent, keeping attachments and
        // AI links (a create+delete replacement would orphan the receipt).
        await updateTxn.mutateAsync({
          id: transaction!.id,
          ...(isReconciled ? {} : { date, amount, cleared }),
          memo: memo || undefined,
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
          ai_job_id: aiJobId,
          splits: splitList,
        })
        if (!fixedAccountId) setLastPickedAccountId(accountId)
      }
      onClose()
      return
    }

    const payload = {
      account_id: accountId,
      // Locked money never leaves the editor for a reconciled row.
      ...(isReconciled ? {} : { date, amount, cleared }),
      memo: memo || undefined,
      approved: true,
      ...(isTransfer
        ? {
            transfer_account_id: transferAccountId,
            // Which existing row is the far leg, when more than one could be.
            // Without an answer the server refuses rather than guess.
            ...(partnerChoice === CREATE_NEW_PARTNER
              ? { transfer_create_partner: true }
              : partnerChoice
                ? { transfer_partner_transaction_id: partnerChoice }
                : {}),
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
      // Turning the toggle OFF: break the link as its own step. The payee of
      // a linked leg IS its destination, so the server refuses to take a new
      // payee and a link instruction together — break first, then edit.
      if (wasTransfer && !isTransfer) {
        await updateTxn.mutateAsync({
          id: transaction!.id,
          transfer_account_id: null,
        })
      }
      await updateTxn.mutateAsync({ id: transaction!.id, ...payload })
    } else {
      // A new row is never reconciled; restate the money so the type says so.
      await createTxn.mutateAsync({ ...payload, date, amount, cleared, ai_job_id: aiJobId })
      if (!fixedAccountId) setLastPickedAccountId(accountId)
    }
    onClose()
  }

  async function handleDelete() {
    if (!transaction) return
    if (!(await confirmDeleteTransaction(transaction.id))) return
    try {
      const { batchId } = await deleteTxn.mutateAsync({ id: transaction.id, accountId })
      onClose()
      showUndo(batchId, 'Transaction deleted')
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not delete'))
    }
  }

  const isPending =
    createTxn.isPending ||
    updateTxn.isPending ||
    deleteTxn.isPending ||
    convertToSplit.isPending ||
    replaceSplits.isPending ||
    splitLinesPending

  // What the bank reported, as distinct from the ledger values the user can
  // edit. The payee line prefers the bank's own string and falls back to the
  // import description; showing both only helps when they actually differ.
  const bankRecord = useMemo(() => {
    if (!transaction) return null
    const payee = transaction.bank_payee
    const description = transaction.import_description
    const hasAny =
      transaction.bank_posted_date != null ||
      transaction.bank_amount != null ||
      payee != null ||
      description != null
    if (!hasAny) return null
    return {
      postedDate: transaction.bank_posted_date,
      amount: transaction.bank_amount,
      amountDiffers:
        transaction.bank_amount != null && transaction.bank_amount !== transaction.amount,
      dateDiffers:
        transaction.bank_posted_date != null && transaction.bank_posted_date !== transaction.date,
      payee: payee ?? description,
      description: payee && description && payee !== description ? description : null,
    }
  }, [transaction])

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

  // Derived exactly as handleSubmit derives the amount it saves. Picking the
  // field with `outflow || inflow` validated the string "0" against a "50"
  // inflow, so the editor checked one number and wrote another.
  const editorTotalCents = (() => {
    const outflowVal = parseAmountExpressionInput(outflow) || 0
    const inflowVal = parseAmountExpressionInput(inflow) || 0
    return Math.abs(toCents(outflowVal > 0 ? -outflowVal : inflowVal)) || 0
  })()

  const splitCheck = checkSplit(editorTotalCents, splits)
  const splitIsValid = !isSplit || splitCheck.isValid

  // Review handoff: when an AI job completes, render a nested TransactionEditor
  // in review mode with the newly created transaction.
  if (reviewJob && reviewTxn) {
    return (
      <TransactionEditor
        key={reviewTxn.id}
        budgetId={budgetId}
        accountId={fixedAccountId}
        transaction={reviewTxn}
        aiJob={reviewJob}
        onClose={onClose}
      />
    )
  }

  // Account field used in both tabs (shared state survives tab switches)
  const accountField = !fixedAccountId && !isEdit ? (
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
  ) : null

  return (
    <Modal
      onClose={onClose}
      className="txn-editor-overlay"
      historyKey={isMobile ? 'txn-editor' : undefined}
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
                {/* The specific reason, not just "it failed". A model without
                    vision and a genuinely unreadable photo produce the same
                    stub, and only one of them is fixable in Settings. */}
                <span>
                  {scanFailureReason(aiJob!.error)}
                  {isConfigFailure(aiJob!.error) && (
                    <>
                      {' '}
                      <Link to="/settings" className="txn-editor__ai-banner-link">
                        Open Settings
                      </Link>
                    </>
                  )}
                </span>
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
            {aiJob!.status === 'error' && (
              <button
                type="button"
                className="txn-editor__ai-banner-action"
                onClick={() => reprocess.mutate(aiJob!.id)}
                disabled={reprocess.isPending}
              >
                <RefreshCw size={12} />
                {reprocess.isPending ? 'Retrying…' : 'Try again'}
              </button>
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

        {/* AI-draft provenance in add mode: the manual form was prefilled
            from a description — say so, since the hop is otherwise silent */}
        {!isEdit && aiDrafted && activeTab === 'manual' && (
          <div className="txn-editor__ai-banner">
            <Sparkles size={13} />
            <span>AI drafted this from your description — check it over, then add.</span>
          </div>
        )}

        {showTabs && (
          <div className="txn-editor__tabs" role="tablist" aria-label="Entry method">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'manual'}
              className={`txn-editor__tab ${activeTab === 'manual' ? 'txn-editor__tab--active' : ''}`}
              onClick={() => setActiveTab('manual')}
            >
              Manual entry
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'describe'}
              className={`txn-editor__tab ${activeTab === 'describe' ? 'txn-editor__tab--active' : ''}`}
              onClick={() => setActiveTab('describe')}
            >
              <MessageSquareText size={13} />
              Describe it
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'receipt'}
              className={`txn-editor__tab ${activeTab === 'receipt' ? 'txn-editor__tab--active' : ''}`}
              onClick={() => setActiveTab('receipt')}
            >
              <ReceiptText size={13} />
              From receipt
            </button>
          </div>
        )}

        {/* Describe tab content: parse free text into a draft, then hop to
            the manual tab with the fields filled in */}
        {showTabs && activeTab === 'describe' && (
          <div className="txn-editor__main">
            <div className="txn-editor__body">
              {accountField}
              <div className="txn-editor__describe">
                <p className="txn-editor__describe-intro">
                  Type or dictate a transaction — AI drafts it into the form
                  for you to review.
                </p>
                <NLEntryForm budgetId={budgetId} onDraft={applyNLDraft} onNavigate={onClose} />
              </div>
            </div>
          </div>
        )}

        {/* Receipt tab content */}
        {showTabs && activeTab === 'receipt' ? (
          <div className="txn-editor__main">
            <div className="txn-editor__body">
              {accountField}
              <ReceiptScanTab
                budgetId={budgetId}
                accountId={accountId}
                aiAvailable={aiAvailable}
                onReviewReady={setReviewJob}
                onRememberAccount={() => {
                  if (!fixedAccountId && accountId) setLastPickedAccountId(accountId)
                }}
                onClose={onClose}
              />
            </div>
          </div>
        ) : showTabs && activeTab === 'describe' ? null : (
          /* Manual entry tab content (default) */
          <>
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
          {accountField}
          {isReconciled && (
            <div className="txn-editor__lock-note" role="note">
              <Lock size={12} aria-hidden />
              Reconciled — the amount, date and cleared state are locked. Everything else
              can be changed here; unlock from the row menu to change those.
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
                disabled={isReconciled}
              />
            </div>
            <div className="txn-editor__field">
              <label className="txn-editor__label">Cleared</label>
              {isReconciled ? (
                <div className="txn-editor__input txn-editor__locked" aria-label="Cleared: reconciled">
                  <Lock size={12} aria-hidden />
                  Reconciled
                </div>
              ) : (
                <select
                  className="txn-editor__select"
                  value={cleared}
                  onChange={(e) => setCleared(e.target.value as 'uncleared' | 'cleared')}
                >
                  <option value="uncleared">Uncleared</option>
                  <option value="cleared">Cleared</option>
                </select>
              )}
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
                disabled={isReconciled}
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
                  onChange={(e) => {
                    setTransferAccountId(e.target.value)
                    setPartnerChoice(null)
                  }}
                  required={isTransfer}
                  aria-label="To Account"
                >
                  <option value="">Select account…</option>
                  {transferAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* More than one row over there could be this transfer's other
                  half. Guessing would either link the wrong money or write a
                  duplicate, so the answer is the user's. */}
              {partnerCandidates.length > 0 && (
                <div className="txn-editor__field">
                  <label className="txn-editor__label">
                    Which transaction in {transferTarget?.name} is the other side?
                  </label>
                  <div className="txn-editor__partner-options">
                    {partnerCandidates.map((c) => (
                      <label key={c.id} className="txn-editor__partner-option">
                        <input
                          type="radio"
                          name="transfer-partner"
                          checked={partnerChoice === c.id}
                          onChange={() => setPartnerChoice(c.id)}
                        />
                        <span>
                          {c.date} · {formatMoney(Number(c.amount))}
                          {c.memo ? ` · ${c.memo}` : ''}
                          {c.cleared === 'reconciled' ? ' · reconciled' : ''}
                        </span>
                      </label>
                    ))}
                    <label className="txn-editor__partner-option">
                      <input
                        type="radio"
                        name="transfer-partner"
                        checked={partnerChoice === CREATE_NEW_PARTNER}
                        onChange={() => setPartnerChoice(CREATE_NEW_PARTNER)}
                      />
                      <span>
                        None of these — add the matching transaction to{' '}
                        {transferTarget?.name}
                      </span>
                    </label>
                  </div>
                </div>
              )}
              {transferIsOffBudget && (
                <div className="txn-editor__field">
                  <label className="txn-editor__label">
                    Category
                    <span className="txn-editor__label-hint">
                      {' '}— transfers to off-budget accounts count as spending
                    </span>
                  </label>
                  <CategoryCombobox
                    value={categoryId || null}
                    onChange={(id) => setCategoryId(id ?? '')}
                    groups={groupedCategories}
                    allowNone
                    aria-label="Category"
                  />
                </div>
              )}
            </>
          ) : isSplit ? (
            <div className="txn-editor__field">
              <label className="txn-editor__label">
                Split Transaction
                {!editingExistingSplit && (
                  <button
                    type="button"
                    className="txn-editor__ai-btn"
                    onClick={() => { setIsSplit(false); setCategoryId('') }}
                    title="Switch to single category"
                  >
                    <X size={12} />
                    Cancel split
                  </button>
                )}
              </label>
              {splitLinesPending && (
                <div className="txn-editor__split-loading" role="status">Loading lines…</div>
              )}
              <div className="txn-editor__splits">
                {splits.map((s) => (
                  <div key={s.tempId} className="txn-editor__split-row">
                    <CategoryCombobox
                      className="txn-editor__split-category"
                      value={s.categoryId}
                      onChange={(id) => updateSplit(s.tempId, { categoryId: id })}
                      groups={groupedCategories}
                      allowNone
                      noneLabel="Category…"
                      sheetTitle="Split category"
                      aria-label="Split category"
                    />
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
                  <span className={`txn-editor__split-remaining ${splitCheck.remainingCents === 0 ? 'txn-editor__split-remaining--done' : ''}`}>
                    {splitCheck.remainingCents === 0
                      ? 'Fully assigned'
                      : `Remaining: ${formatMoney(fromCents(splitCheck.remainingCents))}`}
                  </span>
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
              <CategoryCombobox
                value={categoryId || null}
                onChange={(id) => setCategoryId(id ?? '')}
                groups={groupedCategories}
                allowNone
                aria-label="Category"
              />
            </div>
          )}

          <div className="txn-editor__field">
            <label className="txn-editor__label">Memo</label>
            <textarea
              className="txn-editor__input txn-editor__memo"
              rows={3}
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
                disabled={editingExistingSplit || isReconciled}
                title={
                  isReconciled
                    ? 'Reconciled — the amount is locked'
                    : editingExistingSplit
                      ? 'A split’s total is the sum of its lines'
                      : undefined
                }
              />
            </div>
            <div className="txn-editor__field">
              <label className="txn-editor__label">Inflow</label>
              <AmountInput
                className="txn-editor__input"
                value={inflow}
                onValueChange={handleInflowChange}
                placeholder="0.00"
                disabled={editingExistingSplit || isReconciled}
                title={
                  isReconciled
                    ? 'Reconciled — the amount is locked'
                    : editingExistingSplit
                      ? 'A split’s total is the sum of its lines'
                      : undefined
                }
              />
            </div>
          </div>
          </div>
        </div>

        {isEdit && transaction && bankRecord && (
          <div className="txn-editor__bank-meta">
            <span className="txn-editor__bank-meta-label">From your bank</span>
            <dl className="txn-editor__bank-meta-fields">
              {bankRecord.postedDate && (
                <div
                  className={`txn-editor__bank-meta-field${bankRecord.dateDiffers ? ' txn-editor__bank-meta-field--differs' : ''}`}
                  title={bankRecord.dateDiffers ? 'Differs from the date on this transaction' : undefined}
                >
                  <dt>Posted</dt>
                  <dd>{formatDate(bankRecord.postedDate)}</dd>
                </div>
              )}
              {bankRecord.amount !== null && (
                <div
                  className={`txn-editor__bank-meta-field${bankRecord.amountDiffers ? ' txn-editor__bank-meta-field--differs' : ''}`}
                  title={bankRecord.amountDiffers ? 'Differs from the amount on this transaction' : undefined}
                >
                  <dt>Amount</dt>
                  <dd>{formatMoney(bankRecord.amount)}</dd>
                </div>
              )}
              {bankRecord.payee && (
                <div className="txn-editor__bank-meta-field txn-editor__bank-meta-field--wide">
                  <dt>Payee</dt>
                  <dd title={bankRecord.payee}>{bankRecord.payee}</dd>
                </div>
              )}
              {bankRecord.description && (
                <div className="txn-editor__bank-meta-field txn-editor__bank-meta-field--wide">
                  <dt>Description</dt>
                  <dd title={bankRecord.description}>{bankRecord.description}</dd>
                </div>
              )}
            </dl>
          </div>
        )}

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

        {classification && (
          <p className="txn-editor__classification">
            Counts as <strong>{classification.label}</strong> in reports — because{' '}
            {classification.explanation}.
          </p>
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
              disabled={isPending || !splitIsValid || !accountId || needsPartnerChoice}
            >
              {isReview ? 'Approve' : isEdit ? 'Save' : 'Add'}
            </button>
          </div>
        </div>
          </>
        )}
      </form>
    </Modal>
  )
}
