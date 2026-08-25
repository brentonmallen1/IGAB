import { InfoPopover, InfoSection } from '../../common/InfoPopover/InfoPopover'

/**
 * What the search box can do, in concepts rather than syntax.
 *
 * The dropdown below the box is already a good completion menu — it lists
 * every token and fills one in. What it cannot teach is how the pieces fit:
 * that filters AND together unless you say OR, that the chips above the
 * register are individually removable, that a bare number also matches an
 * amount. Someone who never guesses that a query language exists never opens
 * the dropdown to find out.
 *
 * Kept short on purpose. This is the map; the dropdown is the dictionary.
 *
 * Structured on purpose too. The same words as one run of paragraphs were
 * unreadable — four topics with nothing between them but a line break. The
 * lede stays unlabelled because it answers "what do I type"; the labels start
 * where the vocabulary does.
 */
export function SearchHelp() {
  return (
    <InfoPopover title="Searching transactions" label="How to search transactions" width={420}>
      <p>
        Type words to search <strong>payees and memos</strong>. A number on its
        own also matches that <strong>amount</strong> — <code>12.34</code> finds
        anything for $12.34, in or out.
      </p>

      <InfoSection title="Filters">
        <p>
          A keyword and a colon. Every filter you add <strong>narrows</strong>{' '}
          the results.
        </p>
        <dl className="info-pop__terms">
          <dt>is:</dt>
          <dd>
            a state — <code>uncategorized</code>, <code>unapproved</code>,{' '}
            <code>cleared</code>, <code>transfer</code>
          </dd>

          <dt>has:</dt>
          <dd>
            attachments — <code>has: attachment</code>
          </dd>

          <dt>category:</dt>
          <dd>
            a category name — quote names with spaces:{' '}
            <code>category:"Dining Out"</code>
          </dd>

          <dt>payee:</dt>
          <dd>a payee name</dd>

          <dt>account:</dt>
          <dd>an account name</dd>

          <dt>amount:</dt>
          <dd>
            one value or a range — <code>12.34</code>, <code>&gt;100</code>,{' '}
            <code>10-50</code>
          </dd>

          <dt>date:</dt>
          <dd>any span — a day, a month, a year, or a range</dd>
        </dl>
      </InfoSection>

      <InfoSection title="Dates">
        <p>
          Dates take whichever span you mean: <code>date: 2025</code>,{' '}
          <code>date: 2025-03</code>, <code>date: march 2025</code>,{' '}
          <code>date: 3/15</code>. Ranges and bounds use the same words —{' '}
          <code>date: march..june</code>, <code>date:&gt;2025-03</code>. Words
          like <code>today</code>, <code>last month</code> and{' '}
          <code>jan-mar</code> work on their own.
        </p>
      </InfoSection>

      <InfoSection title="Combining">
        <p>
          Use <code>OR</code> to widen instead of narrow, and <code>NOT</code>{' '}
          to exclude: <code>is: uncategorized OR is: unapproved</code>,{' '}
          <code>NOT is: transfer</code>.
        </p>
      </InfoSection>

      <p className="info-pop__note">
        Each filter becomes a chip above the list — remove one to drop just
        that part. A chip outlined in <strong>warning colour</strong> is a part
        we could not read: it was ignored, so those results are wider than they
        look.
      </p>
    </InfoPopover>
  )
}
