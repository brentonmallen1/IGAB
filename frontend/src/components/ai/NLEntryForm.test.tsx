/**
 * Describe sends the words and gets out of the way. It used to wait on the
 * model inline and fill the form — long enough, on a local model, that
 * nobody at a checkout would. Now it is queued like a receipt.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  submit: vi.fn(),
  status: { enabled: true, available: false },
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('../../api/ai', () => ({ useAIStatus: () => ({ data: h.status }) }))
vi.mock('../../api/aiJobs', () => ({
  useSubmitDescription: () => ({ mutateAsync: h.submit, isPending: false }),
}))
vi.mock('../../hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    supported: false,
    listening: false,
    transcript: '',
    interim: '',
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
  }),
}))
vi.mock('react-hot-toast', () => ({ default: { success: h.success, error: h.error } }))

import { NLEntryForm } from './NLEntryForm'

function renderForm(accountId: string | null, onQueued = vi.fn()) {
  render(
    <MemoryRouter>
      <NLEntryForm budgetId="b1" accountId={accountId} onQueued={onQueued} autoFocus={false} />
    </MemoryRouter>
  )
  return onQueued
}

const box = () => screen.getByRole('textbox')
const send = () => screen.getByRole('button', { name: 'Send' })

beforeEach(() => {
  h.submit.mockReset()
  h.submit.mockResolvedValue({ id: 'job-1' })
  h.success.mockClear()
  h.error.mockClear()
  h.status = { enabled: true, available: false }
})

describe('NLEntryForm', () => {
  it('sends the words with the account and hands back at once', async () => {
    const onQueued = renderForm('acc-1')
    fireEvent.change(box(), { target: { value: ' coffee 5.50 yesterday ' } })
    fireEvent.click(send())

    await waitFor(() => expect(onQueued).toHaveBeenCalled())
    expect(h.submit).toHaveBeenCalledWith({ text: 'coffee 5.50 yesterday', accountId: 'acc-1' })
    expect(h.success).toHaveBeenCalledWith(
      expect.stringMatching(/show up in your transactions to review/),
      expect.anything()
    )
  })

  it('sends with no account, and says where it will wait', async () => {
    const onQueued = renderForm(null)
    expect(screen.getByText(/waits in AI Activity until you pick one/)).toBeTruthy()
    fireEvent.change(box(), { target: { value: 'coffee 5.50' } })
    fireEvent.keyDown(box(), { key: 'Enter' })

    await waitFor(() => expect(onQueued).toHaveBeenCalled())
    expect(h.submit).toHaveBeenCalledWith({ text: 'coffee 5.50', accountId: null })
    expect(h.success).toHaveBeenCalledWith(
      expect.stringMatching(/waits in AI Activity/),
      expect.anything()
    )
  })

  it('keeps the words when sending fails', async () => {
    h.submit.mockRejectedValue(new Error('offline'))
    const onQueued = renderForm('acc-1')
    fireEvent.change(box(), { target: { value: 'coffee 5.50' } })
    fireEvent.click(send())

    await waitFor(() => expect(h.error).toHaveBeenCalled())
    expect(onQueued).not.toHaveBeenCalled()
    expect(box()).toHaveValue('coffee 5.50')
  })

  it('is offered while the model is down, since the queue waits for it', () => {
    // enabled, not available — the scan button's gate
    renderForm('acc-1')
    expect(send()).toBeTruthy()
  })

  it('points at Settings when AI is not set up at all', () => {
    h.status = { enabled: false, available: false }
    renderForm('acc-1')
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByText(/Configure AI/)).toBeTruthy()
  })
})
