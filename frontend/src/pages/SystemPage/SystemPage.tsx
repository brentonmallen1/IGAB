import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useCurrentUser } from '../../api/auth'
import { useSimpleFINConfig } from '../../api/simplefin'
import { Surface } from '../../components/common/Surface'
import { AISettingsPanel } from '../../components/settings/AISettingsPanel'
import { BackupsPanel } from '../../components/settings/BackupsPanel/BackupsPanel'
import { SettingsShell } from '../../components/settings/SettingsShell/SettingsShell'
import { SimpleFINPanel } from '../../components/settings/SimpleFINPanel/SimpleFINPanel'
import { UpdatesPanel } from '../../components/settings/UpdatesPanel/UpdatesPanel'
import { UsersPanel } from '../../components/settings/UsersPanel/UsersPanel'
import { useAppStore } from '../../stores/appStore'
import { SETTINGS_PAGES, visibleSettingsSections } from '../SettingsPage/settingsSections'
import './SystemPage.css'

/**
 * Settings for the whole installation — every budget, every user.
 *
 * Its own route outside the budget shell, on purpose. The shell redirects to
 * the budget picker whenever there is no budget to show, and these are the
 * controls you need precisely then: the database has been emptied, or
 * replaced, or never had anything in it, and the way back is a server backup.
 * Until this page existed you had to create a throwaway budget to reach the
 * restore button, writing to the very database you were about to overwrite.
 *
 * Which sections belong here is decided once, in settingsSections.ts.
 */
export function SystemPage() {
  const { data: me } = useCurrentUser()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: sfConfig } = useSimpleFINConfig()

  const sections = visibleSettingsSections({
    budgetId,
    isAdmin: !!me?.is_admin,
    page: 'system',
    sfWarn: sfConfig && !sfConfig.configured ? 'Bank sync is not configured' : undefined,
  })

  // Back to wherever the person came from: the open budget's settings, or the
  // picker when there is no budget — which is the case this page exists for.
  const back = budgetId
    ? { to: SETTINGS_PAGES.settings.path, label: 'Budget settings' }
    : { to: '/budgets', label: 'Budgets' }

  return (
    <div className="system-page">
      <header className="system-page__header">
        <Link to={back.to} className="system-page__back">
          <ArrowLeft size={15} />
          <span>{back.label}</span>
        </Link>
        <div>
          <h1 className="system-page__title">{SETTINGS_PAGES.system.label}</h1>
          <div className="system-page__subtitle">
            The whole installation — every budget, every user
          </div>
        </div>
      </header>

      <div className="system-page__body">
        <SettingsShell sections={sections} navLabel="System sections">
          {/* Whole-application backups and restore. Admin-only, matching the
              endpoints. */}
          {me?.is_admin && (
            <Surface as="section" className="settings-section" id="data" title="Server Backups">
              <div className="settings-section__body">
                <BackupsPanel />
              </div>
            </Surface>
          )}

          <Surface as="section" className="settings-section" id="updates" title="Updates">
            <div className="settings-section__body">
              <UpdatesPanel />
            </div>
          </Surface>

          <Surface
            as="section"
            className="settings-section"
            id="simplefin"
            title="SimpleFIN Bank Connection"
          >
            <div className="settings-section__body">
              <SimpleFINPanel />
            </div>
          </Surface>

          <AISettingsPanel />

          {me?.is_admin && (
            <Surface as="section" className="settings-section" id="users" title="Users">
              <div className="settings-section__body">
                <UsersPanel />
              </div>
            </Surface>
          )}
        </SettingsShell>
      </div>
    </div>
  )
}
