import { AlertTriangle, RefreshCw, Sparkles, Split } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { type AIJob, useReprocessAIJob } from '../../../api/aiJobs'
import { useFormatters } from '../../../hooks/useFormatters'
import { categoryOverruledNote, draftCheckNotes, unresolvedCategoryNote } from '../../ai/draftNotes'
import { CardEndingNotice } from '../../ai/CardEndingNotice'
import { ReadNotes } from '../../ai/ReadNotes'
import { jobFailure } from './scanFailure'
import { FailureDetails } from '../../ai/FailureDetails'

interface Props {
  job: AIJob
  budgetId: string
  /** How many lines the AI suggests splitting the row into, when the offer
   *  stands (two or more lines, and the row is not split already); null
   *  hides it. */
  splitOffer: number | null
  onApplySplit: () => void
  /** Leaving for another row: the editor closes itself. */
  onNavigate: () => void
}

/** The review banner over an AI-drafted row: where it came from and how
 *  sure the model was, or — when the job failed — the specific reason and a
 *  retry. Its own component so the editor holds the form, not every banner
 *  the form can carry. */
export function AIReviewBanner({ job, budgetId, splitOffer, onApplySplit, onNavigate }: Props) {
  const reprocess = useReprocessAIJob(budgetId)
  const navigate = useNavigate()
  const formatters = useFormatters()
  const overruled = categoryOverruledNote(job.result?.draft)
  // As of the scan, so only while the row still waits for review: once it
  // is approved the question has been answered.
  const twin = job.needs_review ? job.result?.already_entered : undefined
  const checkNotes = draftCheckNotes(job.result?.draft, formatters)
  const failure = job.status === 'error' ? jobFailure(job) : null
  return (
    <div
      className={`txn-editor__ai-banner ${job.status === 'error' ? 'txn-editor__ai-banner--error' : ''}`}
    >
      {job.status === 'error' ? (
        <>
          <AlertTriangle size={13} />
          {/* The specific reason, not just "it failed": the headline, then
              what to do, then — only when asked — the evidence. A model
              without vision and an unreadable photo produce the same stub,
              and only one of them is fixable in System → AI. */}
          {failure && <FailureDetails failure={failure} variant="banner" />}
        </>
      ) : (
        <>
          <Sparkles size={13} />
          <span>
            AI extracted from {job.kind === 'receipt' ? 'receipt' : 'text'}
            {job.result?.draft
              ? ` · ${Math.round((job.result.draft.confidence ?? 0) * 100)}% confidence`
              : ''}
          </span>
          {/* A description's words are its receipt: what the row is
              checked against, shown where the image would be. */}
          {job.kind === 'nl_parse' && job.payload.text && (
            <span className="txn-editor__ai-banner-note">You said: “{job.payload.text}”</span>
          )}
          {/* A field the read failed a check on, named with what was read:
              the confidence above is already capped, but a number does not
              say which field to look at. */}
          {checkNotes.map((note) => (
            <span key={note} className="txn-editor__ai-banner-note txn-editor__ai-banner-check">
              {note}
            </span>
          ))}
          {twin && (
            <span className="txn-editor__ai-banner-note txn-editor__ai-banner-check">
              This receipt looks already entered: the same amount on{' '}
              {formatters.formatDate(twin.date)}. If it’s the same one, delete this copy.{' '}
              <button
                type="button"
                className="txn-editor__ai-banner-link"
                onClick={() => {
                  onNavigate()
                  navigate(`/accounts/${twin.account_id}?highlight=${twin.transaction_id}`)
                }}
              >
                Show the other one
              </button>
            </span>
          )}
          {overruled && <span className="txn-editor__ai-banner-note">{overruled}</span>}
          {unresolvedCategoryNote(job.result?.draft) && (
            <span className="txn-editor__ai-banner-note">
              {unresolvedCategoryNote(job.result?.draft)}
            </span>
          )}
          <span className="txn-editor__ai-banner-note">
            <CardEndingNotice job={job} budgetId={budgetId} canMove={false} />
          </span>
          <ReadNotes read={job.result?.read} />
        </>
      )}
      {/* A failed read is tried again; a finished receipt can be scanned
          again too — after turning its photo upright in the viewer, say,
          which is the copy the scan reads. */}
      {(job.status === 'error' || (job.kind === 'receipt' && job.needs_review)) && (
        <button
          type="button"
          className="txn-editor__ai-banner-action"
          onClick={() => reprocess.mutate(job.id)}
          disabled={reprocess.isPending}
          title={
            job.status === 'error'
              ? undefined
              : 'Reads the attached photo again. Turn it upright in the photo viewer first if it’s sideways.'
          }
        >
          <RefreshCw size={12} />
          {job.status === 'error'
            ? reprocess.isPending
              ? 'Retrying…'
              : 'Try again'
            : reprocess.isPending
              ? 'Scanning…'
              : 'Scan again'}
        </button>
      )}
      {splitOffer !== null && (
        <button type="button" className="txn-editor__ai-banner-action" onClick={onApplySplit}>
          <Split size={12} />
          Apply suggested split ({splitOffer})
        </button>
      )}
    </div>
  )
}
