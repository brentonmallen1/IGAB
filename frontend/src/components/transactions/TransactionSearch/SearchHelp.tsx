import { InfoPopover } from '../../common/InfoPopover/InfoPopover'
import './SearchHelp.css'

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
 */
export function SearchHelp() {
  return (
    <InfoPopover title="Searching transactions" label="How to search transactions" width={380}>
      <p>
        Type words to search <strong>payees and memos</strong>. A number on its
        own also matches that <strong>amount</strong> — <code>12.34</code> finds
        anything for $12.34, in or out.
      </p>
      <p>
        Add filters with a keyword and a colon. Every filter you add
        <strong> narrows</strong> the results:
      </p>
      <ul className="search-help__list">
        <li>
          <code>is:</code> state — <code>is: uncategorized</code>,{' '}
          <code>is: unapproved</code>, <code>is: cleared</code>,{' '}
          <code>is: transfer</code>
        </li>
        <li>
          <code>has:</code> attachments — <code>has: attachment</code>
        </li>
        <li>
          <code>category:</code> <code>payee:</code> <code>account:</code> by
          name — quote names with spaces: <code>category:"Dining Out"</code>
        </li>
        <li>
          <code>amount:</code> one value or a range —{' '}
          <code>amount: 12.34</code>, <code>amount:&gt;100</code>,{' '}
          <code>amount: 10-50</code>
        </li>
        <li>
          <code>date:</code> any span — a day, a month, a year, or a range
        </li>
      </ul>
      <p>
        <strong>Dates</strong> take whichever span you mean:{' '}
        <code>date: 2025</code>, <code>date: 2025-03</code>,{' '}
        <code>date: march 2025</code>, <code>date: 3/15</code>. Ranges and
        bounds use the same words — <code>date: march..june</code>,{' '}
        <code>date:&gt;2025-03</code>. Words like <code>today</code>,{' '}
        <code>last month</code> and <code>jan-mar</code> work on their own.
      </p>
      <p>
        Use <code>OR</code> to widen instead of narrow, and <code>NOT</code> to
        exclude: <code>is: uncategorized OR is: unapproved</code>,{' '}
        <code>NOT is: transfer</code>.
      </p>
      <p className="search-help__note">
        Each filter becomes a chip above the list — remove one to drop just
        that part. A chip outlined in <strong>warning colour</strong> is a part
        we could not read: it was ignored, so those results are wider than they
        look.
      </p>
    </InfoPopover>
  )
}
