/**
 * The money roadmap — an ordered path through personal finance priorities.
 *
 * Adapted from the r/personalfinance "Personal Income Spending Flowchart"
 * (u/atlaswoid, 2016, itself based on an earlier chart by u/beached89). The
 * *decisions* are that community's; the wording here is our own, rewritten to
 * be shorter, to say what each step means inside IGAB, and to be renderable
 * across 40 theme variants on a phone. The original is credited and linked
 * from the roadmap footer.
 *
 * ── Why this is data and not JSX ────────────────────────────────────────────
 * Three views render this same array: Journey (one stage at a time), Browse
 * (everything expanded, both sides of every decision) and, later, Map. One
 * authoring pass, three renderings. A node added here appears in all of them.
 *
 * ── Editing rules ───────────────────────────────────────────────────────────
 * 1. `body` is what everyone reads: 1-3 sentences, no jargon, no hedging.
 *    `detail` is for the person who wants the reasoning and is hidden until
 *    asked for. If a sentence is only interesting to someone already engaged,
 *    it belongs in `detail`.
 * 2. Never state a figure that changes yearly (contribution caps, tax
 *    brackets). "The yearly limit" ages well; a dollar amount goes stale and
 *    quietly becomes wrong. Rate-of-thumb thresholds from the source chart
 *    (~10%, ~4-5%, 15%, 3-6 months) are stable and are stated as
 *    approximations, which is how the chart states them.
 * 3. Anything US-specific carries `region: 'us'` so non-US content can be
 *    hidden later without re-authoring. Do not add a locale setting for it yet.
 * 4. This is education, not advice. Describe the common path and the tradeoff;
 *    never tell the reader what they should do with their money.
 */

import type { GlossaryId } from './glossary'

/** Facts about the user's own money that a node can display.
 *
 * Nothing resolves these yet — detection lands with the signals work. The keys
 * are declared here because the content is what decides which facts are worth
 * computing, and a node referencing a key that detection never implements is a
 * type error rather than a silent blank. */
export type SignalKey =
  | 'budget_exists'
  | 'essential_expenses'
  | 'emergency_fund'
  | 'employer_match'
  | 'high_interest_debt'
  | 'moderate_interest_debt'
  | 'retirement_contributions'
  | 'hsa'
  | 'college_savings'

export type StageId =
  | 'foundation'
  | 'starter-emergency-fund'
  | 'employer-match'
  | 'high-interest-debt'
  | 'full-emergency-fund'
  | 'moderate-interest-debt'
  | 'retirement-and-near-term'
  | 'retirement-fifteen'
  | 'other-goals'

/** Where a decision's answer leads. Exactly one of the two is set. */
export interface RoadmapBranch {
  /** The answer itself — "Yes", "No", "Not sure". */
  answer: string
  /** What that answer means, in one line. */
  label: string
  /** Jump to another node in this stage… */
  toNode?: string
  /** …or move on to another stage entirely. */
  toStage?: StageId
}

/** The scenario calculators on the Tools tab. A node names the one that
 *  answers its question; the registry of labels lives with the components. */
export const TOOL_IDS = ['payoff-plan', 'pay-vs-save', 'loan-compare', 'emergency-fund'] as const
export type ToolId = (typeof TOOL_IDS)[number]

export interface RoadmapNode {
  id: string
  kind: 'action' | 'decision' | 'note'
  title: string
  /** Always visible once the stage is open. Keep it short. */
  body: string
  /** Hidden behind "Why this matters" — the reasoning, the tradeoff, the
   *  common mistake. Present for most nodes; never required reading. */
  detail?: string
  /** Decision nodes only. */
  branches?: RoadmapBranch[]
  /** Glossary terms worth offering inline. Checked against the glossary at
   *  compile time — a term that does not exist will not typecheck. */
  glossary?: GlossaryId[]
  /** Deep links into the app, so a step can be acted on where it lives. */
  appLinks?: { label: string; to: string }[]
  /** The user's own number this node would show, once detection exists. */
  signal?: SignalKey
  /** Which of the concept's targets this node reads. Only the emergency fund
   *  has two — a starter cushion, then the full three to six months — and
   *  the starter node is the one that reads the smaller. */
  threshold?: 'starter'
  /** The calculator that works this node's question through with real numbers. */
  tool?: ToolId
  /** US-specific account types and tax rules. */
  region?: 'us'
  /** One of several parallel choices offered by the node before it, rather
   *  than the next thing in sequence. The source chart's final pair — retire
   *  early / more immediate goals — are these: both can apply, and the chart
   *  says the order from there is up to you. Used by the flow layout to fork
   *  instead of continuing the spine. */
  option?: true
}

