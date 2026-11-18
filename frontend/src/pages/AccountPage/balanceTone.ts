/**
 * An account balance's colour class: below zero is negative, anything else
 * positive. The one rule the desktop header, its equation and the phone
 * header all colour their Working and Cleared figures by, so the three cannot
 * disagree about a figure they share.
 */
export const balanceTone = (amount: number) => (amount < 0 ? 'negative' : 'positive')
