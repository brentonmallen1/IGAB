import { AlertTriangle, RefreshCw, Sparkles, Split } from 'lucide-react'
import { type AIJob, useReprocessAIJob } from '../../../api/aiJobs'
import { useFormatters } from '../../../hooks/useFormatters'
import { draftCheckNotes, unresolvedCategoryNote } from '../../ai/draftNotes'
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
}

/** The review banner over an AI-drafted row: where it came from and how
 *  sure the model was, or — when the job failed — the specific reason and a
 *  retry. Its own component so the editor holds the form, not every banner
 *  the form can carry. */
export function AIReviewBanner({ job, budgetId, splitOffer, onApplySplit }: Props) {
  const reprocess = useReprocessAIJob(budgetId)
  const formatters = useFormatters()
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
      {job.status === 'error' && (
        <button
          type="button"
          className="txn-editor__ai-banner-action"
          onClick={() => reprocess.mutate(job.id)}
          disabled={reprocess.isPending}
        >
          <RefreshCw size={12} />
          {reprocess.isPending ? 'Retrying…' : 'Try again'}
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