export interface RoadmapStage {
  id: StageId
  /** Step number from the source chart. Two stages can share one step — the
   *  original colours the emergency fund red in two places, and debt green in
   *  two — and that repetition is deliberate, not a mistake to normalise. */
  step: number
  title: string
  /** One line, shown on the collapsed row. This is the whole stage in a
   *  breath, for someone scanning rather than reading. */
  summary: string
  nodes: RoadmapNode[]
}

/** Legend for the step numbers, shown once above the roadmap. */
export const ROADMAP_STEPS: { step: number; label: string }[] = [
  { step: 0, label: 'Budget & essentials' },
  { step: 1, label: 'Emergency fund' },
  { step: 2, label: 'Employer match' },
  { step: 3, label: 'Pay down debt' },
  { step: 4, label: 'Retirement & near-term goals' },
  { step: 5, label: 'Save more for retirement' },
  { step: 6, label: 'Other goals & advanced' },
]

/**
 * ── Source map ──────────────────────────────────────────────────────────────
 * Every box in the original chart, in its original order, and where it landed
 * here. Check any edit against this list; it is the only record of what the
 * source actually said once the wording has been rewritten.
 *
 *  Create Budget                              -> create-budget
 *  Pay Rent/Mortgage                          -> housing
 *  Buy Food/Groceries                         -> groceries
 *  Pay Essential Items                        -> essential-items
 *  Pay Income Earning Expenses                -> income-earning-expenses
 *  Pay Health Care                            -> health-care
 *  Make Minimum Payments On All Debts         -> minimum-payments
 *  Build Small Emergency Fund            (S1) -> starter-ef
 *  Pay Any Non-Essential Bills in Full   (S1) -> nonessential-bills
 *  Employer match?                       (S2) -> match-question
 *    yes -> Contribute to the full match (S2) -> contribute-to-match
 *  High interest debt (>=10%)?           (S3) -> high-interest-question
 *    yes -> Avalanche / Snowball         (S3) -> choose-payoff-method
 *  (not a chart box)                     (S3) -> pay-down-card-in-igab
 *  (not a chart box)                     (S3) -> card-carries-again-note
 *      IGAB-native additions: how this app runs a card paydown (the
 *      set-aside/Uncovered mechanics, domain/cards.py) and what to do when
 *      the card must carry an emergency again. The chart prescribes the
 *      order of operations; these two describe the machinery for its S3.
 *  Increase EF to 3-6 months             (S1) -> full-ef
 *  Moderate interest debt (>4-5%)?       (S3) -> moderate-interest-question
 *    yes -> Avalanche / Snowball         (S3) -> pay-moderate-debt
 *  Roth vs Traditional IRA, max it       (S4) -> roth-vs-traditional
 *  Large required purchase coming?       (S4) -> large-purchase-question
 *    yes -> Save it in savings/checking  (S4) -> save-for-purchase
 *  Saving >=15% pre-tax for retirement?  (S5) -> fifteen-percent-question
 *    no  -> Employer plan to save more?  (S5) -> employer-plan-question
 *      yes -> Increase contributions     (S5) -> increase-contributions
 *      no  -> Solo 401k/SEP/SIMPLE, else
 *             a taxable account          (S5) -> self-employed-options
 *  Investable HSA?                       (S6) -> hsa-question
 *    yes -> Max yearly HSA               (S6) -> max-hsa
 *  Children's college?                   (S6) -> college-question
 *    yes -> 529 or similar               (S6) -> college-savings
 *  "At this point you have some options" (S6) -> your-call
 *  Retire early?                         (S6) -> retire-early
 *  More immediate goals?                 (S6) -> immediate-goals
 *  Note on entertainment expenses             -> the Wishlist's note on spending for fun
 *                                                (components/guide/wishlist/wishlistCopy.ts)
 *  Disclaimer                                 -> ROADMAP_DISCLAIMER
 *
 * ── Deliberate deviations ───────────────────────────────────────────────────
 * 1. `retire-early` and `immediate-goals` are decisions in the source, drawn
 *    with a "Yes" arrow and no "No" path. They are modelled as actions here
 *    because both can be true at once — the source itself says the order from
 *    that point is "completely up to you" — and a question with only one
 *    answer asks the reader for something it does not use.
 * 2. Stage grouping follows the *flow*, not the step numbers: the emergency
 *    fund appears at two points and debt at two points, exactly as the chart
 *    draws them. Each stage keeps its source step number for colour, which is
 *    why steps 1 and 3 each appear twice.
 */
