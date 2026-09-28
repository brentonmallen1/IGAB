/**
 * What an account's budget start date does, said once: the Budget starts
 * field's hint in account settings and the pill on the account page both
 * read it. They were two spellings of one sentence, and when the reports
 * began honouring the date, only an edit to both would have kept the pill
 * true.
 *
 * The rule is the server's — `Account.budget_start_date`, `NEEDS_CATEGORY`,
 * and rule 4 in `domain/activity_class.py` — so this only says what it does.
 */
export const BUDGET_START_NOTE =
  'Anything before this date is opening balance: kept in the register, left uncategorized on ' +
  'purpose, and counted neither as needing a category nor as income or spending in reports — ' +
  'give a row a category to count it. On a card it shows as debt not covered and is paid ' +
  'down by assigning to the card.'
