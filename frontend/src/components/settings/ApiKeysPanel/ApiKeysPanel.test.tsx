import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiKey } from '../../../api/apiKeys'

const hooks = vi.hoisted(() => ({
  keys: [] as ApiKey[],
  create: vi.fn(),
  revoke: vi.fn(),
}))

vi.mock('../../../api/apiKeys', () => ({
  useApiKeys: () => ({ data: hooks.keys, isLoading: false }),
  useCreateApiKey: () => ({ mutateAsync: hooks.create, isPending: false }),
  useRevokeApiKey: () => ({ mutateAsync: hooks.revoke }),
}))

vi.mock('../../../api/budgets', () => ({
  useBudgets: () => ({ data: [{ id: 'b1', name: 'Household' }] }),
}))

import { ApiKeysPanel } from './ApiKeysPanel'

function key(over: Partial<ApiKey> = {}): ApiKey {
  return {
    id: 'k1',
    name: 'Claude on the laptop',
    prefix: 'igab_abc123',
    scopes: 'read',
    budget_ids: ['b1'],
    created_at: '2026-09-18T10:00:00Z',
    last_used_at: null,
    revoked_at: null,
    ...over,
  }
}

beforeEach(async () => {
  // Dialog pushes a history entry per mount and pops it on close; drain the
  // queue so a stale pop cannot close the next test's dialog. Without this
  // the failures alternate, which reads like flakiness rather than a shared
  // history stack.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')

  hooks.keys = []
  hooks.create.mockReset()
  hooks.revoke.mockReset()
})

