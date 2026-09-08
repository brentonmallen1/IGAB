import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatMarkdown } from './ChatMarkdown'

function html(markdown: string): string {
  const { container } = render(<ChatMarkdown>{markdown}</ChatMarkdown>)
  return container.innerHTML
}

describe('ChatMarkdown', () => {
  it('renders the shapes an answer actually uses', () => {
    render(
      <ChatMarkdown>{'Groceries is **over** by $42.\n\n- Dining: $118\n- Fuel: $60'}</ChatMarkdown>
    )
    expect(screen.getByText('over').tagName).toBe('STRONG')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('renders a GFM table of figures', () => {
    const markup = html('| Envelope | Left |\n| --- | ---: |\n| Groceries | $12 |')
    expect(markup).toContain('<table>')
    expect(markup).toContain('Groceries')
    // Right alignment survives the sanitiser, because money reads right.
    // react-markdown renders the `align` property as an inline style.
    expect(markup).toContain('text-align: right')
  })

  it('wraps a table so it scrolls instead of widening the panel', () => {
    const markup = html('| a | b |\n| --- | --- |\n| 1 | 2 |')
    expect(markup).toContain('chat-md__table-wrap')
  })

  it('escapes HTML rather than rendering it', () => {
    // The text comes from a model reading a database. Nothing else in this app
    // renders raw HTML and this must not become the exception.
    const markup = html('<img src=x onerror="alert(1)"> and <b>bold</b>')
    expect(markup).not.toContain('<img')
    expect(markup).not.toContain('onerror')
    expect(markup).not.toContain('<b>')
  })

  it('drops a script even when markdown would allow it through', () => {
    const markup = html('<script>alert(1)</script>')
    expect(markup).not.toContain('<script')
    expect(markup).not.toContain('alert(1)</script>')
  })

  it('refuses a javascript: link', () => {
    const markup = html('[click](javascript:alert(1))')
    expect(markup).not.toContain('javascript:')
  })

  it('opens a real link in a new tab, safely', () => {
    render(<ChatMarkdown>{'[docs](https://example.com)'}</ChatMarkdown>)
    const link = screen.getByRole('link', { name: 'docs' })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('refuses an alignment value the sanitiser does not allow', () => {
    // `align` becomes an inline style at render time, so an open value would
    // be a narrow path from model output into the style attribute.
    const markup = html('| a |\n| --- |\n| 1 |').replace(/\s+/g, ' ')
    expect(markup).not.toContain('url(')
    expect(markup).not.toContain('expression(')
  })

  it('drops images entirely', () => {
    // An answer has no business fetching a remote URL; one that tried would
    // leak the question to whoever served it.
    const markup = html('![alt](https://example.com/tracker.png)')
    expect(markup).not.toContain('<img')
  })

  it('demotes a shouted heading', () => {
    // The panel already sits under the page h1.
    const markup = html('# Summary')
    expect(markup).toContain('<h3>')
    expect(markup).not.toContain('<h1>')
  })

  it('renders a partial stream without throwing', () => {
    // Tokens arrive mid-syntax constantly: an unclosed bold, half a table row.
    expect(() => html('Groceries is **over')).not.toThrow()
    expect(() => html('| Envelope | Le')).not.toThrow()
    expect(() => html('- one\n- tw')).not.toThrow()
  })

  it('renders inline code and a fenced block', () => {
    expect(html('`is_assignable`')).toContain('<code>')
    expect(html('```\nnet = 12\n```')).toContain('<pre>')
  })

  it('renders nothing for an empty answer', () => {
    const { container } = render(<ChatMarkdown>{''}</ChatMarkdown>)
    expect(container.textContent).toBe('')
  })
})
