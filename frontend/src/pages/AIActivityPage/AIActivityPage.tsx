import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { PageHeader } from '../../components/common/PageHeader/PageHeader'
import { AI_ACTIVITY_TABS, resolveTab, type AIActivityTab } from './aiActivityTabs'
import { ScansTab } from './tabs/ScansTab'
import { ChatsTab } from './tabs/ChatsTab'
import { ModelCallsTab } from './tabs/ModelCallsTab'
import './AIActivityPage.css'

/**
 * What the AI has done, in three views.
 *
 * Shell-plus-tab-router, the same shape as ReportsPage and GuidePage. The page
 * was one list of scan jobs; the model-call log needed somewhere to live, and
 * so did the chat history, and three flat sections stacked down one page would
 * have buried the one you came for.
 */
export function AIActivityPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [tab, setTab] = useState<AIActivityTab>('scans')
  const active = resolveTab(tab)
  const definition = AI_ACTIVITY_TABS.find((t) => t.id === active)!

  return (
    <div className="ai-activity page-fill">
      <PageHeader
        title="AI Activity"
        titleNode={
          <>
            <Sparkles size={18} />
            AI Activity
          </>
        }
      />

      <nav className="ai-activity__tabs" aria-label="AI activity views">
        {AI_ACTIVITY_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`ai-activity__tab ${t.id === active ? 'ai-activity__tab--active' : ''}`}
            onClick={() => setTab(t.id)}
            aria-current={t.id === active ? 'page' : undefined}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* A label is not enough for the second, less technical person this app
          is built for — each tab says what it is. */}
      <p className="ai-activity__desc">{definition.blurb}</p>

      {budgetId && active === 'scans' && <ScansTab budgetId={budgetId} />}
      {budgetId && active === 'chats' && <ChatsTab budgetId={budgetId} />}
      {budgetId && active === 'calls' && <ModelCallsTab budgetId={budgetId} />}
    </div>
  )
}
