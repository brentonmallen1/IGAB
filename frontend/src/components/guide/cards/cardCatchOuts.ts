/**
 * What catches people out about credit cards here. Prose only: every claim is
 * one the walkthroughs above show with served figures.
 */
import type { CatchOutItem } from '../CatchOuts'

export const CARD_CATCH_OUTS: CatchOutItem[] = [
  {
    id: 'set-aside-is-not-the-bill',
    title: 'Set aside is not what you should pay',
    detail:
      'It is money committed to this card so far, not a target. On a card you carry it sits far below the balance every month, and that is the normal reading — the gap is Uncovered.',
  },
  {
    id: 'uncovered-is-not-an-alarm',
    title: 'Uncovered is information, not a warning',
    detail:
      'It is debt with nothing set aside behind it — an old balance, or spending an envelope could not cover. Sitting there, it charges nothing to Ready to Assign. Paying it down from checking does, because that money leaves; assigning to the card squares its envelope.',
  },
  {
    id: 'only-a-transfer-pays',
    title: 'Only a transfer from your own account spends Set aside',
    detail:
      'Record a payment as a transfer from checking to the card. A plain deposit typed onto the card lowers the balance while Set aside stands still — which is right when somebody else paid the bill, and wrong for your own payment.',
  },
  {
    id: 'funding-does-not-reach-back',
    title: 'Funding an envelope next month does not reach back',
    detail:
      'When a month ends short, the part the envelope could not cover rides onto the card for good. Raising that month’s budget retires it, because the whole calculation is re-run every time you look. Funding the following month does not reach back. And if the shortfall rode onto two cards, the envelope funds the one charged most first — the card row says which remedy reaches it.',
  },
  {
    id: 'a-refund-goes-where-the-money-came-from',
    title: 'Money only returns to the envelope that put it on the card',
    detail:
      'A refund of something bought before you started budgeting, or a settle-up filed to an envelope that never charged this card, reduces the debt without handing any envelope its cash back. Set aside falls and can go below zero — a real position, not an error. Ready to Assign does not move: the envelope’s gain is the mirror of the card’s fall.',
  },
  {
    id: 'releasing-is-allowed',
    title: 'You can take set-aside money back out',
    detail:
      'It is not locked. Release moves it to Ready to Assign or another envelope — down to what the envelope holds and no further, because below zero there is no money, only a deficit. Past the spare part it raises Uncovered dollar for dollar: you are choosing to carry the debt another month, which is an ordinary call to make.',
  },
  {
    id: 'paying-ahead-lowers-ready-to-assign',
    title: 'Paying a card more than you set aside lowers Ready to Assign',
    detail:
      'Pay a card past what its envelope held and that money has left your account. Ready to Assign drops by the unmatched part and the hero says so — “paid ahead on cards”. Assigning to the card afterwards squares its envelope and does not move Ready to Assign again; the money went when you paid.',
  },
  {
    id: 'file-card-spending',
    title: 'Categorising card spending never takes money you do not have',
    detail:
      'An envelope only ever gives up what it actually holds; any shortfall rides on the card instead. So file everything — the spending reports come free, and the debt cannot charge you twice. A row left uncategorised moves the balance and nothing else, so all of it reads as Uncovered.',
  },
]
