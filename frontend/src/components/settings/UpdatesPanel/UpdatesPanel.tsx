import { useQueryClient } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { useSettings, useUpdateSetting } from '../../../api/settings'
import { useUpdateStatus } from '../../../api/system'
import './UpdatesPanel.css'
import { ROOT } from '../../../api/queryKeys'

/** Opt-in update notification for self-hosted installs. Off by default —
 * the app never contacts GitHub until the toggle is switched on. */
export function UpdatesPanel() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const { data: status } = useUpdateStatus()
  const qc = useQueryClient()

  const enabled =
    settings?.find((s) => s.key === 'update_check_enabled')?.value === 'true'

  function toggle(next: boolean) {
    updateSetting.mutate(
      { key: 'update_check_enabled', value: next ? 'true' : 'false' },
      { onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.system] }) }
    )
  }

  return (
    <div className="updates-panel">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Check for updates</div>
          <div className="settings-row__desc">
            Compares this install against the latest GitHub release (checked at
            most every 6 hours). Off by default — nothing is sent until you
            enable it.
          </div>
        </div>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => toggle(e.target.checked)}
          aria-label="Check for updates"
        />
      </div>

      <div className="settings-row">
        <div>
          <div className="settings-row__label">Running version</div>
        </div>
        <span className="updates-panel__version tabular">
          {status?.current_version ?? '…'}
        </span>
      </div>

      {status?.enabled && status.update_available && (
        <div className="updates-panel__available">
          <span>
            Update available: <strong>{status.latest_version}</strong>
          </span>
          {status.release_url && (
            <a
              href={status.release_url}
              target="_blank"
              rel="noreferrer"
              className="updates-panel__release-link"
            >
              Release notes <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
      {status?.enabled && !status.update_available && status.latest_version && (
        <div className="updates-panel__current">
          Up to date (latest release: {status.latest_version})
        </div>
      )}
    </div>
  )
}
