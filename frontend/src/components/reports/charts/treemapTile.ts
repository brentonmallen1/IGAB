/** A treemap tile's name label, pure so it is testable: recharts renders the
 * tile at zero size under jsdom. */
import { truncateLabel } from '../../../utils/truncateLabel'

/** Horizontal pixels one label character is given — the font shrinks with a
 * narrow tile by the same measure the label is cut by. */
const PX_PER_CHAR = 7

/** The label's font size: 12px, smaller on a tile too narrow for it. */
export function tileFontSize(width: number): number {
  return Math.min(12, width / PX_PER_CHAR)
}

/** The name, cut to what fits across the tile by the rule every chart shares.
 * The tile once sliced its own (`floor(width / 7) - 1`), one character wider
 * than every chart at the same limit. */
export function tileLabel(name: string, width: number): string {
  return truncateLabel(name, Math.floor(width / PX_PER_CHAR))
}
