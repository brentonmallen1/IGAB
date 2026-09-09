import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { normalizeFigures } from './figures'
import './ChatMarkdown.css'

const SCHEMA = {
  ...defaultSchema,
  tagNames: [
    // h1/h2 are allowed through so the component mapping below can demote
    // them. Stripping them here instead would delete the element before that
    // runs, leaving a heading as bare unstyled text.
    'h1',
    'h2',
    'p',
    'br',
    'strong',
    'em',
    'del',
    'code',
    'pre',
    'blockquote',
    'ul',
    'ol',
    'li',
    'table',
    'thead',
    'tbody',
    'tr',
    'th',
    'td',
    'h3',
    'h4',
    'hr',
    'a',
  ],
  attributes: {
    ...defaultSchema.attributes,
    // GFM tables carry column alignment, and nothing else here needs an
    // attribute at all. The value is pinned to the three it can legitimately
    // be: react-markdown turns `align` into an inline style when it renders,
    // so leaving the value open would be a narrow way for model output to
    // reach the style attribute.
    th: [['align', 'left', 'center', 'right']],
    td: [['align', 'left', 'center', 'right']],
    a: ['href', 'title'],
  },
  protocols: { ...defaultSchema.protocols, href: ['http', 'https'] },
}

export const ChatMarkdown = memo(function ChatMarkdown({ children }: { children: string }) {
  return (
    <div className="chat-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, SCHEMA]]}
        components={{
          // A link in an answer points outside the app, so it opens outside it
          // — and carries the rel that stops the new tab reaching back.
          a: ({ href, children: label }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {label}
            </a>
          ),
          // Headings are demoted: the panel already sits under an h1, and a
          // model writing "# Summary" should not outrank the page title.
          h1: ({ children: c }) => <h3>{c}</h3>,
          h2: ({ children: c }) => <h3>{c}</h3>,
          // A wide table scrolls inside its own box rather than widening the
          // panel, which is only ~360px.
          table: ({ children: c }) => (
            <div className="chat-md__table-wrap">
              <table>{c}</table>
            </div>
          ),
        }}
      >
        {normalizeFigures(children)}
      </ReactMarkdown>
    </div>
  )
})
