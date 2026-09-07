/**
 * A backup that finished says so.
 *
 * "Backup queued" was the last thing the page said. The 3-second poll did
 * refresh the file list, but nothing announced the finish, so the new file
 * looked like it needed a manual refresh. The panel now watches the job
 * leave queued/running and toasts once per run.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { success, error, refetch, state } = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  refetch: vi.fn(),
  // A box the tests write and the mocked hook reads: vi.mock is hoisted, so
  // the factory cannot close over a plain `let`.
  state: { overview: {} as Record<string, unknown> },
}))
vi.mock('react-hot-toast', () => ({ default: { success, error } }))

vi.mock('../../../api/backups', () => ({
  useBackups: () => ({ data: state.overview, isLoading: false, refetch }),
  useRunBackup: () => ({ mutate: vi.fn(), isPending: false }),
  useRestoreBackup: () => ({ mutateAsync: vi.fn(), isPending: false }),
  fetchBackupStatus: vi.fn(),
  downloadBackupFile: vi.fn(),
}))
vi.mock('../../../api/settings', () => ({
  useSettings: () => ({ data: [] }),
  useUpdateSetting: () => ({ mutate: vi.fn(), isPending: false }),
}))

import { BackupsPanel } from './BackupsPanel'

function job(over: Record<string, unknown> = {}) {
  return {
    action: 'backup',
    state: 'done',
    detail: null,
    finished_at: '2026-09-06T10:00:00Z',
    ...over,
  }
}

beforeEach(() => {
  success.mockClear()
  error.mockClear()
  refetch.mockClear()
  state.overview = { agent_online: true, queued: false, job: null, files: [] }
})

describe('BackupsPanel', () => {
  it('announces a backup that finished while the page was open', async () => {
    state.overview = {
      agent_online: true,
      queued: false,
      job: job({ state: 'running' }),
      files: [],
    }
    const { rerender } = render(<BackupsPanel />)
    expect(success).not.toHaveBeenCalled()

    state.overview = { agent_online: true, queued: false, job: job(), files: [] }
    rerender(<BackupsPanel />)

    await waitFor(() => expect(success).toHaveBeenCalledWith('Backup finished'))
    expect(refetch).toHaveBeenCalled()
  })

  it('says what failed rather than a bare failure', async () => {
    state.overview = { agent_online: true, queued: true, job: null, files: [] }
    const { rerender } = render(<BackupsPanel />)
    state.overview = {
      agent_online: true,
      queued: false,
      job: job({ state: 'error', detail: 'no space left on device' }),
      files: [],
    }
    rerender(<BackupsPanel />)
    await waitFor(() =>
      expect(error).toHaveBeenCalledWith('Backup failed — no space left on device')
    )
  })

  it('does not re-announce a run that finished before the page opened', async () => {
    state.overview = { agent_online: true, queued: false, job: job(), files: [] }
    const { rerender } = render(<BackupsPanel />)
    rerender(<BackupsPanel />)
    await waitFor(() => expect(screen.getByText(/back up now/i)).toBeInTheDocument())
    expect(success).not.toHaveBeenCalled()
  })
})
