import { Fragment } from 'react'
import { InfoPopover, InfoSection } from '../../common/InfoPopover/InfoPopover'
import { SYSTEM_TAG_HELP } from './systemTagHelp'

export function SystemTagsHelp() {
  return (
    <InfoPopover title="System tags" label="What system tags do" width={440}>
      <p>
        Every budget gets these five tags. They can be renamed or recoloured but not
        deleted, because unlike your own tags they change how IGAB <strong>counts</strong>{' '}
        money.
      </p>

      <InfoSection title="Each one">
        <dl className="info-pop__terms info-pop__terms--plain">
          {SYSTEM_TAG_HELP.map((t) => (
            <Fragment key={t.key}>
              <dt>{t.name}</dt>
              <dd>
                <span className="info-pop__term-on">on {t.on}</span> {t.does}
              </dd>
            </Fragment>
          ))}
        </dl>
      </InfoSection>

      <InfoSection title="Applying them">
        <p>
          Tag a category from its inspector on the Budget page, or a payee from the Payees
          page. Any other tag you create is a label for filtering and grouping — it changes
          no number.
        </p>
      </InfoSection>
    </InfoPopover>
  )
}
