import './CatchOuts.css'

/** One thing that catches people out: a title and a sentence or two. */
export interface CatchOutItem {
  id: string
  title: string
  detail: string
}

/** A button beside each item — "Try it" on How money counts, which loads the
 * item's move into the explorer. */
export interface CatchOutAction<T extends CatchOutItem> {
  label: string
  /** The button's accessible name for one item. */
  describe: (item: T) => string
  run: (item: T) => void
}

/** "Things that catch people out", for every Guide tab that has some. */
export function CatchOuts<T extends CatchOutItem>({
  items,
  action,
}: {
  items: readonly T[]
  action?: CatchOutAction<T>
}) {
  return (
    <ul className="catch-outs">
      {items.map((c) => (
        <li key={c.id} className="catch-outs__item surface surface--raised">
          <div className="catch-outs__text">
            <h4 className="catch-outs__title">{c.title}</h4>
            <p className="catch-outs__detail">{c.detail}</p>
          </div>
          {action && (
            <button
              type="button"
              className="guide-link-button catch-outs__try"
              onClick={() => action.run(c)}
              aria-label={action.describe(c)}
            >
              {action.label}
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}
