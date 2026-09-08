import type { Grounding } from '../../../api/chatStream'

/**
 * What to say about an answer's figures.
 *
 * The check is mechanical; this is the sentence a person reads. Three
 * decisions shape it:
 *
 * - **Silence when there is nothing to say.** An answer with no figures gets
 *   no badge. A reassurance printed under every reply is wallpaper within a
 *   day, and wallpaper is not read on the day it matters.
 * - **Name the figure that failed, not the count.** "1 figure could not be
 *   checked" sends you hunting; "$4,182.33 isn't in what it looked up" points
 *   at the thing.
 * - **Never say "verified".** The check proves a number appeared in the data,
 *   not that the answer reasons about it correctly. Claiming more than that
 *   would buy confidence the mechanism has not earned.
 */
export type GroundingTone = 'ok' | 'warn' | 'none'

export interface GroundingNote {
  tone: GroundingTone
  text: string
}

const NOTHING: GroundingNote = { tone: 'none', text: '' }

export function groundingNote(grounding: Grounding | null | undefined): GroundingNote {
  if (!grounding) return NOTHING

  // Figures stated with nothing looked up at all — the worst case, and worth
  // saying plainly even though every figure is technically "unsupported".
  if (grounding.figures > 0 && grounding.lookups === 0) {
    return {
      tone: 'warn',
      text: 'This answer gives figures without looking anything up. Check them against your budget.',
    }
  }

  if (grounding.unsupported.length > 0) {
    const named = grounding.unsupported.slice(0, 3).join(', ')
    const rest = grounding.unsupported.length - 3
    return {
      tone: 'warn',
      text:
        rest > 0
          ? `${named} and ${rest} more aren't in what it looked up. Check them.`
          : `${named} ${grounding.unsupported.length === 1 ? "isn't" : "aren't"} in what it looked up. Check ${grounding.unsupported.length === 1 ? 'it' : 'them'}.`,
    }
  }

  if (grounding.figures === 0) return NOTHING

  const n = grounding.figures
  return {
    tone: 'ok',
    text: `${n === 1 ? 'The figure' : `All ${n} figures`} here came from your budget.`,
  }
}
