import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAppStore } from '../../../stores/appStore'
import { useCardExamples } from '../../../api/guide'
import type { CardsAnchor } from '../../../utils/guideLinks'
import { guideTabHref } from '../../../utils/guideLinks'
import { CatchOuts } from '../CatchOuts'
import { CARD_CATCH_OUTS } from './cardCatchOuts'
import { CardWalkthrough } from './CardWalkthrough'
import '../GuideArticle.css'
import './CardsPanel.css'

function Section({
  anchor,
  title,
  lede,
  children,
}: {
  anchor: CardsAnchor
  title: string
  lede?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={anchor} className="guide-article__section" aria-labelledby={`${anchor}-title`}>
      <h3 className="guide-article__heading" id={`${anchor}-title`}>
        {title}
      </h3>
      {lede && <p className="guide-article__lede">{lede}</p>}
      {children}
    </section>
  )
}

/**
 * Credit cards: what the figures on the card row mean, and what happens to
 * them in the situations a card actually gets into.
 *
 * Examples only — nothing here reads the budget. Every walkthrough is the
 * app's own card situation, walked month by month by the card domain the
 * budget page serves from, so this tab cannot teach arithmetic the app does
 * not do.
 *
 * The reader picks how they use the card before they pick a situation. That
 * order is deliberate: most of what confuses people about card figures is
 * being shown a state that cannot happen to them — a paid-in-full reader does
 * not need the paydown loop, and somebody carrying debt does not need to be
 * told their Set aside looks short.
 */
export function CardsPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data, isLoading } = useCardExamples(budgetId)
  const [intent, setIntent] = useState<string | null>(null)
  const [openSlug, setOpenSlug] = useState<string | null>(null)

  const examples = data?.examples ?? []
  const shown = intent ? examples.filter((e) => e.intents.includes(intent)) : examples
  const chosen = data?.intents.find((i) => i.id === intent) ?? null

  return (
    <section className="guide-article">
      <header className="guide-roadmap__header">
        <div>
          <h2 className="guide-roadmap__title">Credit cards</h2>
          <p className="guide-roadmap__lede">
            A card purchase spends from an envelope like any other, but your cash stays in the bank
            until the bill arrives. Everything on a card row follows from that. Every amount here is
            an invented example; your own budget shows your figures. For how every transaction is
            counted, see <Link to={guideTabHref('money')}>How money counts</Link>.
          </p>
        </div>
      </header>

      <Section
        anchor="how-cards-work"
        title="The one idea"
        lede="Pay cash and the money leaves your account with the purchase. Pay by card and the envelope is still charged — but the cash it gave up is still sitting in your account, because the card fronted the purchase."
      >
        <ol className="cards-idea">
          <li>
            <b>Budget $200 into Groceries.</b> Ready to Assign falls by $200; Groceries holds it.
          </li>
          <li>
            <b>Buy $200 of groceries with the card.</b> Groceries empties. The $200 does not go back
            to Ready to Assign — the bill is coming — so it moves into{' '}
            <b>the card&rsquo;s envelope</b> and waits there as <b>Set aside</b>. Your bank balance
            has not moved.
          </li>
          <li>
            <b>Pay the bill by transfer from checking.</b> Now the $200 really leaves your account.
            Set aside empties and the balance falls with it.
          </li>
        </ol>
        <p className="guide-article__lede">
          Anything the card owes beyond Set aside is <b>Uncovered</b> — debt with nothing behind it.
          That is the whole model. Everything below is what happens when a month does not run that
          cleanly.
        </p>
      </Section>

      <Section
        anchor="how-you-use-it"
        title="How do you use this card?"
        lede="Pick the way you actually run it. The situations below narrow to the ones that can happen to you."
      >
        <div className="cards-intents" role="group" aria-label="How you use this card">
          {(data?.intents ?? []).map((i) => (
            <button
              key={i.id}
              type="button"
              className={`cards-intent ${intent === i.id ? 'is-on' : ''}`}
              aria-pressed={intent === i.id}
              onClick={() => setIntent(intent === i.id ? null : i.id)}
            >
              {i.label}
            </button>
          ))}
        </div>
        {chosen ? (
          <p className="cards-intent__detail">{chosen.detail}</p>
        ) : (
          <p className="cards-intent__detail">
            Nothing picked, so every situation is listed. None of them is a failure state — they are
            the shapes a card gets into.
          </p>
        )}
      </Section>

      <Section
        anchor="situations"
        title="What can happen, and what the card reads"
        lede="Each one is a situation the app is built and tested against. Open it to walk the months."
      >
        {isLoading && <p className="guide-article__lede">Reading the examples…</p>}
        {!isLoading && shown.length === 0 && (
          <p className="guide-article__lede">No situation is listed for that choice.</p>
        )}
        <ul className="cards-situations">
          {shown.map((e) => {
            const open = openSlug === e.slug
            return (
              <li key={e.slug} className="cards-situation surface surface--raised">
                <button
                  type="button"
                  className="cards-situation__head"
                  aria-expanded={open}
                  onClick={() => setOpenSlug(open ? null : e.slug)}
                >
                  <span className="cards-situation__title">{e.title}</span>
                  <span className="cards-situation__card">{e.card}</span>
                </button>
                {open && (
                  <div className="cards-situation__body">
                    {/* Three labelled beats, not a paragraph. Each answers a
                      question a reader actually has, in the order they have
                      them — and each is one line, so the whole situation can
                      be taken in before deciding whether to walk the months
                      below it. */}
                    <dl className="cards-lesson">
                      <div className="cards-lesson__beat">
                        <dt>What happens</dt>
                        <dd>{e.happens}</dd>
                      </div>
                      <div className="cards-lesson__beat">
                        <dt>What you see</dt>
                        <dd>{e.reads}</dd>
                      </div>
                      <div className="cards-lesson__beat">
                        <dt>What to do</dt>
                        <dd>{e.todo}</dd>
                      </div>
                    </dl>
                    <CardWalkthrough example={e} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </Section>

      <div id="card-catch-outs" className="guide-article__section">
        <h3 className="guide-article__heading">Things that catch people out</h3>
        <CatchOuts items={CARD_CATCH_OUTS} />
      </div>
    </section>
  )
}
