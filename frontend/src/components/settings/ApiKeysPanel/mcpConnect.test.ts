import { describe, expect, it } from 'vitest'

import {
  KEY_PLACEHOLDER,
  MCP_CLIENTS,
  MCP_PATH,
  mcpAuthHeader,
  mcpClient,
  mcpConfigJson,
  mcpConnectCommand,
  mcpConnectionDetails,
  mcpConnectSnippet,
  mcpCurlCommand,
  mcpEndpoint,
} from './mcpConnect'

describe('mcpEndpoint', () => {
  it('appends the mount path to the origin the page is served from', () => {
    expect(mcpEndpoint('https://igab.example.com')).toBe('https://igab.example.com/api/v1/mcp/')
  })

  it('keeps a port, because a self-hosted install is usually on one', () => {
    expect(mcpEndpoint('http://192.168.1.10:8080')).toBe('http://192.168.1.10:8080/api/v1/mcp/')
  })

  it('ends in a slash, which is the URL that answers without a redirect', () => {
    // The sub-app is mounted at /api/v1/mcp and serves at /, so the
    // slashless form 307s. A client that does not follow redirects fails,
    // and nothing in its error would point here.
    expect(mcpEndpoint('https://x').endsWith('/api/v1/mcp/')).toBe(true)
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

describe('mcpConfigJson', () => {
  it('is valid JSON naming the endpoint and the header', () => {
    const parsed = JSON.parse(mcpConfigJson('https://igab.example.com', 'igab_abc123'))
    expect(parsed.mcpServers.igab.url).toBe('https://igab.example.com/api/v1/mcp/')
    expect(parsed.mcpServers.igab.headers.Authorization).toBe('Bearer igab_abc123')
  })

  it('falls back to the placeholder too', () => {
    expect(mcpConfigJson('https://x')).toContain(KEY_PLACEHOLDER)
  })
})

describe('mcpAuthHeader', () => {
  it('is the one line a client with no config file still needs', () => {
    expect(mcpAuthHeader('igab_abc123')).toBe('Authorization: Bearer igab_abc123')
  })
})

describe('mcpConnectSnippet', () => {
  it('picks the command for Claude Code', () => {
    expect(mcpConnectSnippet('claude-code', 'https://x', 'k')).toBe(
      mcpConnectCommand('https://x', 'k')
    )
  })

  it('picks the config block for a config-file client', () => {
    expect(mcpConnectSnippet('config-json', 'https://x', 'k')).toBe(mcpConfigJson('https://x', 'k'))
  })

  it('picks the full connection details for everything else', () => {
    // It used to be the bare header, which is the one fact nobody was
    // stuck on.
    expect(mcpConnectSnippet('other', 'https://x', 'k')).toBe(
      mcpConnectionDetails('https://x', 'k')
    )
    expect(mcpConnectSnippet('other', 'https://x', 'k')).toContain(mcpAuthHeader('k'))
  })

  it('picks the curl for the check-it-works option', () => {
    expect(mcpConnectSnippet('curl', 'https://x', 'k')).toBe(mcpCurlCommand('https://x', 'k'))
  })
})

describe('mcpConnectionDetails', () => {
  it('names the four things a setup form asks for', () => {
    const details = mcpConnectionDetails('https://igab.example.com', 'igab_abc123')
    expect(details).toContain('Streamable HTTP')
    expect(details).toContain('https://igab.example.com/api/v1/mcp/')
    expect(details).toContain('Authorization: Bearer igab_abc123')
    expect(details).toContain('no OAuth')
  })
})

describe('mcpCurlCommand', () => {
  it('is a single POST — tools/list needs no initialize, the server is stateless', () => {
    const curl = mcpCurlCommand('https://igab.example.com', 'igab_abc123')
    expect(curl).toContain('curl -X POST https://igab.example.com/api/v1/mcp/')
    expect(curl).toContain('Authorization: Bearer igab_abc123')
    expect(curl).toContain('"method":"tools/list"')
  })
})

describe('mcpClient', () => {
  it('names every kind in MCP_CLIENTS, so the picker can never show an id with no option behind it', () => {
    for (const c of MCP_CLIENTS) {
      expect(mcpClient(c.id)).toBe(c)
    }
  })
})
