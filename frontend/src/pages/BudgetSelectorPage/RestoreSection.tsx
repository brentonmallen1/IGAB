import { ArrowRight, DatabaseBackup } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Surface } from '../../components/common/Surface'
import { sectionHref } from '../SettingsPage/settingsSections'

/**
 * The way back from an empty budget list.
 *
 * Restore lives in System → Server Backups, which is its own route outside
 * the budget shell precisely so it is reachable from here. But "reachable"
 * and "findable" are different things: a person staring at a budget picker
 * with nothing in it, after a restore that went wrong, is not going to guess
 * that the fix is behind a link in the header. This card says it where they
 * are looking. Admin-only, matching the endpoints.
 */
export function RestoreSection() {
  return (
    <Surface as="section" className="selector-card selector-card--restore">
      <div className="selector-card__body selector-card__body--row">
        <DatabaseBackup size={18} className="selector-card__icon" aria-hidden="true" />
        <div>
          <div className="section-label surface__title">Restore from a Backup</div>
          <div className="selector-card__subtitle">
            Server backups replace every budget from a database dump. They live in System settings,
            with updates, users and bank connections.
          </div>
        </div>
        <Link
          to={sectionHref({ id: 'data', page: 'system' })}
          className="selector-btn selector-btn--secondary selector-card__link"
        >
          Server Backups
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    </Surface>
  )
}
