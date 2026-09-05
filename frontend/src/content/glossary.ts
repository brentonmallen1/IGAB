/**
 * Plain-language definitions for the finance vocabulary IGAB uses.
 *
 * Two audiences share this file: someone reading the roadmap who hits a term
 * they do not know, and someone anywhere in the app who presses a help icon.
 * Both want the same thing — a short answer, immediately, without leaving what
 * they were doing.
 *
 * ── Editing rules ───────────────────────────────────────────────────────────
 * 1. `short` is one line and must stand alone. It is what shows in a tooltip,
 *    and for most readers it is the only part that gets read.
 * 2. `body` is two to four sentences. Not an article.
 * 3. `inIgab` is the part no general glossary can offer — where this concept
 *    lives in this app. Include it whenever there is a real answer; omit it
 *    rather than writing something vague.
 * 4. `related` builds the browse path. Link generously; the terms people need
 *    next are usually the ones sitting beside the one they looked up.
 *
 * Some copy here deliberately mirrors wording already written for users in
 * `backend/src/igab/domain/account_types.py` and the activity-class reasons in
 * `backend/src/igab/domain/activity_class.py`. Those are the canonical
 * explanations of how IGAB itself classifies money — if they change, change
 * these to match rather than letting the two drift.
 */

/** Every glossary id, as a literal tuple.
 *
 * Declared separately from GLOSSARY so `GlossaryId` is a union of the actual
 * ids rather than `string`. That is what makes a term reference from the
 * roadmap a compile error when it points at nothing. `content.test.ts` checks
 * the other direction — an id here with no entry below. */
export const GLOSSARY_IDS = [
  'zero-based-budgeting',
  'archived-envelope',
  'to-be-assigned',
  'target',
  'emergency-fund',
  'sinking-fund',
  'apr',
  'apy',
  'principal',
  'minimum-payment',
  'amortization',
  'high-interest-debt',
  'avalanche',
  'snowball',
  'employer-match',
  'vesting',
  '401k',
  'ira',
  'roth',
  'traditional',
  'hsa',
  '529',
  'taxable-account',
  'savings-rate',
  'compounding',
  'pending',
  'uncleared',
  'cleared',
  'reconciled',
  'essential-expenses',
  'cooling-off',
  'ready-to-pay',
  'uncovered',
  'credit-overspending',
  'carried-balance',
  'card-payment',
  'refused-card-inflow',
] as const

export type GlossaryId = (typeof GLOSSARY_IDS)[number]

export interface GlossaryEntry {
  id: GlossaryId
  term: string
  /** Extra search terms — abbreviations, plurals, the phrasing people type. */
  aliases?: string[]
  /** One line. Stands alone. */
  short: string
  /** Two to four sentences. */
  body: string
  /** Where this lives in IGAB, when there is a concrete answer. */
  inIgab?: string
  related?: GlossaryId[]
  region?: 'us'
}

