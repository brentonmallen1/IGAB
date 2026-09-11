import { toCents } from '../../utils/money'
import { isCardAccount, isCashAccount, type AccountKindFields } from '../../utils/accountKinds'

/**
 * What closing an account is about to do to the budget, said before it happens.
 *
 * Closing moves no money. That is the whole point of the sentence: `is_closed`
 * and `on_budget` are independent, and the app deliberately keeps them that
 * way — `on_budget` is read at query time by the activity classifier, so
 * flipping it on close would reclassify every historical row on the account.
 * Spending from an old checking account would become activity inside a tracked
 * account; transfers into it would become saving. Reports would change because
 * someone tidied up.
 *
 * The cost of that choice is a closed on-budget account whose balance goes on
 * funding Ready to Assign from somewhere no longer in the sidebar. Cards said
 * so already. Cash accounts said nothing at all — you could close a checking
 * account with $400 in it and get a bare "Close this account?" — which is the
 * gap this fills, and which `AccountHygiene._closed_account_still_holds_money`
 * catches afterwards for the ones already closed that way.
 *
 * Returns null when there is nothing worth saying: an emptied cash account, or
 * anything off budget, where closing really is only tidying.
 */
export interface ClosingAccount extends AccountKindFields {
  balance: number
}

export function closeAccountMessage(
  account: ClosingAccount,
  money: (amount: number) => string
): string | null {
  // In cents: below one is float dust from summing a ledger, not money.
  const holdsMoney = toCents(account.balance) !== 0

  if (isCardAccount(account)) {
    // A card's set-aside outlives the card, so this one speaks even at zero:
    // the envelope can still hold money the balance does not show.
    return holdsMoney
      ? `This card’s balance is ${money(account.balance)}. Closing moves no money — the balance ` +
          `and anything reserved to pay it stay in the budget’s Credit cards section until both ` +
          `reach zero.`
      : `Closing moves no money — anything still reserved to pay this card keeps reducing Ready ` +
          `to Assign until you move it out or record a payment.`
  }

  if (isCashAccount(account) && holdsMoney) {
    return (
      `This account holds ${money(account.balance)}. Closing moves no money — that balance stays ` +
      `on budget and goes on funding Ready to Assign from an account that will no longer be in ` +
      `your sidebar. Move it out first if the account is really empty.`
    )
  }

  // An emptied cash account, or anything off budget: closing is tidying and
  // nothing about the budget changes.
  return null
}
