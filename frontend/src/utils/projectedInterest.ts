/**
 * The words for a projected interest row — the loan interest the server
 * writes from a liability's terms (backend `services/projected_interest.py`)
 * and retires when the lender's own interest row arrives.
 *
 * Copy only. Whether a row IS a projection is served
 * (`Transaction.projected_interest_month`); what a month should carry is the
 * server's rule and is never re-derived here. Kept in one place because the
 * register row and the editor both say it, and two spellings of what an edit
 * does to the row would drift.
 */

/** The register badge's tooltip and accessible name. */
export const PROJECTED_INTEREST_LABEL =
  "Projected interest from the loan's terms — replaced when the lender posts its own"

/** The editor's note: what the row is, and what each kind of edit does to it
 *  (backend `domain/projected_interest.adopts_projection` decides; this
 *  describes). */
export const PROJECTED_INTEREST_NOTE =
  "Projected interest, written from this loan's terms. It is replaced when the lender's own interest row arrives. Changing the amount, date, cleared state or account makes it yours; deleting it skips interest for this month."
