/**
 * The endpoint and the connect command, said once.
 *
 * Two places need them and they are read months apart: the dialog that shows
 * a key the one time the key exists, and the section itself, which has to
 * answer "how do I connect this?" for someone whose key is already in a
 * config file somewhere. Writing the path twice is how the two disagree the
 * first time it moves.
 */

/** Where the MCP transport is mounted. Matches the `app.mount` in main.py. */
export const MCP_PATH = '/api/v1/mcp'

/**
 * What stands in for the key where there is no key to show.
 *
 * The server keeps only a hash, so the section can never reprint one. It
 * shows the shape instead, which is the part someone actually needs to be
 * reminded of.
 */
export const KEY_PLACEHOLDER = 'igab_your_key_here'

export function mcpEndpoint(origin: string): string {
  return `${origin}${MCP_PATH}`
}

export function mcpConnectCommand(origin: string, key: string = KEY_PLACEHOLDER): string {
  return (
    `claude mcp add --transport http igab ${mcpEndpoint(origin)} ` +
    `--header "Authorization: Bearer ${key}"`
  )
}
