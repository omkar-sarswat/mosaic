import { Button as MantineButton } from '@mantine/core'
import { Icon, type IconName } from '@blueprintjs/core'
import type { ComponentPropsWithoutRef, ReactElement, ReactNode } from 'react'

type ButtonProps = ComponentPropsWithoutRef<'button'> & {
  className?: string
  icon?: IconName | ReactElement
  rightIcon?: IconName | ReactElement
  intent?: 'none' | 'primary' | 'success' | 'warning' | 'danger'
  small?: boolean
  large?: boolean
  minimal?: boolean
  fill?: boolean
  active?: boolean
  loading?: boolean
  text?: ReactNode
}

/** Shared Mantine action control with the workspace's sizing and semantic colors. */
export function Button({ className = '', icon, rightIcon, intent = 'none', small, large, minimal, fill, active, loading, disabled, text, children, ...props }: ButtonProps) {
  const classes = ['ui-button', 'bp6-button', `bp6-intent-${intent}`, small && 'bp6-small', large && 'bp6-large', minimal && 'bp6-minimal', active && 'bp6-active', fill && 'bp6-fill', (disabled || loading) && 'bp6-disabled', className].filter(Boolean).join(' ')
  const renderIcon = (value: IconName | ReactElement) => typeof value === 'string' ? <Icon icon={value} size={small ? 14 : 16} /> : value
  return (
    <MantineButton {...props} className={classes} disabled={disabled || loading} loading={loading} variant={minimal ? 'subtle' : intent === 'primary' || intent === 'success' ? 'filled' : 'default'} size={small ? 'xs' : large ? 'md' : 'sm'} fullWidth={fill} leftSection={icon && renderIcon(icon)} rightSection={rightIcon && renderIcon(rightIcon)} aria-busy={loading || undefined} aria-pressed={props['aria-pressed'] ?? (active === undefined ? undefined : active)}>
      {text}{children}
    </MantineButton>
  )
}
