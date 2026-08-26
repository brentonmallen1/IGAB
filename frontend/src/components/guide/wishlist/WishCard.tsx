import { ArrowDown, ArrowUp, ExternalLink } from 'lucide-react'
import type { Wish, WishlistProject } from '../../../api/wishlist'
import { useFormatters } from '../../../hooks/useFormatters'
import { coolingLabel, fundingLabel, reachLabel } from './wishlistCopy'

interface Props {
  wish: Wish
  project?: WishlistProject | null
  showProject?: boolean
  hero?: boolean
  onEdit: () => void
  onDone: () => void
  onDrop: () => void
  onDelete: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}

/**
 * One wish: what it costs, where its money lives, how far off it is.
 *
 * While the cooling-off period runs the Done button is there but quiet —
 * the friction is the feature, not a lock. Everything shown is served; the
 * bar is the served progress, net of wishes ahead in the same envelope.
 */
export function WishCard({
  wish,
  project,
  showProject = false,
  hero = false,
  onEdit,
  onDone,
  onDrop,
  onDelete,
  onMoveUp,
  onMoveDown,
}: Props) {
  const fmt = useFormatters()
  const cooling = coolingLabel(wish, fmt)
  const progress = wish.reach && wish.reach.state !== 'unlinked' ? Number(wish.reach.progress) : null
  const pct = progress === null ? 0 : Math.round(Math.min(1, Math.max(0, progress)) * 100)

  return (
    <article className={`wish ${hero ? 'wish--hero' : ''} ${wish.cooling ? 'wish--cooling' : ''}`}>
      <div className="wish__head">
        <h4 className="wish__name">
          {wish.url ? (
            <a href={wish.url} target="_blank" rel="noreferrer" className="wish__link">
              {wish.name}
              <ExternalLink size={11} aria-hidden />
            </a>
          ) : (
            wish.name
          )}
        </h4>
        <span className="wish__cost tabular">{fmt.formatMoney(Number(wish.cost))}</span>
      </div>

      <p className="wish__funding">
        {fundingLabel(wish)}
        {showProject && project && <span className="wish__chip">{project.name}</span>}
      </p>

      {progress !== null && (
        <div
          className="wish__bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label={`${pct}% funded`}
        >
          <div className="wish__bar-fill" style={{ width: `${pct}%` }} />
        </div>
      )}

      <p className={`wish__reach ${wish.reach?.state === 'now' ? 'wish__reach--now' : ''}`}>
        {reachLabel(wish, fmt)}
      </p>
      {cooling && <p className="wish__cooling">{cooling}</p>}
      {wish.notes && <p className="wish__notes">{wish.notes}</p>}

      <div className="wish__actions">
        <button
          type="button"
          className={`wish__done ${wish.cooling ? 'wish__done--quiet' : ''}`}
          onClick={onDone}
          title={wish.cooling ? 'Still cooling off — but it is your call' : 'Bought it, or did it'}
        >
          Done
        </button>
        <button type="button" className="guide-link-button" onClick={onEdit}>
          Edit
        </button>
        <button type="button" className="guide-link-button" onClick={onDrop}>
          Drop
        </button>
        <button type="button" className="guide-link-button wish__delete" onClick={onDelete}>
          Delete
        </button>
        {(onMoveUp || onMoveDown) && (
          <span className="wish__move">
            <button type="button" className="tool__icon-button" onClick={onMoveUp} disabled={!onMoveUp} aria-label={`Move ${wish.name} up`}>
              <ArrowUp size={13} />
            </button>
            <button type="button" className="tool__icon-button" onClick={onMoveDown} disabled={!onMoveDown} aria-label={`Move ${wish.name} down`}>
              <ArrowDown size={13} />
            </button>
          </span>
        )}
      </div>
    </article>
  )
}
