import { TOOL_IDS, type ToolId } from '../../../content/roadmap'

/**
 * The calculators on the Tools tab, and how the roadmap names them.
 *
 * The ids live with the content (a node names its tool); the labels live
 * here with the components that render them. `Record<ToolId, …>` is what
 * keeps the two in step: a new id without a registry entry does not typecheck.
 */
export interface ToolDef {
  id: ToolId
  label: string
  blurb: string
  /** The link text a roadmap node shows. */
  linkLabel: string
}

export const TOOLS: Record<ToolId, ToolDef> = {
  'payoff-plan': {
    id: 'payoff-plan',
    label: 'Payoff planner',
    blurb:
      'Avalanche against snowball with your real debts — including what a cleared debt frees up for the next one — measured against just paying the minimums.',
    linkLabel: 'Open the payoff planner',
  },
  'pay-vs-save': {
    id: 'pay-vs-save',
    label: 'Pay down or save?',
    blurb:
      'Put extra money against a debt, or into savings at a rate you can get today? Interest avoided against interest earned, over the same months.',
    linkLabel: 'Compare paying down with saving',
  },
  'loan-compare': {
    id: 'loan-compare',
    label: 'Which loan?',
    blurb: 'Two or more loans side by side: the payment, the interest, and what it all costs with fees.',
    linkLabel: 'Compare loans',
  },
  'emergency-fund': {
    id: 'emergency-fund',
    label: 'Emergency fund',
    blurb:
      'How big, from your own essential spending — and how long the gap takes to close at what you can put aside.',
    linkLabel: 'Size your emergency fund',
  },
}

export const TOOL_LIST: ToolDef[] = TOOL_IDS.map((id) => TOOLS[id])
