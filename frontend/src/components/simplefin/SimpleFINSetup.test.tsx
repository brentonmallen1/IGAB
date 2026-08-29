import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SimpleFINSetup } from './SimpleFINSetup'
import { useSetupSimpleFIN, useSimpleFINConfig } from '../../api/simplefin'
import { useCurrentUser } from '../../api/auth'

vi.mock('../../api/simplefin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/simplefin')>()),
  useSimpleFINConfig: vi.fn(),
  useSetupSimpleFIN: vi.fn(),
}))

vi.mock('../../api/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/auth')>()),
  useCurrentUser: vi.fn(),
}))

const GENERATE = 'python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'

type ConfigQuery = ReturnType<typeof useSimpleFINConfig>

function config(data: unknown, extra: Record<string, unknown> = {}): ConfigQuery {
  return {
    data,
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
    ...extra,
  } as unknown as ConfigQuery
}

beforeEach(() => {
  vi.mocked(useSetupSimpleFIN).mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useSetupSimpleFIN>)
  vi.mocked(useCurrentUser).mockReturnValue({
    data: { id: 'u1', email: 'a@b.c', is_admin: true },
  } as unknown as ReturnType<typeof useCurrentUser>)
})

describe('SimpleFINSetup', () => {
  it('offers the token form when the server is configured', () => {
    vi.mocked(useSimpleFINConfig).mockReturnValue(
      config({ configured: true, problem: null, generate_key_command: GENERATE })
    )

    render(<SimpleFINSetup onDone={() => {}} />)

    expect(screen.getByPlaceholderText(/paste setup token/i)).toBeInTheDocument()
  })

  it('does not render a token field when the server has no encryption key', () => {
    // The safety property, not a cosmetic one: SimpleFIN setup tokens are
    // single-use, so a server that cannot store the result must not accept one.
    vi.mocked(useSimpleFINConfig).mockReturnValue(
      config({
        configured: false,
        problem: 'SIMPLEFIN_ENCRYPTION_KEY is not set on the server.',
        generate_key_command: GENERATE,
      })
    )

    render(<SimpleFINSetup onDone={() => {}} />)

    expect(screen.queryByPlaceholderText(/paste setup token/i)).not.toBeInTheDocument()
    expect(screen.getByText(/SIMPLEFIN_ENCRYPTION_KEY is not set/)).toBeInTheDocument()
  })

  it('shows an admin the command and where the key goes', () => {
    vi.mocked(useSimpleFINConfig).mockReturnValue(
      config({ configured: false, problem: 'Key missing.', generate_key_command: GENERATE })
    )

    render(<SimpleFINSetup onDone={() => {}} />)

    expect(screen.getByText(GENERATE)).toBeInTheDocument()
    expect(screen.getByText(/Advanced View/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /check again/i })).toBeInTheDocument()
  })

  it('tells a non-admin who to ask instead of how to fix it', () => {
    vi.mocked(useCurrentUser).mockReturnValue({
      data: { id: 'u2', email: 'x@y.z', is_admin: false },
    } as unknown as ReturnType<typeof useCurrentUser>)
    vi.mocked(useSimpleFINConfig).mockReturnValue(
      config({ configured: false, problem: 'Key missing.', generate_key_command: GENERATE })
    )

    render(<SimpleFINSetup onDone={() => {}} />)

    expect(screen.getByText(/Ask whoever runs this server/)).toBeInTheDocument()
    expect(screen.queryByText(GENERATE)).not.toBeInTheDocument()
  })
})