describe('how to connect', () => {
  it('shows the endpoint and the command with no key in existence', () => {
    // The question arrives long after the one moment a key is printable: a
    // new laptop, a second client, a key already sitting in a config file.
    // Before this, the command lived only in the dialog that shows a new
    // key — the one moment nobody needs reminding.
    hooks.keys = []
    render(<ApiKeysPanel />)

    expect(screen.getByText(`${window.location.origin}/api/v1/mcp/`)).toBeInTheDocument()
    expect(screen.getByText(/claude mcp add --transport http igab/)).toBeInTheDocument()
  })

  it('stands in for the key it can never reprint', () => {
    hooks.keys = [key()]
    render(<ApiKeysPanel />)
    expect(screen.getByText('igab_your_key_here')).toBeInTheDocument()
  })

  it('switches the snippet when a different client is picked', async () => {
    // Claude Code is the only client this ever named. Ollama, ChatGPT and
    // everything else still only need an endpoint and a header — picking
    // "Something else" is what proves that isn't hidden behind one CLI
    // command.
    const user = userEvent.setup()
    render(<ApiKeysPanel />)

    expect(screen.getByText(/claude mcp add --transport http igab/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Client'), 'Any other client')
    expect(screen.queryByText(/claude mcp add/)).not.toBeInTheDocument()
    // Not just the header: the transport and the URL are the parts a
    // client's own setup form actually asks for.
    const details = screen.getByText(/Streamable HTTP/)
    expect(details).toHaveTextContent('Authorization: Bearer igab_your_key_here')
    expect(details).toHaveTextContent(`${window.location.origin}/api/v1/mcp/`)

    await user.selectOptions(screen.getByLabelText('Client'), 'Claude Desktop / a config file')
    expect(screen.getByText(/"mcpServers"/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Client'), 'Check it works (curl)')
    expect(screen.getByText(/curl -X POST/)).toHaveTextContent('"method":"tools/list"')
  })
})

describe('the key list', () => {
  it('shows only the prefix, never the key', () => {
    // The server kept a hash. Nothing on this screen can reconstruct a key,
    // which is the whole reason it is shown once at creation.
    hooks.keys = [key()]
    render(<ApiKeysPanel />)
    expect(screen.getByText(/igab_abc123…/)).toBeInTheDocument()
  })

  it('keeps a revoked key listed, marked', () => {
    // A key that turns up in a config file or a log has to stay
    // identifiable after it stops working.
    hooks.keys = [key({ revoked_at: '2026-09-18T12:00:00Z' })]
    render(<ApiKeysPanel />)
    expect(screen.getByText('revoked')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Revoke/ })).not.toBeInTheDocument()
  })

  it('says when a key has never been used', () => {
    hooks.keys = [key()]
    render(<ApiKeysPanel />)
    expect(screen.getByText('Never')).toBeInTheDocument()
  })
})

describe('creating a key', () => {
  it('shows the key once, and says that it cannot be shown again', async () => {
    const user = userEvent.setup()
    hooks.create.mockResolvedValue({ ...key(), key: 'igab_the-actual-secret' })
    render(<ApiKeysPanel />)

    await user.click(screen.getByRole('button', { name: /New key/ }))
    await user.type(screen.getByLabelText(/Name/), 'Claude on the laptop')
    await user.click(screen.getByLabelText('Household'))
    await user.click(screen.getByRole('button', { name: 'Create key' }))

    await waitFor(() =>
      expect(screen.getByDisplayValue('igab_the-actual-secret')).toBeInTheDocument()
    )
    expect(screen.getByText(/one time it can be shown/i)).toBeInTheDocument()
  })

  it('offers a command that any MCP client could use', async () => {
    const user = userEvent.setup()
    hooks.create.mockResolvedValue({ ...key(), key: 'igab_the-actual-secret' })
    render(<ApiKeysPanel />)

    await user.click(screen.getByRole('button', { name: /New key/ }))
    await user.type(screen.getByLabelText(/Name/), 'Claude on the laptop')
    await user.click(screen.getByLabelText('Household'))
    await user.click(screen.getByRole('button', { name: 'Create key' }))

    await waitFor(() => expect(screen.getByText(/Authorization header/i)).toBeInTheDocument())
  })

  it('carries the real key into whichever client snippet is picked', async () => {
    const user = userEvent.setup()
    hooks.create.mockResolvedValue({ ...key(), key: 'igab_the-actual-secret' })
    render(<ApiKeysPanel />)

    await user.click(screen.getByRole('button', { name: /New key/ }))
    await user.type(screen.getByLabelText(/Name/), 'Claude on the laptop')
    await user.click(screen.getByLabelText('Household'))
    await user.click(screen.getByRole('button', { name: 'Create key' }))

    const dialog = await screen.findByRole('dialog', { name: 'Your new key' })
    await user.selectOptions(within(dialog).getByLabelText('Client'), 'Check it works (curl)')
    const shown = dialog.querySelector('textarea') as HTMLTextAreaElement
    expect(shown.value).toContain('Authorization: Bearer igab_the-actual-secret')
    expect(shown.value).toContain('curl -X POST')
  })

  it('says why rather than disabling the button', async () => {
    // The dialog standard: a primary that will not say why it is refusing
    // is the thing this repo stopped shipping.
    const user = userEvent.setup()
    render(<ApiKeysPanel />)

    await user.click(screen.getByRole('button', { name: /New key/ }))
    const create = screen.getByRole('button', { name: 'Create key' })
    expect(create).toBeEnabled()

    await user.click(create)
    expect(screen.getByText(/Give the key a name and pick a budget/)).toBeInTheDocument()
    expect(hooks.create).not.toHaveBeenCalled()
  })

  it('refuses a name with no budget chosen', async () => {
    const user = userEvent.setup()
    render(<ApiKeysPanel />)

    await user.click(screen.getByRole('button', { name: /New key/ }))
    await user.type(screen.getByLabelText(/Name/), 'Nameless')
    await user.click(screen.getByRole('button', { name: 'Create key' }))

    expect(hooks.create).not.toHaveBeenCalled()
  })
})

describe('revoking', () => {
  it('revokes the key it names', async () => {
    const user = userEvent.setup()
    hooks.keys = [key()]
    hooks.revoke.mockResolvedValue(undefined)
    render(<ApiKeysPanel />)

    await user.click(screen.getByRole('button', { name: /Revoke Claude on the laptop/ }))
    expect(hooks.revoke).toHaveBeenCalledWith('k1')
  })
})
