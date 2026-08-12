// === STAGE 21.8 TOGGLE BUTTON ===
import type {
  ButtonHTMLAttributes,
  ReactNode,
} from 'react'

export default function ToggleButton({
  pressed,
  onPressedChange,
  children,
  className = '',
  disabled = false,
  ...buttonProps
}: {
  pressed: boolean
  onPressedChange: (
    pressed: boolean,
  ) => void
  children: ReactNode
  className?: string
  disabled?: boolean
} & Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'type' | 'onChange' | 'onClick'
>) {
  return (
    <button
      {...buttonProps}
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      className={`toggle-button ${
        pressed
          ? 'toggle-button-active'
          : ''
      } ${className}`.trim()}
      onClick={() =>
        onPressedChange(!pressed)
      }
    >
      {children}
    </button>
  )
}
