import {
  useDeleteSimpleFINConnection,
  useSimpleFINConnections,
  useSimpleFINRateLimitStatus,
  useUpdateSimpleFINConnection,
} from '../../../api/simplefin'
import { useFormatters } from '../../../hooks/useFormatters'
import { confirmAsync } from '../../../stores/confirmStore'
import { SimpleFINConfigNotice, SimpleFINSetup } from '../../simplefin/SimpleFINSetup'
import { SyncSchedule } from '../SyncSchedule/SyncSchedule'
import './SimpleFINPanel.css'

/**
 * The SimpleFIN connection: setup when there is none, and the sync switch,
 * schedule, quota and last error when there is.
 *
 * A connection belongs to the installation, not to a budget — the same bank
 * feed serves every budget that links an account to it — which is why this
 * lives on the System page. (Which budget's accounts sync is decided where
 * the accounts are.)
 */
export function SimpleFINPanel() {
  const { formatDateTime } = useFormatters()
  const { data: connections } = useSimpleFINConnections()
  const updateConnection = useUpdateSimpleFINConnection()
  const deleteConnection = useDeleteSimpleFINConnection()

  const firstConnectionId = connections && connections.length > 0 ? connections[0].id : null
  const { data: rateLimitStatus } = useSimpleFINRateLimitStatus(firstConnectionId)

  if (!connections || connections.length === 0) {
    // The setup form shows the encryption-key notice itself.
    return <SimpleFINSetup onDone={() => {}} />
  }

  return (
    <>
      {/* Only when connections already exist: a key lost or rotated after
          setup breaks every sync, and the list below would just fail without
          saying why. */}
      <SimpleFINConfigNotice />
      {connections.map((conn) => (
        <div key={conn.id} className="sf-connection">
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Sync enabled</div>
              <div className="settings-row__desc">
                Last synced: {conn.last_sync_at ? formatDateTime(conn.last_sync_at) : 'Never'}
              </div>
            </div>
            <input
              type="checkbox"
              checked={conn.sync_enabled}
              onChange={(e) =>
                updateConnection.mutate({ id: conn.id, sync_enabled: e.target.checked })
              }
            />
          </div>

          <SyncSchedule connection={conn} />

          {rateLimitStatus && (
            <div className="sf-usage">
              <div className="sf-usage__row">
                <span className="sf-usage__label">Global syncs today</span>
                <span className="sf-usage__count">{rateLimitStatus.global_used} / 12</span>
              </div>
              <div className="sf-usage__bar">
                <div
                  className="sf-usage__fill"
                  style={{ transform: `scaleX(${Math.min(1, rateLimitStatus.global_used / 12)})` }}
                />
              </div>
              <div className="sf-usage__row" style={{ marginTop: 6 }}>
                <span className="sf-usage__label">Account syncs today</span>
                <span className="sf-usage__count">{rateLimitStatus.account_used} / 12</span>
              </div>
              <div className="sf-usage__bar">
                <div
                  className="sf-usage__fill"
                  style={{ transform: `scaleX(${Math.min(1, rateLimitStatus.account_used / 12)})` }}
                />
              </div>
              <div className="sf-usage__reset">Resets at midnight UTC</div>
            </div>
          )}

          {conn.last_sync_error && (
            <div className="sf-error">
              <span className="sf-error__label">Last sync error</span>
              <span className="sf-error__msg">{conn.last_sync_error}</span>
              {conn.last_sync_error_at && (
                <span className="sf-error__time">{formatDateTime(conn.last_sync_error_at)}</span>
              )}
            </div>
          )}

          <div style={{ paddingTop: 4 }}>
            <button
              className="settings-btn settings-btn--danger"
              onClick={async () => {
                const ok = await confirmAsync({
                  title: 'Remove this SimpleFIN connection?',
                  confirmLabel: 'Remove',
                  destructive: true,
                })
                if (ok) deleteConnection.mutate(conn.id)
              }}
            >
              Remove connection
            </button>
          </div>
        </div>
      ))}
    </>
  )
}
