import type { ExplorerState } from './explorerMove'
import { CATCH_OUTS } from './catchOutList'
import './CatchOuts.css'

export function CatchOuts({ onTry }: { onTry: (state: ExplorerState) => void }) {
  return (
    <ul className="catch-outs">
      {CATCH_OUTS.map((c) => (
        <li key={c.id} className="catch-outs__item surface surface--raised">
          <div className="catch-outs__text">
            <h4 className="catch-outs__title">{c.title}</h4>
            <p className="catch-outs__detail">{c.detail}</p>
          </div>
          <button
            type="button"
            className="guide-link-button catch-outs__try"
            onClick={() => onTry(c.tryIt)}
            aria-label={`Try it in the explorer: ${c.title}`}
          >
            Try it
          </button>
        </li>
      ))}
    </ul>
  )
}
