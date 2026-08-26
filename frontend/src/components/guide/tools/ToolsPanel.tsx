import { useGuideStore } from '../../../stores/guideStore'
import { Surface } from '../../common/Surface'
import { TOOL_LIST, TOOLS } from './toolRegistry'
import { PayoffPlanner } from './PayoffPlanner'
import { PayVsSave } from './PayVsSave'
import { LoanCompare } from './LoanCompare'
import { EmergencyFundSizer } from './EmergencyFundSizer'
import './Tools.css'

/**
 * The Tools tab: one calculator at a time, chosen here or by a roadmap node.
 *
 * Every figure any of them shows is arithmetic you could check by hand.
 * There is no market-return projection and no tax modeling anywhere on this
 * tab, and the footer says so.
 */
export function ToolsPanel() {
  const activeTool = useGuideStore((s) => s.activeTool) ?? 'payoff-plan'
  const setActiveTool = useGuideStore((s) => s.setActiveTool)

  return (
    <section className="guide-tools">
      <header className="guide-tools__head">
        <div>
          <h2 className="guide-tools__title">Scenario tools</h2>
          <p className="guide-tools__lede">
            Calculators for the questions the roadmap raises, on your own numbers.
          </p>
        </div>
        <div className="guide-viewswitch" role="group" aria-label="Calculator">
          {TOOL_LIST.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`guide-viewswitch__button ${activeTool === t.id ? 'guide-viewswitch__button--active' : ''}`}
              aria-pressed={activeTool === t.id}
              onClick={() => setActiveTool(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <Surface as="div" className="guide-tools__card">
        <div className="guide-tools__strip surface surface--chrome">
          <p className="guide-tools__blurb">{TOOLS[activeTool].blurb}</p>
        </div>
        <div className="guide-tools__body">
          {activeTool === 'payoff-plan' && <PayoffPlanner />}
          {activeTool === 'pay-vs-save' && <PayVsSave />}
          {activeTool === 'loan-compare' && <LoanCompare />}
          {activeTool === 'emergency-fund' && <EmergencyFundSizer />}
        </div>
      </Surface>

      <p className="guide-tools__note">
        Plain arithmetic you can check, nothing more — no projected market returns, no tax
        modeling, no advice. Nothing you type here is saved.
      </p>
    </section>
  )
}
