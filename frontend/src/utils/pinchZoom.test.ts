import { describe, expect, it } from 'vitest'
import { distance, isDoubleTap, midpoint, panTranslate, pinchScale } from './pinchZoom'

describe('pinchScale', () => {
  it('scales by how far the fingers spread', () => {
    expect(pinchScale(1, 100, 200)).toBe(2)
    expect(pinchScale(2, 100, 150)).toBe(3)
  })

  it('never goes below 1× or above 4×', () => {
    expect(pinchScale(1, 100, 20)).toBe(1)
    expect(pinchScale(3, 100, 400)).toBe(4)
  })

  it('holds the scale when the starting distance is meaningless', () => {
    expect(pinchScale(2, 0, 100)).toBe(2)
  })
})

describe('panTranslate', () => {
  it('moves the image by the finger travel, divided by the scale', () => {
    // 100px of finger at 2× moves the image 50 image-px.
    expect(panTranslate({ x: 10, y: 10, tx: 0, ty: 0 }, { x: 110, y: 60 }, 2)).toEqual({
      translateX: 50,
      translateY: 25,
    })
  })

  it('continues from where the last pan left the image', () => {
    expect(panTranslate({ x: 0, y: 0, tx: 30, ty: -10 }, { x: 40, y: 40 }, 1)).toEqual({
      translateX: 70,
      translateY: 30,
    })
  })
})

describe('geometry', () => {
  it('measures finger distance and midpoint', () => {
    expect(distance({ clientX: 0, clientY: 0 }, { clientX: 3, clientY: 4 })).toBe(5)
    expect(midpoint({ clientX: 0, clientY: 0 }, { clientX: 4, clientY: 2 })).toEqual({ x: 2, y: 1 })
  })
})

describe('isDoubleTap', () => {
  it('is two taps within 300ms', () => {
    expect(isDoubleTap(1000, 800)).toBe(true)
    expect(isDoubleTap(1000, 600)).toBe(false)
    expect(isDoubleTap(1000, 0)).toBe(false)
  })
})
