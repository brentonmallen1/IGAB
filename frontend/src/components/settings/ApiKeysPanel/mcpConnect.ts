/**
 * The endpoint and the connect instructions, said once per client.
 *
 * Two places need them and they are read months apart: the dialog that shows
 * a key the one time the key exists, and the section itself, which has to
 * answer "how do I connect this?" for someone whose key is already in a
 * config file somewhere. Writing the path twice is how the two disagree the
 * first time it moves.
 *
 * It is a plain bearer token specifically so it is vendor-agnostic, but
 * "vendor-agnostic" is a property of the protocol, not of what a person has
 * to type — a Claude Code command and a claude_desktop_config.json entry are
 * both "just a header", spelled two different ways. So this names the shapes
 * a client actually asks for (a CLI flag, a JSON block, a form's worth of
 * connection details, and a curl to prove it all works) rather than trying
 * to describe the click-path of every desktop app and local-model front end,
 * which would be guesswork today and wrong by next release.
 *
 * Ollama and ChatGPT are the two that get asked about and neither is an MCP
 * client: Ollama runs models, and ChatGPT's connectors are a different
 * protocol. What connects is whatever MCP-aware thing sits in front of them,
 * and that thing wants the connection details below.
 */

/**
 * Where the MCP transport actually answers.
 *
 * The TRAILING SLASH is load-bearing and was found by running the curl below
 * against a real server: the app mounts the sub-app at `/api/v1/mcp` and the
 * sub-app serves at `/`, so `POST /api/v1/mcp` gets a 307 to
 * `/api/v1/mcp/` and only the slashed form answers 200 directly. A client
 * that follows redirects never notices; one that does not just fails, and
 * "it 307s" is not a thing anyone debugging their own MCP config would
 * think to check. Printing the canonical URL everywhere costs nothing and
 * removes the whole class of failure.
 */
export const MCP_PATH = '/api/v1/mcp/'

/**
 * What stands in for the key where there is no key to show.
 *
 * The server keeps only a hash, so the section can never reprint one. It
 * shows the shape instead, which is the part someone actually needs to be
 * reminded of.
 */
export const KEY_PLACEHOLDER = 'igab_your_key_here'

/** The name a client sees for this server. */
export const MCP_SERVER_NAME = 'igab'

export type McpClientKind = 'claude-code' | 'config-json' | 'other' | 'curl'

export interface McpClientOption {
  id: McpClientKind
  /** What the picker calls it. */
  label: string
  /** What the field holding its snippet is called. */
  fieldLabel: string
  /** What the copy button says. */
  copyLabel: string
}

/** In picker order — Claude Code first because it is the one this app can
 *  name with certainty; the JSON shape covers most desktop clients that
 *  keep a config file (Claude Desktop among them); the details block is
 *  what every other client's setup form asks for; and curl is for when one
 *  of those forms has been filled in and it still isn't working. */
export const MCP_CLIENTS: McpClientOption[] = [
  { id: 'claude-code', label: 'Claude Code', fieldLabel: 'Command', copyLabel: 'Copy command' },
  {
    id: 'config-json',
    label: 'Claude Desktop / a config file',
    fieldLabel: 'Config',
    copyLabel: 'Copy config',
  },
  {
    id: 'other',
    label: 'Any other client',
    fieldLabel: 'Connection details',
    copyLabel: 'Copy details',
  },
  { id: 'curl', label: 'Check it works (curl)', fieldLabel: 'Command', copyLabel: 'Copy command' },
]

export function mcpEndpoint(origin: string): string {
  return `${origin}${MCP_PATH}`
}

export function mcpAuthHeader(key: string = KEY_PLACEHOLDER): string {
  return `Authorization: Bearer ${key}`
}

export function mcpConnectCommand(origin: string, key: string = KEY_PLACEHOLDER): string {
  return (
    `claude mcp add --transport http ${MCP_SERVER_NAME} ${mcpEndpoint(origin)} ` +
    `--header "${mcpAuthHeader(key)}"`
  )
}

/**
 * The `mcpServers` block most config-file clients share — Claude Desktop's
 * own file among them — for a remote server reached over HTTP with a bearer
 * header. Not every client that keeps a config file uses this exact shape,
 * but it is the common one, and closer to what someone needs than nothing.
 */
export function mcpConfigJson(origin: string, key: string = KEY_PLACEHOLDER): string {
  return JSON.stringify(
    {
      mcpServers: {
        [MCP_SERVER_NAME]: {
          url: mcpEndpoint(origin),
          headers: { Authorization: `Bearer ${key}` },
        },
      },
    },
    null,
    2
  )
}

/**
 * Every fact a setup form asks for, in the words those forms use.
 *
 * This is what "any MCP client" actually needs, and it is four things, not
 * one — a bare `Authorization:` line (which is what this used to print) is
 * the least useful of the four on its own, because it answers the question
 * nobody was stuck on.
 */
export function mcpConnectionDetails(origin: string, key: string = KEY_PLACEHOLDER): string {
  return [
    `Transport   Streamable HTTP (one POST per call)`,
    `URL         ${mcpEndpoint(origin)}`,
    `Header      ${mcpAuthHeader(key)}`,
    `Auth        Static bearer token — no OAuth, no login flow`,
  ].join('\n')
}

/**
 * One call that proves the endpoint, the key and the scope all work.
 *
 * `tools/list` with no `initialize` first is a real single request because
 * the server is stateless (`stateless_http=True`); this was run against a
 * live server before being printed here, and answers 200 with the tool
 * list. It is the thing to try when a client's own setup screen says only
 * that it could not connect.
 */
export function mcpCurlCommand(origin: string, key: string = KEY_PLACEHOLDER): string {
  return (
    `curl -X POST ${mcpEndpoint(origin)} \\\n` +
    `  -H "${mcpAuthHeader(key)}" \\\n` +
    `  -H "Content-Type: application/json" \\\n` +
    `  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`
  )
}

/** The one thing to show below the endpoint, for whichever client is
 *  selected — the endpoint itself is shown once, above, regardless of kind. */
export function mcpConnectSnippet(
  kind: McpClientKind,
  origin: string,
  key: string = KEY_PLACEHOLDER
): string {
  switch (kind) {
    case 'claude-code':
      return mcpConnectCommand(origin, key)
    case 'config-json':
      return mcpConfigJson(origin, key)
    case 'other':
      return mcpConnectionDetails(origin, key)
    case 'curl':
      return mcpCurlCommand(origin, key)
  }
}

export function mcpClient(kind: McpClientKind): McpClientOption {
  return MCP_CLIENTS.find((c) => c.id === kind) ?? MCP_CLIENTS[0]
}