export const GLOSSARY: GlossaryEntry[] = [
  {
    id: 'archived-envelope',
    term: 'Archived envelope',
    aliases: ['archive', 'archived category', 'hidden category', 'hide a category'],
    short: 'A category you have finished with, kept for its history but out of the budget.',
    body: 'Archiving takes an envelope off the budget without losing anything: its past spending still counts in every report, and every transaction stays filed where it was. What it stops is new use — nothing can be budgeted into it or filed to it. Deleting is the other choice, and it is the one that gives up the grouping of that spending.',
    inIgab:
      'See archived, at the top of the Budget page, lists them with their history and anything still in them. An envelope has to be emptied before it can be archived, because an archived one is not drawn on the budget and money left in it would be out of reach. Hiding a category in a saved view is a different thing entirely — that only changes what that one view shows.',
    related: ['zero-based-budgeting', 'to-be-assigned'],
  },
  {
    id: 'zero-based-budgeting',
    term: 'Zero-based budgeting',
    aliases: ['zero based', 'envelope budgeting', 'envelopes'],
    short: 'Give every incoming pound or dollar a job until none is unassigned.',
    body: 'Rather than tracking spending against a forecast, you assign all the money you actually have to specific categories. When nothing is left unassigned, the budget balances — not because you spent nothing, but because every amount has a purpose.',
    inIgab:
      'The Budget page is this. Money arrives in To Be Assigned, and you distribute it into categories until To Be Assigned reaches zero.',
    related: ['to-be-assigned', 'target', 'sinking-fund'],
  },
  {
    id: 'to-be-assigned',
    term: 'To Be Assigned',
    aliases: ['tba', 'ready to assign', 'unassigned'],
    short: 'Money you have received but have not yet given a job.',
    body: 'Income lands here first. From there you move it into categories. A positive balance means there is money still waiting on a decision; a negative one means you have assigned more than you actually have.',
    inIgab:
      'Shown at the top of the Budget page, with a drawer for assigning it and for covering overspent categories.',
    related: ['zero-based-budgeting', 'target'],
  },
  {
    id: 'target',
    term: 'Target',
    aliases: ['goal', 'category target'],
    short: 'The amount a category needs, and by when.',
    body: 'A target turns an intention into something the budget can check. It can mean a monthly amount, a balance to reach by a date, or a sum needed for spending in the month.',
    inIgab:
      'Set on any category. The budget then shows whether that category is funded, underfunded or overfunded for the month.',
    related: ['sinking-fund', 'zero-based-budgeting'],
  },
  {
    id: 'emergency-fund',
    term: 'Emergency fund',
    aliases: ['rainy day fund', 'buffer', 'ef'],
    short: 'Money set aside for genuine surprises, kept somewhere you can reach immediately.',
    body: 'Its job is to absorb the unexpected — a repair, a medical bill, a lost job — so that a bad month does not become debt. The roadmap builds it in two passes: a small starter buffer early, then three to six months of expenses once expensive debt is cleared. Speed of access matters more than the interest rate it earns.',
    inIgab: 'Usually a category tagged Savings, an account of its own, or both.',
    related: ['sinking-fund', 'savings-rate'],
  },
  {
    id: 'essential-expenses',
    term: 'Essential expenses',
    aliases: ['essentials', 'lean month', 'bare-bones budget'],
    short: 'What a month costs if you cut everything you could do without.',
    body: 'Housing, groceries, utilities, transport to work, insurance, minimum debt payments, medical needs — the spending that continues whatever else stops. It is the figure an emergency fund is measured against: three months of essentials, not three months of everything.',
    inIgab:
      'Tag the categories and payees you could not do without as Essential. The Essentials report, the Overview card and the Guide’s emergency-fund target all read that one figure, and the checkup states your emergency fund in months of it.',
    related: ['emergency-fund', 'target'],
  },
  {
    id: 'cooling-off',
    term: 'Cooling-off period',
    aliases: ['waiting period', '30-day rule'],
    short: 'A deliberate wait between wanting something and buying it.',
    body: 'Most impulse purchases do not survive a month on a list. A cooling-off period is that month, made explicit: the wish sits, the envelope fills or does not, and at the end you decide with the urgency gone. The friction is the feature — an impulse that survives it was never an impulse.',
    inIgab:
      'Every wish on the wishlist gets one (30 days by default, adjustable per wish and per budget). Until it passes, the wish reads "cooling off until <date>" and the Done button keeps quiet.',
    related: ['sinking-fund', 'target'],
  },
  {
    id: 'sinking-fund',
    term: 'Sinking fund',
    short: 'An envelope you fill a little each month for a large, predictable expense.',
    body: 'Car insurance, property tax, holidays and annual renewals are all knowable in advance. Saving a twelfth each month turns a yearly shock into an ordinary monthly line. Unlike an emergency fund, a sinking fund is for something you already know is coming.',
    inIgab: 'A category with a monthly target that accumulates rather than resetting.',
    related: ['emergency-fund', 'target'],
  },
  {
    id: 'apr',
    term: 'APR',
    aliases: ['annual percentage rate', 'interest rate'],
    short: 'The yearly cost of borrowing money, as a percentage of what you owe.',
    body: 'A higher APR means the debt grows faster when it is not paid off. It is the single most useful number for deciding which debt to attack first. APR is distinct from APY, which describes what savings earn.',
    inIgab: 'Stored on each liability record, and used for payoff projections and amortization.',
    related: ['apy', 'principal', 'high-interest-debt', 'minimum-payment'],
  },
  {
    id: 'apy',
    term: 'APY',
    aliases: ['annual percentage yield'],
    short: 'What savings earn in a year, including the effect of compounding.',
    body: 'The counterpart to APR. Comparing the APY on savings against the APR on a debt is the arithmetic behind "should I pay this off or save it?" — if the debt costs more than the savings earn, paying it down wins.',
    related: ['apr', 'compounding'],
  },
  {
    id: 'principal',
    term: 'Principal',
    short: 'The amount you actually owe, separate from the interest charged on it.',
    body: 'A loan payment is usually split between interest and principal. Only the principal portion reduces the debt; the interest portion is the cost of having borrowed. Early in a long loan, most of each payment goes to interest.',
    inIgab:
      'Money moved to a tracked debt account counts as paying down debt rather than as spending, so it stays out of your spending reports.',
    related: ['apr', 'minimum-payment', 'amortization'],
  },
  {
    id: 'minimum-payment',
    term: 'Minimum payment',
    short: 'The smallest amount a lender will accept in a given month without penalising you.',
    body: 'Paying only the minimum on a high-rate debt can mean the balance barely moves, because most of the payment covers interest. On some cards a minimum payment is close enough to the monthly interest that the debt never clears.',
    inIgab:
      "Held on a liability as a RULE rather than a snapshot: either a fixed amount, or a percentage of the balance with a dollar floor (\u201c2% or $35, whichever is greater\u201d), optionally plus the month's interest. That matters because a percentage falls as the balance does \u2014 a projection built from the figure on one statement pays the debt off sooner and cheaper than it really goes. The payoff projections use the rule, and flag a minimum that would never clear the debt.",
    related: ['apr', 'principal', 'amortization'],
  },
  {
    id: 'amortization',
    term: 'Amortization',
    aliases: ['amortisation', 'payoff schedule'],
    short: 'The month-by-month schedule of how a loan gets paid off.',
    body: 'Each row splits a payment into interest and principal and shows the balance falling. It is how you can tell what a loan will actually cost over its life, and how much an extra payment would change that.',
    inIgab: 'Available on any liability with a rate and a minimum payment.',
    related: ['principal', 'minimum-payment', 'apr'],
  },
  {
    id: 'high-interest-debt',
    term: 'High-interest debt',
    short: 'Debt above roughly 10% APR — usually credit cards, store cards and payday loans.',
    body: 'The threshold is a rule of thumb. The reasoning behind it: clearing a debt is a guaranteed return equal to its interest rate, and a guaranteed 10% is very hard to beat reliably by investing instead.',
    related: ['apr', 'avalanche', 'snowball'],
  },
  {
    id: 'avalanche',
    term: 'Avalanche method',
    aliases: ['debt avalanche', 'highest interest first'],
    short:
      'Pay minimums on everything, then put every spare pound or dollar at the highest interest rate.',
    body: 'Mathematically this costs the least in total interest and usually clears all debt soonest. Its weakness is motivational: if your highest-rate debt is also your largest, it can be a long time before anything visibly disappears.',
    related: ['snowball', 'high-interest-debt', 'apr'],
  },
  {
    id: 'snowball',
    term: 'Snowball method',
    aliases: ['debt snowball', 'smallest balance first'],
    short:
      'Pay minimums on everything, then put every spare pound or dollar at the smallest balance.',
    body: 'This costs slightly more in interest than avalanche, but clears individual debts sooner. Each debt that closes frees up its payment and gives visible proof of progress, which measurably helps people keep going. The method you actually stick with beats the one that is optimal on paper.',
    related: ['avalanche', 'high-interest-debt'],
  },
  {
    id: 'employer-match',
    term: 'Employer match',
    aliases: ['company match', '401k match'],
    short: 'Money your employer adds to your retirement account when you contribute.',
    body: 'A typical arrangement matches some percentage of your pay — for example, 50% of the first 6% you contribute. Because the match lands immediately, it is effectively an instant return that no other step on the roadmap matches. Contributing less than the full match leaves that money unclaimed.',
    related: ['vesting', '401k'],
    region: 'us',
  },
  {
    id: 'vesting',
    term: 'Vesting',
    short: 'How long you must stay with an employer before matched money is fully yours.',
    body: 'Your own contributions are always yours. Employer contributions may vest gradually over several years, or all at once on a set date. Leaving before you are vested can mean forfeiting some of the match.',
    related: ['employer-match', '401k'],
    region: 'us',
  },
  {
    id: '401k',
    term: '401(k) / 403(b)',
    aliases: ['401k', '403b', 'workplace retirement plan'],
    short: 'A retirement account offered through an employer, funded straight from payroll.',
    body: 'Contributions come out before the money reaches your bank account, which removes the monthly decision entirely. Employer matching, where offered, is attached to these plans. Contribution limits are set annually and change most years.',
    inIgab:
      'Usually tracked as an off-budget Investment account: it counts toward net worth, but is not spendable envelope money.',
    related: ['employer-match', 'ira', 'taxable-account'],
    region: 'us',
  },
  {
    id: 'ira',
    term: 'IRA',
    aliases: ['individual retirement account'],
    short: 'A retirement account you open yourself, independent of any employer.',
    body: 'Comes in Roth and Traditional forms, which differ in when the money is taxed. Contribution limits are lower than a workplace plan and change most years. Anyone with earned income can generally use one, subject to income rules.',
    inIgab: 'Usually an off-budget Investment account.',
    related: ['roth', 'traditional', '401k'],
    region: 'us',
  },
  {
    id: 'roth',
    term: 'Roth',
    short: 'You pay tax on the money now; qualified withdrawals later are untaxed.',
    body: 'Broadly suits people who expect to be in a higher tax bracket later than they are today, which often means earlier in a career. Because the tax is already settled, the balance you see is closer to what you can actually spend.',
    related: ['traditional', 'ira'],
    region: 'us',
  },
  {
    id: 'traditional',
    term: 'Traditional',
    short: 'You get the tax break now; withdrawals in retirement are taxed.',
    body: 'The mirror image of a Roth. Broadly suits people whose tax bracket is high now and likely lower in retirement. The headline balance overstates what you can spend, because tax is still owed on it.',
    related: ['roth', 'ira'],
    region: 'us',
  },
  {
    id: 'hsa',
    term: 'HSA',
    aliases: ['health savings account'],
    short: 'A medical savings account attached to a high-deductible health plan.',
    body: 'Unusual in that contributions, growth and qualified medical withdrawals are all untaxed. Not every HSA can be invested — some providers hold the balance as cash only. Unspent money carries over year to year rather than expiring.',
    inIgab: 'Often tracked as two paired accounts — a cash side and an invested side.',
    related: ['401k', 'ira'],
    region: 'us',
  },
  {
    id: '529',
    term: '529 plan',
    aliases: ['college savings plan', 'education savings'],
    short: 'A tax-advantaged account for education costs.',
    body: 'Growth is untaxed when the money goes toward qualifying education expenses. The roadmap places it after your own retirement is on track, on the reasoning that education can be borrowed for and retirement cannot.',
    related: ['ira', 'taxable-account'],
    region: 'us',
  },
  {
    id: 'taxable-account',
    term: 'Taxable brokerage account',
    aliases: ['brokerage', 'taxable'],
    short: 'An ordinary investment account with no contribution limits and no withdrawal rules.',
    body: 'You give up the tax treatment that makes retirement accounts worth filling first, which is why it appears last on the roadmap. In exchange you get full access at any age, which matters for goals that arrive before retirement.',
    inIgab: 'An off-budget Investment account.',
    related: ['401k', 'ira'],
  },
  {
    id: 'savings-rate',
    term: 'Savings rate',
    short: 'The share of your income that you save rather than spend.',
    body: 'The single most useful summary of whether a budget is working over time. The roadmap targets 15% of pre-tax income for retirement specifically, which is a narrower measure than your overall savings rate.',
    inIgab:
      'Computed in the Savings Rate report, on-budget only, so investment growth is never counted as money you saved.',
    related: ['compounding', 'emergency-fund'],
  },
  {
    id: 'compounding',
    term: 'Compounding',
    short: 'Growth earning further growth, so the balance accelerates over time.',
    body: 'The reason starting early matters more than contributing heavily later — early money has the most time to compound. It works identically against you on debt, which is why high-rate balances grow so quickly when left unpaid.',
    related: ['apy', 'savings-rate', 'apr'],
  },
  {
    id: 'pending',
    term: 'Pending',
    aliases: ['authorization hold', 'auth hold', 'pending transaction'],
    short: 'The bank reports a hold that has not posted yet. Provisional, and not counted.',
    body: 'When you pay by card the bank first records an authorization for an estimated amount; the final charge posts days later and can differ (a tip, a fuel hold). Until it posts, nothing has actually moved.',
    inIgab:
      'Rows the bank sync brings in as pending show a clock and are left out of every balance. When the same record posts, the row clears in place; if the posted amount differs from something you entered yourself, it is offered for review rather than changed silently.',
    related: ['uncleared', 'cleared', 'reconciled'],
  },
  {
    id: 'uncleared',
    term: 'Uncleared',
    aliases: ['unconfirmed'],
    short:
      'You entered it and the money has moved in your ledger; the bank has not confirmed it yet.',
    body: 'An uncleared transaction is a real one you recorded before the bank did. It counts toward your balance because you know you spent it; it simply has not been matched to a bank record yet.',
    inIgab:
      'The empty circle in the register. Clicking it marks the row cleared by hand; a bank sync that finds the matching record clears it for you.',
    related: ['pending', 'cleared', 'reconciled'],
  },
  {
    id: 'cleared',
    term: 'Cleared',
    short: 'The bank agrees this transaction happened, at this amount.',
    body: 'Cleared means confirmed: either the bank record matched, or you ticked it yourself while checking against a statement. Cleared rows are what a reconciliation compares to the bank balance.',
    inIgab:
      'The filled check in the register. The cleared balance shown on an account is the sum of these rows.',
    related: ['uncleared', 'reconciled', 'pending'],
  },
  {
    id: 'reconciled',
    term: 'Reconciled',
    aliases: ['locked'],
    short:
      'Checked against a bank statement and locked. The money cannot change; the bookkeeping can.',
    body: 'Reconciling an account is agreeing that its cleared balance equals what the bank says on a date. Every cleared transaction up to that date is then locked, so the agreement stays true.',
    inIgab:
      'The lock in the register. A reconciled row keeps its amount, date and account fixed, but you can still edit its category, payee, memo and split lines through Edit… in the row menu; Unlock returns it to cleared.',
    related: ['cleared', 'uncleared', 'pending'],
  },
  {
    id: 'ready-to-pay',
    term: 'Ready to pay',
    aliases: ['set aside', 'set-aside', 'card payment reserve'],
    short: "Cash reserved to pay a credit card — the card's own envelope.",
    body: "When you spend on a card from a funded category, the budgeted cash does not vanish — it moves into a reserve for that card, so the payment is already covered before the bill exists. Assigning money to the card adds to the reserve; payments drain it. Spending a category could not cover adds nothing here — it becomes the card's uncovered debt instead. It is the card's envelope, not a measurement of the card, so it can sit above what the card owes or below zero.",
    inIgab:
      'The "Ready to pay" column of the Credit cards section on the budget page. Below zero usually means you paid more than an envelope set aside — assign that much to the card to settle up; it is only a credit balance when the card owes nothing. Above the balance means assignments no debt needed, and releasing them is safe.',
    related: ['uncovered', 'credit-overspending', 'card-payment', 'to-be-assigned'],
  },
  {
    id: 'uncovered',
    term: 'Uncovered',
    aliases: ['uncovered debt'],
    short: 'What a card is owed beyond the cash reserved to pay it.',
    body: 'Uncovered debt is card balance with no reserve behind it: overspending that rode onto the card, an old carried balance, or a purchase someone still owes you for. It is information, not an alarm — nothing leaves your budget until you choose to assign money to the card, and assigning lowers Uncovered dollar for dollar.',
    inIgab:
      "The last column of the Credit cards section; the collapsed header still shows the total. The number is a door — it opens the card's transactions.",
    related: ['ready-to-pay', 'carried-balance', 'credit-overspending', 'refused-card-inflow'],
  },
  {
    id: 'credit-overspending',
    term: 'Credit overspending',
    short: 'Overspending a category on a credit card — it becomes card debt, not a budget charge.',
    body: 'When a category ends a month negative and the spending was on a card, the shortfall rides onto the card as uncovered debt instead of coming out of To Be Assigned. The category resets to zero at the month boundary; the debt stays visible on the card until money is assigned to it. Cash overspending is different — real money left, so it settles from To Be Assigned.',
    inIgab:
      "A red category funded by card swipes turns into the card's Uncovered at month end. Cover Overspent handles only the cash kind, on purpose.",
    related: ['uncovered', 'ready-to-pay', 'to-be-assigned'],
  },
  {
    id: 'carried-balance',
    term: 'Carried balance',
    aliases: ['revolving balance', 'carrying a balance'],
    short: 'Card debt rolled from month to month instead of paid in full.',
    body: "A balance you carry accrues interest at the card's APR, which is what makes card debt expensive. In envelope terms it is spending that was never backed by budgeted cash, so it shows beside the card as uncovered debt rather than inside any category. Paying it down is a budget line like any other: assign what you can afford to the card each month.",
    inIgab:
      "Shows as the card's Uncovered — including the balance a newly linked card arrives with. Set the card's APR and minimum payment on its liability page and the payoff planner includes it. If the card's minimum is a percentage of the balance, enter it that way rather than as this month's figure; see Minimum payment.",
    related: ['uncovered', 'high-interest-debt', 'minimum-payment', 'apr'],
  },
  {
    id: 'card-payment',
    term: 'Card payment',
    short:
      "A transfer from a cash account to a card — the only move that spends the card's reserve.",
    body: 'Record a payment as a transfer from checking or savings to the card. That drains Ready to pay and lowers the balance together, and To Be Assigned never moves. A plain deposit typed onto the card lowers the balance without touching the reserve — right when someone else paid the card company, wrong for your own payment.',
    inIgab:
      "Enter it as a transfer between the two accounts. A synced payment is paired for you when both accounts are connected and the two sides are unmistakable — same amount, a few days apart, nothing else it could be. When they are not, the Accounts page lists the pair so you can confirm it; until then the payment is not counted against the card's reserve.",
    related: ['ready-to-pay', 'uncovered', 'cleared', 'refused-card-inflow'],
  },
  {
    id: 'refused-card-inflow',
    term: 'Refused card inflow',
    aliases: ['card inflow that paid down debt'],
    short: 'Money that arrived on a card and paid down debt instead of returning to an envelope.',
    body: 'An envelope only gets a card refund back if it put that money on the card in the first place. A refund of something bought before you started budgeting — or of spending that overspent and rode onto the card — reduces what you owe without releasing any reserved cash, so it pays down Uncovered rather than landing in an envelope you could spend from. Without this the same dollars would count twice: once as debt paid down, once as spendable money, with To Be Assigned quietly making up the difference.',
    inIgab:
      'Almost always zero. When it is not, the envelope shows the amount under its Available, so the figure is never lower than you can account for. A large one usually means a card payment was filed to a category instead of being recorded as a transfer.',
    related: ['uncovered', 'ready-to-pay', 'card-payment'],
  },
]

const BY_ID = new Map(GLOSSARY.map((e) => [e.id, e]))

export function glossaryEntry(id: string): GlossaryEntry | undefined {
  return BY_ID.get(id as GlossaryId)
}

/** Substring match over term, aliases and the one-liner. */
export function searchGlossary(query: string): GlossaryEntry[] {
  const q = query.trim().toLowerCase()
  if (!q) return GLOSSARY
  return GLOSSARY.filter((e) =>
    [e.term, e.short, ...(e.aliases ?? [])].some((s) => s.toLowerCase().includes(q))
  )
}
