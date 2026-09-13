/**
 * Adding an asset asks which kind first. The sidebar's + went straight to the
 * New Account form and the Assets page went straight to the valued-asset form,
 * so the same words led to two unrelated dialogs with no explanation.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AddAssetFlow } from './AddAssetFlow'
import { useAppStore } from '../../stores/appStore'

vi.mock('../accounts/AddAccountModal', () => ({
  AddAccountModal: ({ initialTypeKey }: { initialTypeKey?: string }) => (
    <div>New Account form ({initialTypeKey})</div>
  ),
}))
vi.mock('./AssetSettingsModal', () => ({
  AssetSettingsModal: ({ asset }: { asset: unknown }) => (
    <div>Valued asset form ({asset === null ? 'create' : 'edit'})</div>
  ),
}))

beforeEach(async () => {
  // Each test opens the chooser Dialog; drain the last one's history.back().
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  useAppStore.setState({ currentBudgetId: 'b1' })
})

describe('AddAssetFlow', () => {
  it('offers both kinds before either form', () => {
    render(<AddAssetFlow onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Track its balance/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Track its value/ })).toBeInTheDocument()
    expect(screen.queryByText(/form/)).toBeNull()
  })

  it('continues to the New Account form for a balance', async () => {
    render(<AddAssetFlow onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /Track its balance/ }))
    expect(screen.getByText('New Account form (investment)')).toBeInTheDocument()
  })

  it('continues to the valued-asset form for a value', async () => {
    render(<AddAssetFlow onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /Track its value/ }))
    expect(screen.getByText('Valued asset form (create)')).toBeInTheDocument()
  })
})
