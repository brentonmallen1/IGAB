import type { MoneyRule } from '../../../api/moneyRules'
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { ClassChip } from './ClassChip'
import './TagImpact.css'

/** What each system tag does. The words are the Tags panel's own; whether a
 * tag changes a row's class is read off the served rules, not written here. */
export function TagImpact({ rules }: { rules: MoneyRule[] }) {
  return (
    <div className="tag-impact surface surface--raised">
      <table className="tag-impact__table" aria-label="What each tag does">
        <thead>
          <tr>
            <th scope="col">Tag</th>
            <th scope="col">Changes class?</th>
            <th scope="col">What it does</th>
          </tr>
        </thead>
        <tbody>
          {SYSTEM_TAG_HELP.map((tag) => {
            const rule = rules.find((r) => r.tag_key === tag.key)
            return (
              <tr key={tag.key}>
                <th scope="row">{tag.name}</th>
                <td>
                  {rule ? (
                    <ClassChip cls={rule.cls} label={rule.class_label} />
                  ) : (
                    <span className="tag-impact__no">No</span>
                  )}
                </td>
                <td className="tag-impact__does">{tag.does}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