export const ROADMAP: RoadmapStage[] = [
  // ── Step 0 ────────────────────────────────────────────────────────────────
  {
    id: 'foundation',
    step: 0,
    title: 'Cover your essentials',
    summary:
      'Know where your money goes, then cover the things that keep you housed, fed and earning.',
    nodes: [
      {
        id: 'create-budget',
        kind: 'action',
        title: 'Build a budget',
        body: 'Everything after this depends on knowing what comes in and what goes out. A budget is how the rest of the roadmap gets its numbers.',
        detail:
          'You do not need a perfect budget to start — you need an honest one. Most people find the first month is mostly discovery: you learn what you actually spend rather than what you assumed. That gap is the useful part.',
        glossary: ['zero-based-budgeting', 'to-be-assigned'],
        appLinks: [{ label: 'Open your budget', to: '/budget' }],
        signal: 'budget_exists',
      },
      {
        id: 'housing',
        kind: 'action',
        title: 'Pay rent or mortgage',
        body: 'Including renters or homeowners insurance where it is required.',
        detail:
          'Housing sits first because losing it makes every other problem on this roadmap harder to solve. If the payment is genuinely unaffordable, that is a bigger conversation than budgeting — but it is one worth having early rather than after arrears build up.',
        appLinks: [
          { label: 'Open your budget', to: '/budget' },
          { label: 'Essentials report', to: '/reports?tab=essentials' },
        ],
        signal: 'essential_expenses',
      },
      {
        id: 'groceries',
        kind: 'action',
        title: 'Buy food and groceries',
        body: 'Depending on how tight things are, you may want to cover utilities before this one.',
        detail:
          'The source chart flags this ordering explicitly, and the reasoning is practical: a missed utility bill can bring a reconnection fee and a mark on your credit, while a grocery budget can flex for a week without lasting damage. Neither should be squeezed for long.',
      },
      {
        id: 'essential-items',
        kind: 'action',
        title: 'Pay for essential items',
        body: 'Power, water, heat, toiletries — the running costs of a household.',
      },
      {
        id: 'income-earning-expenses',
        kind: 'action',
        title: 'Pay what it costs you to keep earning',
        body: 'Necessary transport, possibly internet and a phone, and anything else required to keep your income coming in.',
        detail:
          'This category is easy to under-fund because it looks discretionary from the outside. A phone plan or a commute is not a lifestyle expense when your job depends on it — cutting here can cost you the income the rest of the budget assumes.',
      },
      {
        id: 'health-care',
        kind: 'action',
        title: 'Pay for health care',
        body: 'Health insurance and your ongoing health care costs.',
        detail:
          'Health costs are the classic route from a stable budget into high-interest debt, which is exactly what the next several steps are about avoiding. Insurance is the cheaper end of that problem.',
      },
      {
        id: 'minimum-payments',
        kind: 'action',
        title: 'Make every minimum payment',
        body: 'Every loan and card, every month, without exception — even while you are still building savings.',
        detail:
          'Missing a minimum is uniquely expensive: a late fee, a penalty rate that can outlast the missed payment by months, and a mark on your credit report that lingers for years. This is the one line in the roadmap with no tradeoff to weigh.',
        glossary: ['apr', 'minimum-payment'],
        appLinks: [{ label: 'Your liabilities', to: '/liabilities' }],
      },
    ],
  },

  // ── Step 1 ────────────────────────────────────────────────────────────────
  {
    id: 'starter-emergency-fund',
    step: 1,
    title: 'Build a starter emergency fund',
    summary: 'A small buffer so the next surprise does not become debt.',
    nodes: [
      {
        id: 'starter-ef',
        tool: 'emergency-fund',
        kind: 'action',
        title: 'Save $1,000, or one month of expenses — whichever is larger',
        body: 'Keep it somewhere you can reach the same day: checking or plain savings. This is not an investment.',
        detail:
          'The point of this money is not growth, it is speed. A car repair or an urgent flight is exactly when you cannot afford to wait for a transfer to settle or to sell something at a bad moment. Chasing a slightly better rate here trades away the only feature that matters.\n\nThis is a starter buffer, not the finished one — the roadmap comes back to grow it to three to six months once expensive debt is out of the way.',
        glossary: ['emergency-fund', 'sinking-fund'],
        appLinks: [{ label: 'Open your budget', to: '/budget' }],
        signal: 'emergency_fund',
        threshold: 'starter',
      },
      {
        id: 'nonessential-bills',
        kind: 'action',
        title: 'Pay non-essential bills in full',
        body: 'Streaming, cable, subscriptions, the phone plan you upgraded. Pay what you have committed to, then look hard at whether you still want it.',
        detail:
          'Subscriptions are the most common place a budget quietly leaks, because each one is individually too small to argue with. Seen together as a monthly and annual total, the picture usually changes.',
        appLinks: [{ label: 'Subscriptions report', to: '/reports?tab=subscriptions' }],
      },
    ],
  },

  // ── Step 2 ────────────────────────────────────────────────────────────────
  {
    id: 'employer-match',
    step: 2,
    title: 'Take the full employer match',
    summary:
      'If your employer matches retirement contributions, this is the highest-return step on the roadmap.',
    nodes: [
      {
        id: 'match-question',
        kind: 'decision',
        title: 'Does your employer match retirement contributions?',
        body: 'A match means your employer adds money when you contribute — often matching some percentage of your pay.',
        detail:
          'Nothing in your budget can answer this; it lives in your employment paperwork or your payroll portal. Look for "employer match" or "company contribution" in your retirement plan documents.',
        branches: [
          {
            answer: 'Yes',
            label: 'Contribute enough to get all of it',
            toNode: 'contribute-to-match',
          },
          { answer: 'No', label: 'Move on to high-interest debt', toStage: 'high-interest-debt' },
          {
            answer: 'Not sure',
            label: 'Worth checking — it is the largest guaranteed return here',
            toNode: 'contribute-to-match',
          },
        ],
        glossary: ['employer-match'],
        signal: 'employer_match',
        region: 'us',
      },
      {
        id: 'contribute-to-match',
        kind: 'action',
        title: 'Contribute exactly enough to get the full match — and no more, for now',
        body: 'Matched money is an immediate return no other step on this roadmap can beat. Contributing beyond the match comes later, at step 5.',
        detail:
          'A 50% match on the first 6% of your pay is a 50% return on that money the moment it lands. Even high-interest credit card debt at 25% does not out-earn that, which is why this step sits above paying down debt.\n\nThe "no more, for now" matters: money above the match is ordinary retirement saving, and the roadmap has cheaper problems to solve first. Watch for a vesting schedule — matched money may not be fully yours until you have been there a set number of years.',
        glossary: ['employer-match', 'vesting'],
        region: 'us',
      },
    ],
  },

  // ── Step 3 (first pass) ───────────────────────────────────────────────────
  {
    id: 'high-interest-debt',
    step: 3,
    title: 'Clear high-interest debt',
    summary: 'Debt above roughly 10% grows faster than almost anything you could earn elsewhere.',
    nodes: [
      {
        id: 'high-interest-question',
        kind: 'decision',
        title: 'Do you have any debt with an interest rate of 10% or higher?',
        body: 'Credit cards, store cards, payday loans and some personal loans usually land here.',
        detail:
          'Ten percent is a rule of thumb, not a law. The reasoning: paying off a debt is a guaranteed, tax-free return equal to its rate, and a guaranteed 10% is hard to beat reliably anywhere else. Where a debt sits close to the line, either choice is defensible.',
        branches: [
          {
            answer: 'Yes',
            label: 'Pick a payoff method and commit to it',
            toNode: 'choose-payoff-method',
          },
          {
            answer: 'No',
            label: 'Grow the emergency fund instead',
            toStage: 'full-emergency-fund',
          },
        ],
        glossary: ['apr', 'high-interest-debt'],
        appLinks: [{ label: 'Your liabilities', to: '/liabilities' }],
        signal: 'high_interest_debt',
      },
      {
        id: 'choose-payoff-method',
        tool: 'payoff-plan',
        kind: 'action',
        title: 'Choose avalanche or snowball — then stick with it',
        body: 'Avalanche pays the highest rate first and costs the least. Snowball pays the smallest balance first and clears individual debts sooner. Keep paying every minimum either way.',
        detail:
          'Avalanche wins on arithmetic, usually by a modest amount. Snowball wins on momentum: closing a debt entirely is a visible finish line, and people who need to see progress are measurably more likely to keep going.\n\nThe source chart is deliberate about this — it says to weigh the financial and the psychological together rather than always taking the cheaper path. The best method is the one you will still be following in a year.',
        glossary: ['avalanche', 'snowball'],
        appLinks: [{ label: 'Your liabilities', to: '/liabilities' }],
      },
      {
        id: 'pay-down-card-in-igab',
        kind: 'action',
        title: 'Run a card paydown as an envelope in IGAB',
        body: 'Categorize everything the card syncs, then assign what you can to the card itself each month. Old debt sits calmly as Uncovered until you cover it.',
        detail:
          "Categorizing a card transaction never takes money you do not have. Money moves from the category into the card's Ready to pay only up to what the category could actually cover; any shortfall rides on the card as Uncovered, and To Be Assigned never hears about it. So categorize everything — the spending reports come free, and the debt cannot charge you twice.\n\nThe monthly loop: assign what you can afford to the card in the Credit cards section (To Be Assigned goes down, Uncovered goes down, one for one), then pay the card with a transfer from checking — the transfer drains Ready to pay and the balance together. A paydown target on the card row keeps the number honest month to month.\n\nEnter the card's APR and minimum payment on its liability page. That is what places the card in the payoff planner's avalanche and snowball schedules, and what lets the checkup call it high-interest debt instead of guessing.",
        glossary: ['carried-balance', 'uncovered', 'ready-to-pay', 'card-payment'],
        appLinks: [
          { label: 'Open your budget', to: '/budget' },
          { label: 'Your liabilities', to: '/liabilities' },
        ],
      },
      {
        id: 'card-carries-again-note',
        kind: 'note',
        title: 'When the card has to carry something again',
        body: "Put the expense in its real category and let it go red. At month end the shortfall becomes the card's Uncovered — the same paydown loop, just smaller.",
        detail:
          "The category does not stay negative waiting to heal. At the month boundary it resets to zero, and the part the envelope could not fund moves to the card's Uncovered column — visible, calm, charged to nothing until you cover it. Fund the category first when you can: Ready to pay picks that cash up automatically the moment the spending is covered.\n\nIf you notice after the month has turned, there are two ways back and the cheaper one is easy to miss. Assigning to the card covers the ride from any month — it costs you this month's money. But going back to the month that ended short and raising that envelope's assignment retires the ride outright, because the whole calculation is re-run from scratch every time you look at it. Funding the envelope in the FOLLOWING month does neither: it does not reach back. Only do the first if the earlier month has nothing to spare.\n\nNone of this is a failure state in the app. Uncovered exists to hold exactly this without alarms, so an emergency re-entering the card is a loop you already know how to run.",
        glossary: ['credit-overspending', 'uncovered'],
        appLinks: [{ label: 'Open your budget', to: '/budget' }],
      },
    ],
  },

  // ── Step 1 again ──────────────────────────────────────────────────────────
  {
    id: 'full-emergency-fund',
    step: 1,
    title: 'Grow the emergency fund to 3–6 months',
    summary: 'Enough to absorb a job loss, not just a broken appliance.',
    nodes: [
      {
        id: 'full-ef',
        tool: 'emergency-fund',
        kind: 'action',
        title: 'Build up to three to six months of living expenses',
        body: 'Measure against what you would actually spend in a lean month — essentials, not your current spending.',
        detail:
          'Where you land in the three-to-six range depends on how quickly you could replace your income. A two-earner household in a field that hires constantly can reasonably sit at the low end. A single earner, a specialised role, a long typical job search, or self-employment all argue for the high end.\n\nKeep it accessible — a savings or checking account, same as the starter fund. This is still not money to invest.',
        glossary: ['emergency-fund'],
        appLinks: [
          { label: 'Open your budget', to: '/budget' },
          { label: 'Essentials report', to: '/reports?tab=essentials' },
        ],
        signal: 'emergency_fund',
      },
    ],
  },

  // ── Step 3 again ──────────────────────────────────────────────────────────
  {
    id: 'moderate-interest-debt',
    step: 3,
    title: 'Clear moderate-interest debt',
    summary: 'Remaining debt above roughly 4–5%, setting your mortgage aside.',
    nodes: [
      {
        id: 'moderate-interest-question',
        tool: 'pay-vs-save',
        kind: 'decision',
        title: 'Do you have debt above about 4–5%, not counting your mortgage?',
        body: 'Car loans, student loans and personal loans often sit in this range.',
        detail:
          'A mortgage is set aside here for two reasons: the rate is usually low, and the balance is large enough that paying it down early competes directly with retirement saving over decades rather than months. It is a genuine judgement call, and the roadmap leaves it as one.\n\nThis band is where "pay it off or invest instead" stops having an obvious answer. Below roughly 4%, many people reasonably choose to invest instead. The closer to 10%, the stronger the case for paying it off.',
        branches: [
          {
            answer: 'Yes',
            label: 'Use the same method you chose before',
            toNode: 'pay-moderate-debt',
          },
          {
            answer: 'No',
            label: 'Move on to retirement saving',
            toStage: 'retirement-and-near-term',
          },
        ],
        glossary: ['apr', 'avalanche', 'snowball'],
        appLinks: [{ label: 'Your liabilities', to: '/liabilities' }],
        signal: 'moderate_interest_debt',
      },
      {
        id: 'pay-moderate-debt',
        tool: 'payoff-plan',
        kind: 'action',
        title: 'Apply the same payoff method here',
        body: 'Avalanche or snowball, whichever you picked. There is no reason to switch methods midway.',
        detail:
          'One thing worth checking before you accelerate: whether the loan carries a prepayment penalty, and whether extra payments are applied to principal by default. Some servicers apply an overpayment to next month’s bill instead, which feels like progress but is not.',
        glossary: ['principal', 'avalanche', 'snowball'],
        appLinks: [{ label: 'Your liabilities', to: '/liabilities' }],
      },
    ],
  },

  // ── Step 4 ────────────────────────────────────────────────────────────────
  {
    id: 'retirement-and-near-term',
    step: 4,
    title: 'Start retirement saving and fund what is coming',
    summary:
      'Open a retirement account beyond the match, and set aside money for large near-term needs.',
    nodes: [
      {
        id: 'roth-vs-traditional',
        kind: 'action',
        title: 'Weigh a Roth against a Traditional IRA, then fund it',
        body: 'Roth contributions are taxed now and withdrawals are not. Traditional is the reverse. Contribute up to the yearly limit.',
        detail:
          'The usual shorthand: Roth tends to suit people who expect to be in a higher tax bracket later — often earlier in a career — and Traditional tends to suit people whose bracket is high now and likely lower in retirement.\n\nThat is a generalisation with real exceptions, and both are far better than not contributing. Contribution limits and income eligibility change most years, so check the current figures rather than trusting a number you remember.',
        glossary: ['ira', 'roth', 'traditional'],
        region: 'us',
      },
      {
        id: 'large-purchase-question',
        tool: 'loan-compare',
        kind: 'decision',
        title: 'Is a large, genuinely required expense coming?',
        body: 'A car you need to get to work, tuition, a professional certification — not things you would simply like to have.',
        detail:
          'The word doing the work is "required". A replacement car when your current one is failing belongs here. An upgrade because you fancy a newer model belongs in step 6, alongside your other goals.',
        branches: [
          { answer: 'Yes', label: 'Save for it in cash, separately', toNode: 'save-for-purchase' },
          { answer: 'No', label: 'Move on to the 15% target', toStage: 'retirement-fifteen' },
        ],
        glossary: ['sinking-fund'],
      },
      {
        id: 'save-for-purchase',
        kind: 'action',
        title: 'Save for it in checking or savings',
        body: 'Money you will need within a few years does not belong in the market. Give it its own category so it is never accidentally spent.',
        detail:
          'This is what a sinking fund is for: a known expense, a known rough date, funded a little each month instead of arriving as a crisis. In IGAB, that is a category with a target — the budget then tells you each month whether you are on pace.',
        glossary: ['sinking-fund', 'target'],
        appLinks: [{ label: 'Open your budget', to: '/budget' }],
      },
    ],
  },

  // ── Step 5 ────────────────────────────────────────────────────────────────
  {
    id: 'retirement-fifteen',
    step: 5,
    title: 'Work up to saving 15% for retirement',
    summary: 'Counting everything you put toward retirement, including the employer match.',
    nodes: [
      {
        id: 'fifteen-percent-question',
        kind: 'decision',
        title: 'Are you saving at least 15% of your pre-tax income for retirement?',
        body: 'Count every retirement contribution together, your employer match included.',
        detail:
          'Fifteen percent is a common target for someone who starts in their twenties and works a full career. Starting later means the number needs to be higher — the arithmetic of compounding is unforgiving about lost years, and no amount of later saving fully replaces them.\n\nIf 15% is out of reach today, that is information rather than failure. Raise the rate when your income does, and treat each raise as the moment to move it up a point.',
        branches: [
          { answer: 'Yes', label: 'Move on to your other goals', toStage: 'other-goals' },
          {
            answer: 'No',
            label: 'Look at where you could contribute more',
            toNode: 'employer-plan-question',
          },
        ],
        glossary: ['savings-rate', 'compounding'],
        appLinks: [{ label: 'Savings rate report', to: '/reports?tab=savings-rate' }],
        signal: 'retirement_contributions',
      },
      {
        id: 'employer-plan-question',
        kind: 'decision',
        title: 'Does your employer offer a plan you could put more into?',
        body: 'A 401(k), 403(b) or similar workplace retirement plan.',
        branches: [
          {
            answer: 'Yes',
            label: 'Raise your contribution toward 15%',
            toNode: 'increase-contributions',
          },
          {
            answer: 'No',
            label: 'Look at the options outside work',
            toNode: 'self-employed-options',
          },
        ],
        glossary: ['401k'],
        region: 'us',
      },
      {
        id: 'increase-contributions',
        kind: 'action',
        title: 'Raise your contribution rate until you reach 15%',
        body: 'You do not have to get there in one move. A percentage point at a time, especially alongside a raise, is a normal way to close the gap.',
        detail:
          'Payroll contributions have a quiet advantage: the money never reaches your checking account, so there is no monthly decision to make and nothing to resist. Increases timed to a raise are barely noticeable in take-home pay.',
        region: 'us',
      },
      {
        id: 'self-employed-options',
        kind: 'action',
        title: 'Use the accounts available outside a workplace plan',
        body: 'If you are self-employed, a Solo 401(k), SEP-IRA or SIMPLE IRA can carry the rest. If not, an ordinary taxable brokerage account will do it.',
        detail:
          'A taxable account has no contribution cap and no withdrawal rules, which is exactly why it is listed last: you give up the tax treatment that makes the other accounts worth filling first. It is still a perfectly good place for money once they are full.',
        glossary: ['taxable-account'],
        region: 'us',
      },
    ],
  },

  // ── Step 6 ────────────────────────────────────────────────────────────────
  {
    id: 'other-goals',
    step: 6,
    title: 'Other goals and advanced methods',
    summary: 'From here the order is genuinely yours. These are the common next moves.',
    nodes: [
      {
        id: 'hsa-question',
        kind: 'decision',
        title: 'Do you have a high-deductible health plan with an investable HSA?',
        body: 'Not every HSA can be invested — some are cash-only accounts held at your employer’s chosen provider.',
        detail:
          'An HSA is unusual: contributions, growth and qualified medical withdrawals are all untaxed. That combination is why it appears here rather than being treated as an ordinary savings account.',
        branches: [
          { answer: 'Yes', label: 'Consider filling it to the yearly limit', toNode: 'max-hsa' },
          { answer: 'No', label: 'Move on', toNode: 'college-question' },
        ],
        glossary: ['hsa'],
        signal: 'hsa',
        region: 'us',
      },
      {
        id: 'max-hsa',
        kind: 'action',
        title: 'Fill the HSA to the yearly limit',
        body: 'Contribute up to the annual maximum and invest the balance if your provider allows it.',
        detail:
          'Paying current medical costs out of pocket, keeping the receipts, and leaving the HSA invested is a common approach — the money compounds untouched, and qualified expenses can be reimbursed later. It only works if paying out of pocket does not strain the rest of your budget.',
        glossary: ['hsa'],
        region: 'us',
      },
      {
        id: 'college-question',
        kind: 'decision',
        title: 'Are you helping pay for a child’s education?',
        body: 'If so, dedicated accounts exist for it — a 529 plan is the most common in the US.',
        detail:
          'Worth stating plainly: this comes after your own retirement is on track. Your child can borrow for education. Nobody lends for retirement. Funding college ahead of your own retirement is one of the most common and most costly reorderings of this roadmap.',
        branches: [
          { answer: 'Yes', label: 'Look at a 529 or similar', toNode: 'college-savings' },
          { answer: 'No', label: 'Move on', toNode: 'your-call' },
        ],
        glossary: ['529'],
        signal: 'college_savings',
        region: 'us',
      },
      {
        id: 'college-savings',
        kind: 'action',
        title: 'Fund a 529 or a similar education account',
        body: 'Contribute what fits alongside your own retirement saving, not instead of it.',
        glossary: ['529'],
        region: 'us',
      },
      {
        id: 'your-call',
        kind: 'note',
        title: 'From here, it is your call',
        body: 'The remaining choices depend on what you actually want your money to do. Both paths below are ordinary and neither is more correct.',
      },
      {
        id: 'retire-early',
        kind: 'action',
        option: true,
        title: 'If you want to retire early',
        body: 'Fill your workplace plan to its limit, look into whether a mega backdoor Roth is available to you, then use a taxable account.',
        detail:
          'Retiring before the usual retirement age needs money you can reach before then, which is why a taxable account earns its place here despite the tax treatment. Access, not just total balance, becomes the constraint.',
        glossary: ['401k', 'taxable-account'],
        region: 'us',
      },
      {
        id: 'immediate-goals',
        kind: 'action',
        option: true,
        title: 'If you have nearer-term goals',
        body: 'For anything within three to five years, keep it in savings. For longer horizons, a conservative mix of stocks and bonds is the usual approach.',
        detail:
          'Common examples: a house deposit, a vehicle, paying down a mortgage, a significant trip. The dividing line is time, not the size of the goal — money you will need soon cannot afford to be down 20% on the month you need it.',
        glossary: ['sinking-fund'],
        appLinks: [{ label: 'Open your budget', to: '/budget' }],
      },
    ],
  },
]

/** A standing note from the source chart, shown once beneath the roadmap. */
export const ROADMAP_ATTRIBUTION = {
  text: 'Adapted from the r/personalfinance Personal Income Spending Flowchart.',
  href: 'https://www.reddit.com/r/personalfinance/wiki/commontopics/',
}

export const ROADMAP_DISCLAIMER =
  'This is general education, not financial advice. Circumstances differ, and the roadmap is a common starting order rather than a rule.'

/** All nodes, flattened — for lookup by id when a branch points somewhere. */
export function findNode(nodeId: string): { stage: RoadmapStage; node: RoadmapNode } | null {
  for (const stage of ROADMAP) {
    const node = stage.nodes.find((n) => n.id === nodeId)
    if (node) return { stage, node }
  }
  return null
}

export function findStage(stageId: StageId): RoadmapStage | null {
  return ROADMAP.find((s) => s.id === stageId) ?? null
}
