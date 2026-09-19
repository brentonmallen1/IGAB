import { PageHeader } from '../../components/common/PageHeader/PageHeader'
import { useCurrentUser } from '../../api/auth'
import { useSimpleFINConfig } from '../../api/simplefin'
import { SyncLogsPanel } from '../../components/settings/SyncLogsPanel/SyncLogsPanel'
import { AISettingsPanel } from '../../components/settings/AISettingsPanel'
import { AIStatusBadge } from '../../components/settings/AIStatusBadge'
import { AI_STATUS_LABEL, useAIStatusTone } from '../../components/settings/aiStatus'
import { BackupsPanel } from '../../components/settings/BackupsPanel/BackupsPanel'
import {
  SettingsShell,
  type SectionPanel,
} from '../../components/settings/SettingsShell/SettingsShell'
import { SimpleFINPanel } from '../../components/settings/SimpleFINPanel/SimpleFINPanel'
import { UpdatesPanel } from '../../components/settings/UpdatesPanel/UpdatesPanel'
import { UsersPanel } from '../../components/settings/UsersPanel/UsersPanel'
import { useAppStore } from '../../stores/appStore'
import {
  SETTINGS_PAGES,
  visibleSettingsSections,
  type SettingsSectionId,
} from '../SettingsPage/settingsSections'
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
  const isAdmin = !!me?.is_admin
  const aiTone = useAIStatusTone()

  const sections = visibleSettingsSections({
    budgetId,
    isAdmin,
    page: 'system',
    sfWarn: sfConfig && !sfConfig.configured ? 'Bank sync is not configured' : undefined,
  })

  // Back to wherever the person came from: the open budget's settings, or the
  // picker when there is no budget — which is the case this page exists for.
  const back = budgetId
    ? { to: SETTINGS_PAGES.settings.path, label: 'Budget settings' }
    : { to: '/budgets', label: 'Budgets' }

  // Admin-only panels are simply absent for everyone else, matching the
  // endpoints; the registry already keeps their nav entries out.
  const panels: Partial<Record<SettingsSectionId, SectionPanel>> = {
    updates: { body: <UpdatesPanel /> },
    simplefin: { body: <SimpleFINPanel /> },
    ai: { body: <AISettingsPanel />, titleAside: <AIStatusBadge /> },
    ...(isAdmin
      ? {
          data: { body: <BackupsPanel /> },
          'sync-logs': { body: <SyncLogsPanel /> },
          users: { body: <UsersPanel /> },
        }
      : {}),
  }

  return (
    <div className="system-page">
      <header className="system-page__header">
        <PageHeader
          title={SETTINGS_PAGES.system.label}
          back={back}
          subtitle="The whole installation — every budget, every user"
        />
      </header>

      <div className="system-page__body">
        <SettingsShell
          page="system"
          sections={sections}
          panels={panels}
          hints={{
            simplefin: sfConfig ? (sfConfig.configured ? 'Connected' : 'Not set up') : undefined,
            ai: AI_STATUS_LABEL[aiTone],
          }}
          navLabel="System sections"
        />
      </div>
    </div>
  )
}
