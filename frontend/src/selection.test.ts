import { describe, expect, it } from 'vitest'
import { toggleVisibleSelection } from './selection'

describe('visible selection', () => {
  it('does not mistake equal counts for identical selections', () => {
    expect([
      ...toggleVisibleSelection(new Set(['hidden']), ['visible']),
    ]).toEqual(['hidden', 'visible'])
  })
  it('deselects visible books while preserving hidden selections', () => {
    expect([
      ...toggleVisibleSelection(new Set(['hidden', 'visible']), ['visible']),
    ]).toEqual(['hidden'])
  })
})
