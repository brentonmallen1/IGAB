import { useRef, useState } from 'react'
import { useMoneyRules } from '../../../api/moneyRules'
import { useAppStore } from '../../../stores/appStore'
import { Surface } from '../../common/Surface'
import { CatchOuts } from './CatchOuts'
import { DEFAULT_EXPLORER, type ExplorerState } from './explorerMove'
import { MoneyExplorer } from './MoneyExplorer'
import { RuleLadder } from './RuleLadder'
import { TagImpact } from './TagImpact'
import { TwoFacts } from './TwoFacts'
import { WorkedMonth } from './WorkedMonth'
import './MoneyPanel.css'

/**
 * How money counts: what decides whether a row is income, spending, saving or
 * just a move — and so what every report and the savings rate add up.
 *
 * Nothing on this tab classifies anything. The ladder, the explorer's
 * answers and the worked month's figures are served by the rules the reports
 * run (`backend/.../domain/money_moves.py`); the prose around them is the
 * only thing written here.
 */
export function MoneyPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: rules, isError } = useMoneyRules(budgetId)
  const [explorer, setExplorer] = useState<ExplorerState>(DEFAULT_EXPLORER)
  const explorerRef = useRef<HTMLElement>(null)

  function tryIt(state: ExplorerState) {
    setExplorer(state)
    explorerRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  return (
    <section className="money-panel">
      <header className="guide-roadmap__header">
        <div>
          <h2 className="guide-roadmap__title">How money counts</h2>
          <p className="guide-roadmap__lede">
            Every transaction is counted as income, spending, saving or just a move between your
            accounts. Two facts decide which, and the reports and your savings rate add up the
            result.
          </p>
        </div>
      </header>

      <div className="money-panel__section">
        <h3 className="money-panel__heading">Two facts decide it</h3>
        <TwoFacts />
      </div>

      <div className="money-panel__section">
        <h3 className="money-panel__heading">The rules, in order</h3>
        <p className="money-panel__lede">
          Each transaction is checked against these from the top, and the first that matches
          decides. A tag you chose always comes before a guess from the accounts.
        </p>
        {isError ? (
          <p className="money-panel__status">The rules could not be loaded.</p>
        ) : rules ? (
          <RuleLadder rules={rules.rules} />
        ) : (
          <p className="money-panel__status">Loading…</p>
        )}
      </div>

      <section className="money-panel__section" ref={explorerRef} aria-labelledby="money-try">
        <h3 className="money-panel__heading" id="money-try">
          Try a move
        </h3>
        <Surface as="div" className="money-panel__card">
          <MoneyExplorer
            state={explorer}
            onChange={setExplorer}
            families={rules?.report_families ?? []}
          />
        </Surface>
      </section>

      <div className="money-panel__section">
        <h3 className="money-panel__heading">What the tags do</h3>
        {rules && <TagImpact rules={rules.rules} />}
      </div>

      <div className="money-panel__section">
        <h3 className="money-panel__heading">A worked month</h3>
        <p className="money-panel__lede">
          One made-up household’s month, counted the way your reports would count it.
        </p>
        <WorkedMonth />
      </div>

      <div className="money-panel__section">
        <h3 className="money-panel__heading">Things that catch people out</h3>
        <CatchOuts onTry={tryIt} />
      </div>
    </section>
  )
}
