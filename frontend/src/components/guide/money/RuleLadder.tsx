import type { MoneyRule } from '../../../api/moneyRules'
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { ClassChip } from './ClassChip'
import './RuleLadder.css'

const tagName = (key: string) => SYSTEM_TAG_HELP.find((t) => t.key === key)?.name ?? key

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
            {rule.tag_key && <span className="rule-ladder__tag">tag: {tagName(rule.tag_key)}</span>}
          </span>
          <ClassChip cls={rule.cls} label={rule.class_label} />
        </li>
      ))}
    </ol>
  )
}
