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
    id: 'zero-based-budgeting',
    term: 'Zero-based budgeting',
    aliases: ['zero based', 'envelope budgeting', 'envelopes'],
    short: 'Give every incoming pound or dollar a job until none is unassigned.',
    body: 'Rather than tracking spending against a forecast, you assign all the money you actually have to specific categories. When nothing is left unassigned, the budget balances — not because you spent nothing, but because every amount has a purpose.',
    inIgab: 'The Budget page is this. Money arrives in To Be Assigned, and you distribute it into categories until To Be Assigned reaches zero.',
    related: ['to-be-assigned', 'target', 'sinking-fund'],
  },
  {
    id: 'to-be-assigned',
    term: 'To Be Assigned',
    aliases: ['tba', 'ready to assign', 'unassigned'],
    short: 'Money you have received but have not yet given a job.',
    body: 'Income lands here first. From there you move it into categories. A positive balance means there is money still waiting on a decision; a negative one means you have assigned more than you actually have.',
    inIgab: 'Shown at the top of the Budget page, with a drawer for assigning it and for covering overspent categories.',
    related: ['zero-based-budgeting', 'target'],
  },
  {
    id: 'target',
    term: 'Target',
    aliases: ['goal', 'category target'],
    short: 'The amount a category needs, and by when.',
    body: 'A target turns an intention into something the budget can check. It can mean a monthly amount, a balance to reach by a date, or a sum needed for spending in the month.',
    inIgab: 'Set on any category. The budget then shows whether that category is funded, underfunded or overfunded for the month.',
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
    inIgab: 'Money moved to a tracked debt account counts as paying down debt rather than as spending, so it stays out of your spending reports.',
    related: ['apr', 'minimum-payment', 'amortization'],
  },
  {
    id: 'minimum-payment',
    term: 'Minimum payment',
    short: 'The smallest amount a lender will accept in a given month without penalising you.',
    body: 'Paying only the minimum on a high-rate debt can mean the balance barely moves, because most of the payment covers interest. On some cards a minimum payment is close enough to the monthly interest that the debt never clears.',
    inIgab: 'Stored on a liability and used as the baseline for payoff projections — including flagging when a minimum would never pay the debt off.',
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
    short: 'Pay minimums on everything, then put every spare pound or dollar at the highest interest rate.',
    body: 'Mathematically this costs the least in total interest and usually clears all debt soonest. Its weakness is motivational: if your highest-rate debt is also your largest, it can be a long time before anything visibly disappears.',
    related: ['snowball', 'high-interest-debt', 'apr'],
  },
  {
    id: 'snowball',
    term: 'Snowball method',
    aliases: ['debt snowball', 'smallest balance first'],
    short: 'Pay minimums on everything, then put every spare pound or dollar at the smallest balance.',
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
    inIgab: 'Usually tracked as an off-budget Investment account: it counts toward net worth, but is not spendable envelope money.',
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
    inIgab: 'Computed in the Savings Rate report, on-budget only, so investment growth is never counted as money you saved.',
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
    inIgab: 'Rows the bank sync brings in as pending show a clock and are left out of every balance. When the same record posts, the row clears in place; if the posted amount differs from something you entered yourself, it is offered for review rather than changed silently.',
    related: ['uncleared', 'cleared', 'reconciled'],
  },
  {
    id: 'uncleared',
    term: 'Uncleared',
    aliases: ['unconfirmed'],
    short: 'You entered it and the money has moved in your ledger; the bank has not confirmed it yet.',
    body: 'An uncleared transaction is a real one you recorded before the bank did. It counts toward your balance because you know you spent it; it simply has not been matched to a bank record yet.',
    inIgab: 'The empty circle in the register. Clicking it marks the row cleared by hand; a bank sync that finds the matching record clears it for you.',
    related: ['pending', 'cleared', 'reconciled'],
  },
  {
    id: 'cleared',
    term: 'Cleared',
    short: 'The bank agrees this transaction happened, at this amount.',
    body: 'Cleared means confirmed: either the bank record matched, or you ticked it yourself while checking against a statement. Cleared rows are what a reconciliation compares to the bank balance.',
    inIgab: 'The filled check in the register. The cleared balance shown on an account is the sum of these rows.',
    related: ['uncleared', 'reconciled', 'pending'],
  },
  {
    id: 'reconciled',
    term: 'Reconciled',
    aliases: ['locked'],
    short: 'Checked against a bank statement and locked. The money cannot change; the bookkeeping can.',
    body: 'Reconciling an account is agreeing that its cleared balance equals what the bank says on a date. Every cleared transaction up to that date is then locked, so the agreement stays true.',
    inIgab: 'The lock in the register. A reconciled row keeps its amount, date and account fixed, but you can still edit its category, payee, memo and split lines through Edit… in the row menu; Unlock returns it to cleared.',
    related: ['cleared', 'uncleared', 'pending'],
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
