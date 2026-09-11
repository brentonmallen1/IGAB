"""Spreading lumpy charges over the months they pay for.

A bill paid twice a year has a steady COST and irregular TIMING, and a series
of monthly totals cannot tell those apart from a category whose cost genuinely
swings. Spread 600 in January across January to June and 600 in July across
July to December and the series reads a flat 100 — so what is left in the
spread is variation in the rate, which is the thing a volatility report is for.

Pure: a list of numbers in, a list of numbers out. The Volatility report's
"Amortize lumpy charges" toggle is the only reader, through
`services.report_stats.volatility_stats`.
"""

from collections.abc import Sequence


def spread_forward(totals: Sequence[float]) -> list[float | None]:
    """Each charge spread over the months it pays for, on the same grid.

    `totals` is one category's monthly total for every month of a CONTIGUOUS
    month grid, oldest first, zero where nothing was charged. A non-zero month
    is a charge. Gaps are measured in grid positions, which is why the grid
    must have no holes.

    **Before the first charge: None, not zero.** Those months were paid for
    by a charge dated before the window, which the report never saw. Counting
    them as zero made the reading depend on where the window happened to
    start: a 600 bill every six months read a flat 100 only when a charge fell
    in the window's first month, and read 0 to 600 — exactly the raw range —
    when the charges fell in its second and last. None leaves them out of the
    mean, the spread and the quartiles rather than inventing a quiet spell.

    **A charge covers the months until the next charge.** Unequal gaps are
    honest: 900 in January, April and October is 300 a month for three
    months, then 150 a month for six.

    **The last charge covers its PRIOR gap** — the rhythm the category has
    kept — clipped to the end of the grid, so only the share for months inside
    the grid is counted. Spreading it over whatever months happened to be left
    read a charge in the window's last month at full size, beside months that
    held a sixth of it.

    **A lone charge has no rhythm**, so it spreads to the end of the grid: an
    early guess, reading high for a charge made recently. The report drops a
    category with fewer than two charging months anyway.

    After the first charge, a month no charge covers is a real zero: a bill
    that stopped.
    """
    charges = [(i, amount) for i, amount in enumerate(totals) if amount]
    out: list[float | None] = [None] * len(totals)
    if not charges:
        return out
    for i in range(charges[0][0], len(totals)):
        out[i] = 0.0
    for n, (at, amount) in enumerate(charges):
        if n + 1 < len(charges):
            span = charges[n + 1][0] - at
        elif n > 0:
            span = at - charges[n - 1][0]
        else:
            span = len(totals) - at
        # Spans never overlap: each ends where the next charge begins.
        for i in range(at, min(at + span, len(totals))):
            out[i] = amount / span
    return out
