import type { MoneyRule } from '../../../api/moneyRules'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'
import { ClassChip } from './ClassChip'
import { MODE_PHRASE } from './moveAnswer'
import './RuleLadder.css'

/** "tag: Savings · when sent out" — the mode is served with the rule. */
const tagChip = (rule: Pick<MoneyRule, 'tag_key' | 'savings_mode'>) =>
  rule.tag_key === null
    ? ''
    : `tag: ${systemTagName(rule.tag_key)}${rule.savings_mode ? ` · ${MODE_PHRASE[rule.savings_mode]}` : ''}`

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

/** The classifier's rules in the order it tries them — served, so the ladder
 * on this page is the ladder the reports run. */
export function RuleLadder({ rules }: { rules: MoneyRule[] }) {
  return (
    <ol className="rule-ladder surface surface--raised" aria-label="Rules, first match wins">
      {rules.map((rule) => (
        <li key={rule.reason} className="rule-ladder__rule">
          <span className="rule-ladder__position" aria-hidden>
            {rule.is_default ? '—' : rule.position}
          </span>
          <span className="rule-ladder__when">
            {rule.is_default ? 'Otherwise: ' : ''}
            {sentence(rule.reason_text)}
            {rule.tag_key && <span className="rule-ladder__tag">{tagChip(rule)}</span>}
          </span>
          <ClassChip cls={rule.cls} label={rule.class_label} />
        </li>
      ))}
    </ol>
  )
}
