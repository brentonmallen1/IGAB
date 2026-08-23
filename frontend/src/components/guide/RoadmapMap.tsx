import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minus, Plus } from 'lucide-react'
import type { StageId } from '../../content/roadmap'
import { useGuideStore } from '../../stores/guideStore'
import { GuideDialog } from './GuideDialog'
import { NodeCard } from './NodeCard'
import { stepColor } from './stepColor'
import { buildFlow, NODE_W, NODE_H, ROW_GAP, type FlowEdge } from './flowLayout'
import { useGuideSignalMap } from './useGuideSignalMap'
import { SignalBindingSheet } from './SignalBindingSheet'
import type { SignalKey } from '../../content/roadmap'

const MIN_SCALE = 0.35
const MAX_SCALE = 1.8

/**
 * The roadmap as an actual flowchart — boxes, arrows, branch labels.
 *
 * Positions and arrows both come from `flowLayout`, which derives them from
 * the roadmap content, so the diagram cannot disagree with the other views
 * about where a "No" leads.
 *
 * Pan by dragging, zoom with the wheel or the buttons. Any stage can be folded
 * to a single box, which is what lets the whole thing fit on a screen without
 * shrinking the text past reading size.
 */
export function RoadmapMap() {
  const [collapsedStages, setCollapsedStages] = useState<StageId[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [correcting, setCorrecting] = useState<SignalKey | null>(null)
  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })

  const viewportRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null)

  const expandedDetails = useGuideStore((s) => s.expandedDetails)
  const toggleDetail = useGuideStore((s) => s.toggleDetail)
  const guide = useGuideSignalMap()

  const flow = useMemo(() => buildFlow(collapsedStages), [collapsedStages])

  /** Anchor box for any drawable id — a node or a collapsed stage. */
  const boxes = useMemo(() => {
    const m = new Map<string, { x: number; y: number }>()
    for (const n of flow.nodes) m.set(n.node.id, { x: n.x, y: n.y })
    for (const c of flow.collapsed) m.set(`stage:${c.stage.id}`, { x: c.x, y: c.y })
    return m
  }, [flow])

  const fit = useCallback(() => {
    const el = viewportRef.current
    if (!el) return
    const pad = 32
    const next = Math.min(1, (el.clientWidth - pad * 2) / Math.max(flow.width, 1))
    setScale(Math.max(MIN_SCALE, next))
    setPan({ x: pad, y: pad })
  }, [flow.width])

  // Fit on first paint so the chart never opens mid-diagram or overflowing.
  useEffect(() => {
    fit()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function onPointerDown(e: React.PointerEvent) {
    if ((e.target as HTMLElement).closest('.flow-node, .flow-stage')) return
    dragRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: React.PointerEvent) {
    const d = dragRef.current
    if (!d) return
    setPan({ x: d.panX + (e.clientX - d.x), y: d.panY + (e.clientY - d.y) })
  }

  function onPointerUp(e: React.PointerEvent) {
    dragRef.current = null
    ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
  }

  // React's onWheel is registered passively, so it cannot stop the page from
  // scrolling underneath the zoom. A native non-passive listener can — and the
  // page behind the map is locked while this view is open, so the two no
  // longer fight over the same gesture.
  const scaleRef = useRef(scale)
  useEffect(() => {
    scaleRef.current = scale
  }, [scale])

  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    function onWheel(e: WheelEvent) {
      e.preventDefault()
      const rect = el!.getBoundingClientRect()
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top
      const current = scaleRef.current
      const next = clamp(current * wheelZoomFactor(e))
      if (next === current) return
      // Keep whatever is under the cursor pinned while the scale changes.
      setPan((p) => ({
        x: px - ((px - p.x) * next) / current,
        y: py - ((py - p.y) * next) / current,
      }))
      setScale(next)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  function zoomBy(factor: number) {
    const el = viewportRef.current
    const next = clamp(scale * factor)
    if (!el) return setScale(next)
    const cx = el.clientWidth / 2
    const cy = el.clientHeight / 2
    setPan((p) => ({ x: cx - ((cx - p.x) * next) / scale, y: cy - ((cy - p.y) * next) / scale }))
    setScale(next)
  }

  function toggleStage(id: StageId) {
    setCollapsedStages((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))
  }

  const selectedNode = selected ? flow.byId.get(selected) : undefined
  const correctingConcept =
    correcting && guide.budgetId ? guide.concepts.get(correcting) : undefined

  const detail = selectedNode && (
    <NodeCard
      node={selectedNode.node}
      showAllBranches
      detailOpen={expandedDetails.includes(selectedNode.node.id)}
      onToggleDetail={() => toggleDetail(selectedNode.node.id)}
      signal={selectedNode.node.signal ? guide.signals.get(selectedNode.node.signal) : undefined}
      concept={
        selectedNode.node.signal ? guide.concepts.get(selectedNode.node.signal) : undefined
      }
      onCorrectSignal={
        selectedNode.node.signal
          ? () => {
              // Swap dialogs rather than stacking them — a sheet inside a
              // sheet traps focus in the wrong one and has no sensible back.
              const key = selectedNode.node.signal!
              setSelected(null)
              setCorrecting(key)
            }
          : undefined
      }
    />
  )

  return (
    <div className="flow">
      <div className="flow__toolbar">
        <p className="flow__hint">Drag to move · scroll to zoom · click a box to read it</p>
        <div className="flow__zoom">
          <button type="button" onClick={() => zoomBy(0.85)} aria-label="Zoom out" title="Zoom out">
            <Minus size={14} />
          </button>
          <span className="flow__zoom-level tabular">{Math.round(scale * 100)}%</span>
          <button type="button" onClick={() => zoomBy(1.18)} aria-label="Zoom in" title="Zoom in">
            <Plus size={14} />
          </button>
          <button type="button" onClick={fit} aria-label="Fit to width" title="Fit to width">
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      <div
        className="flow__viewport"
        ref={viewportRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div
          className="flow__canvas"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            width: flow.width,
            height: flow.height,
          }}
        >
          <svg
            className="flow__wires"
            width={flow.width}
            height={flow.height}
            role="presentation"
            aria-hidden
          >
            <defs>
              <marker
                id="flow-arrow"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--flow-wire)" />
              </marker>
            </defs>
            {flow.edges.map((e) => {
              const a = boxes.get(e.from)
              const b = boxes.get(e.to)
              if (!a || !b) return null
              return (
                <g key={`${e.from}->${e.to}`}>
                  <path
                    d={edgePath(a, b)}
                    className={`flow__wire flow__wire--${e.kind}`}
                    markerEnd="url(#flow-arrow)"
                  />
                  {e.label && <EdgeLabel edge={e} a={a} b={b} />}
                </g>
              )
            })}
          </svg>

          {flow.collapsed.map((c) => (
            <button
              key={c.stage.id}
              type="button"
              className="flow-stage"
              style={{
                left: c.x,
                top: c.y,
                width: NODE_W,
                height: NODE_H,
                ['--stage-color' as string]: stepColor(c.stage.step),
              }}
              onClick={() => toggleStage(c.stage.id)}
              title="Expand this step"
            >
              <span className="flow-node__step">Step {c.stage.step}</span>
              <span className="flow-stage__title">{c.stage.title}</span>
              <span className="flow-stage__count">
                {c.stage.nodes.length} boxes — click to expand
              </span>
            </button>
          ))}

          {flow.nodes.map((n) => {
            const first = n.stage.nodes[0].id === n.node.id
            return (
              <div
                key={n.node.id}
                className={`flow-node flow-node--${n.node.kind}`}
                style={{
                  left: n.x,
                  top: n.y,
                  width: NODE_W,
                  height: NODE_H,
                  ['--stage-color' as string]: stepColor(n.stage.step),
                }}
              >
                <button
                  type="button"
                  className="flow-node__button"
                  onClick={() => setSelected(n.node.id)}
                >
                  {first && <span className="flow-node__step">Step {n.stage.step}</span>}
                  <span className="flow-node__title">{n.node.title}</span>
                </button>
                {first && (
                  <button
                    type="button"
                    className="flow-node__fold"
                    onClick={() => toggleStage(n.stage.id)}
                    aria-label={`Collapse step ${n.stage.step}`}
                    title={`Collapse step ${n.stage.step}`}
                  >
                    <Minus size={11} />
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Reading a box uses the same component the other views render, so a
          node's content is defined in exactly one place. */}
      {correctingConcept && (
        <SignalBindingSheet
          budgetId={guide.budgetId!}
          concept={correctingConcept}
          signal={guide.signals.get(correctingConcept.key)}
          onClose={() => setCorrecting(null)}
        />
      )}

      {selectedNode && (
        <GuideDialog
          title={`Step ${selectedNode.stage.step} — ${selectedNode.stage.title}`}
          onClose={() => setSelected(null)}
          historyKey="flow-node"
        >
          {detail}
        </GuideDialog>
      )}
    </div>
  )
}

function clamp(v: number) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, v))
}

/** How much one wheel event should zoom.
 *
 * A fixed step per event is wrong for both input devices at once: a trackpad
 * fires a stream of small deltas, so a fixed step rockets away, while a mouse
 * fires one large delta per notch. So scale the change to the delta, cap how
 * much any single event may do, and go through exp() so zooming in and back
 * out returns to exactly where it started.
 *
 * `deltaMode` 1 means the delta is in lines rather than pixels — Firefox
 * reports mouse wheels that way, and untranslated it zooms ~16x too slowly. */
function wheelZoomFactor(e: WheelEvent): number {
  const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY
  const capped = Math.max(-40, Math.min(40, px))
  return Math.exp(-capped * 0.0016)
}

type Pt = { x: number; y: number }

/** Orthogonal elbows — the shape a flowchart is expected to have.
 *  Geometry depends only on where the two boxes sit, not on the edge kind;
 *  kind drives the stroke style in CSS instead. */
function edgePath(a: Pt, b: Pt): string {
  const aMidX = a.x + NODE_W / 2
  const bMidX = b.x + NODE_W / 2
  const aMidY = a.y + NODE_H / 2
  const bMidY = b.y + NODE_H / 2
  const aBottom = a.y + NODE_H

  // Side by side on a packed row — a straight arrow between the two edges,
  // pointing whichever way the run happens to be flowing.
  if (a.y === b.y) {
    return bMidX > aMidX
      ? `M ${a.x + NODE_W} ${aMidY} L ${b.x} ${bMidY}`
      : `M ${a.x} ${aMidY} L ${b.x + NODE_W} ${bMidY}`
  }

  // Straight down the same column.
  if (aMidX === bMidX) return `M ${aMidX} ${aBottom} L ${bMidX} ${b.y}`

  // Stepping right into a side branch: out of the right edge, then down.
  if (bMidX > aMidX) return `M ${a.x + NODE_W} ${aMidY} L ${bMidX} ${aMidY} L ${bMidX} ${b.y}`

  // Dropping back left — either rejoining the spine or wrapping onto the next
  // line of a packed run. Down out of the box, across, then down into the next.
  const drop = aBottom + ROW_GAP / 2
  return `M ${aMidX} ${aBottom} L ${aMidX} ${drop} L ${bMidX} ${drop} L ${bMidX} ${b.y}`
}

function EdgeLabel({ edge, a, b }: { edge: FlowEdge; a: Pt; b: Pt }) {
  const aMidX = a.x + NODE_W / 2
  const bMidX = b.x + NODE_W / 2
  const sameRow = a.y === b.y
  const right = bMidX > aMidX
  // Sit just clear of the box the arrow leaves, on the side it leaves from.
  const x = sameRow ? (right ? a.x + NODE_W + 6 : b.x + NODE_W + 6) : right ? a.x + NODE_W + 8 : aMidX + 8
  const y = sameRow ? a.y + NODE_H / 2 - 8 : right ? a.y + NODE_H / 2 - 8 : a.y + NODE_H + 14
  return (
    <text className="flow__wire-label" x={x} y={y}>
      {edge.label}
    </text>
  )
}
