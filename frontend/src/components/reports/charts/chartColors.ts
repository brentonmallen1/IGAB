export const CHART_COLORS = [
  '#4e79a7',
  '#f28e2b',
  '#e15759',
  '#76b7b2',
  '#59a14f',
  '#edc948',
  '#b07aa1',
  '#ff9da7',
  '#9c755f',
  '#bab0ac',
  '#499894',
  '#86bcb6',
  '#d37295',
  '#fabfd2',
  '#b6992d',
]

export const COLOR_POSITIVE = '#59a14f'
export const COLOR_NEGATIVE = '#e15759'
export const COLOR_NEUTRAL = '#4e79a7'
export const COLOR_NET = '#76b7b2'

export function chartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}
