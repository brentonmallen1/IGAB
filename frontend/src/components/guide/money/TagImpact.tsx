import type { MoneyRule } from '../../../api/moneyRules'
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { GuideTabLink } from '../GuideTabLink'
import { ClassChip } from './ClassChip'
import { savingsModeLabel } from '../../../utils/savingsModes'
import './TagImpact.css'

/** What each system tag does. The words are the Tags panel's own; whether a
 * tag changes a row's class — and for which savings mode — is read off the
 * served rules (`tag_keys`, `savings_mode`), not written here. So Emergency
 * fund shows the Savings rule because the server says that rule reads it. */
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
            const rule = rules.find((r) => r.tag_keys.includes(tag.key))
            return (
              <tr key={tag.key}>
                <th scope="row">{tag.name}</th>
                <td>
                  {rule ? (
                    <span className="tag-impact__class">
                      <ClassChip cls={rule.cls} label={rule.class_label} />
                      {rule.savings_mode && (
                        <span className="tag-impact__mode">
                          {savingsModeLabel(rule.savings_mode)}
                        </span>
                      )}
                    </span>
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
      <p className="tag-impact__more">
        What setting money aside counts as:{' '}
        <GuideTabLink tab="aside" anchor="savings-modes">
          Setting money aside
        </GuideTabLink>
      </p>
    </div>
  )
}
