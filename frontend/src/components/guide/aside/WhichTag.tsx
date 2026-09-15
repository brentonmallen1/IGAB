import { DEFAULT_MARKER, savingsModeShort } from '../../../utils/savingsModes'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'
import { WHICH_TAG_ROWS, type WhichTagRow } from './whichTagRows'
import './WhichTag.css'

function modeText(row: WhichTagRow): string | null {
  if (row.mode === null) return null
  if (row.mode === 'either') return 'either works'
  const word = savingsModeShort(row.mode)
  return row.modeIsDefault ? `${word} ${DEFAULT_MARKER}` : word
}

/** What an envelope is for, and the tag that says so. */
export function WhichTag() {
  return (
    <div className="which-tag">
      <div className="which-tag__scroll surface surface--raised">
        <table className="which-tag__table" aria-label="Which tag to use">
          <thead>
            <tr>
              <th scope="col">The envelope is for…</th>
              <th scope="col">Tag it</th>
            </tr>
          </thead>
          <tbody>
            {WHICH_TAG_ROWS.map((row) => {
              const mode = modeText(row)
              return (
                <tr key={row.id}>
                  <th scope="row">{row.purpose}</th>
                  <td>
                    <span className="which-tag__tag">
                      {row.tags.map(systemTagName).join(' or ')}
                    </span>
                    {mode && <span className="which-tag__mode"> · {mode}</span>}
                    {row.note && <span className="which-tag__note">{row.note}</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="which-tag__warning">
        A category tagged both {systemTagName('savings')} and {systemTagName('long_term_expense')}{' '}
        gets a warning in its inspector: it is either savings or a bill you will pay, not both.
        Until you choose, it counts as savings.
      </p>
    </div>
  )
}
