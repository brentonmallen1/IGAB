/**
 * A failed scan explains itself in layers: the headline and what to do are
 * in view, the evidence waits behind Details.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AIJob, AIJobFailure } from '../../../api/aiJobs'
import { AIReviewBanner } from './AIReviewBanner'

function failedJob(failure: AIJobFailure | undefined, error: string): AIJob {
  return {
    id: 'job-1',
    kind: 'receipt',
    status: 'error',
    payload: {},
    result: failure ? { failure } : null,
    error,
  } as unknown as AIJob
}

function renderBanner(job: AIJob) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AIReviewBanner job={job} budgetId="b-1" splitOffer={null} onApplySplit={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const RAN_OUT: AIJobFailure = {
  headline: 'The model ran out of room before reaching the total.',
  next_step: 'Usually a long receipt with thinking on. Enter the details from the image.',
  technical: 'Cut off: output limit or context window reached\ngemma4:12b · thinking on',
  settings: 'System → AI → Advanced → Thinking',
}

describe('AIReviewBanner on a failed scan', () => {
  it('shows the headline and the next step, with a link named for the setting', () => {
    renderBanner(failedJob(RAN_OUT, 'ignored when the layers exist'))
    expect(screen.getByText(RAN_OUT.headline).tagName).toBe('STRONG')
    expect(screen.getByText(/Usually a long receipt with thinking on/)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Open System → AI → Advanced → Thinking' })
    ).toBeInTheDocument()
  })

  it('keeps the evidence behind Details', async () => {
    renderBanner(failedJob(RAN_OUT, ''))
    expect(screen.queryByText(/Cut off: output limit/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText(/Cut off: output limit/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Details' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('shows an older one-line failure as its headline, without Details', () => {
    renderBanner(failedJob(undefined, 'ReplyNotJSON: The model returned an empty reply.'))
    expect(screen.getByText('The model returned an empty reply.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument()
  })
})
