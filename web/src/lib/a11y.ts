import type { KeyboardEvent } from 'react'

/** Props that make a non-button element (a table row) work from the keyboard as well as the mouse:
 * focusable, and Enter or Space does what a click does. Use real buttons wherever the markup allows. */
export function activate(fn: () => void) {
  return {
    tabIndex: 0,
    onClick: fn,
    onKeyDown: (e: KeyboardEvent) => {
      if (e.target !== e.currentTarget) return
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        fn()
      }
    },
  }
}
