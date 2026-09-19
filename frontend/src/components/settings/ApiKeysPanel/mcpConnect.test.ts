import { describe, expect, it } from 'vitest'

import { KEY_PLACEHOLDER, MCP_PATH, mcpConnectCommand, mcpEndpoint } from './mcpConnect'

describe('mcpEndpoint', () => {
  it('appends the mount path to the origin the page is served from', () => {
    expect(mcpEndpoint('https://igab.example.com')).toBe('https://igab.example.com/api/v1/mcp')
  })

  it('keeps a port, because a self-hosted install is usually on one', () => {
    expect(mcpEndpoint('http://192.168.1.10:8080')).toBe('http://192.168.1.10:8080/api/v1/mcp')
  })
})

describe('mcpConnectCommand', () => {
  it('carries a real key when there is one to carry', () => {
    const command = mcpConnectCommand('https://igab.example.com', 'igab_abc123')
    expect(command).toContain('https://igab.example.com/api/v1/mcp')
    expect(command).toContain('Authorization: Bearer igab_abc123')
  })

  it('falls back to the placeholder, which is what the settings section shows', () => {
    // The server stores only a hash, so a key cannot be reprinted. The
    // section still has to answer "how do I connect", so it shows the shape.
    expect(mcpConnectCommand('https://igab.example.com')).toContain(
      `Authorization: Bearer ${KEY_PLACEHOLDER}`
    )
  })

  it('is one string both places build, so the path cannot disagree', () => {
    expect(mcpConnectCommand('https://x', 'k')).toContain(MCP_PATH)
    expect(mcpEndpoint('https://x')).toContain(MCP_PATH)
  })
})
