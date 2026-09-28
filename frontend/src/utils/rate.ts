/**
 * An interest rate as every liability surface prints it: the percentage to
 * at most three places, trailing zeros dropped — "6.5%", "24.99%", "6.125%",
 * "0%". The report printed the served number bare, the overview page added
 * "APR", the liability page ran it through `Number()`: several spellings of
 * one figure, one refactor from a rate stored to four places reading
 * "6.5000%" on one page and "6.5%" on the next.
 */
export function formatRate(rate: number): string {
  return `${Number(rate.toFixed(3))}%`
}
