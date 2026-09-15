import { Fragment } from 'react'
import { InfoPopover, InfoSection } from '../../common/InfoPopover/InfoPopover'
import { SYSTEM_TAG_HELP } from './systemTagHelp'
import { GuideTabLink } from '../../guide/GuideTabLink'

export function SystemTagsHelp() {
  return (
    <InfoPopover title="System tags" label="What system tags do" width={440}>
      <p>
        Every budget gets these tags. Their colour is yours to change; their names are not, and they
        cannot be deleted — unlike your own tags they change what the reports read, and the name is
        how you know which is which. Only some change how a transaction <strong>counts</strong>: a
        Savings category set to sent out, and Debt principal.
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
          Tag a category from its inspector on the Budget page. Any other tag you create is a label
          for filtering and grouping — it changes no number.
        </p>
        <p>
          <GuideTabLink tab="aside" anchor="which-tag">
            Which tag do I use?
          </GuideTabLink>
        </p>
      </InfoSection>
    </InfoPopover>
  )
}
