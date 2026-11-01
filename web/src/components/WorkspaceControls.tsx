import { Drawer, Popover } from '@mantine/core'
import { Icon } from '@blueprintjs/core'
import type { ReactNode } from 'react'
import type { User } from '../api'
import { initials } from '../lib/format'
import { Button } from './Button'

export function MobileNavigation({ open, onOpenChange, children }: {
  open: boolean; onOpenChange: (open: boolean) => void; children: ReactNode
}) {
  return <>
    <button className="icon-button mobile-nav-toggle" aria-label="Open navigation" aria-expanded={open} onClick={() => onOpenChange(true)}><Icon icon="menu" /></button>
    <Drawer opened={open} onClose={() => onOpenChange(false)} title="Workspace navigation" size={300} classNames={{ content: 'navigation-drawer', body: 'navigation-drawer-body', header: 'navigation-drawer-header' }}>
      {children}
    </Drawer>
  </>
}

const ROLE_LABEL: Record<string, string> = {
  io: 'Investigating officer', supervisor: 'Supervising officer', analyst: 'Analyst', steward: 'Data steward',
  auditor: 'Oversight officer', viewer: 'Read-only', operator: 'Control-room operator', admin: 'Administrator',
}

export function AccountMenu({ me, users, userId, onUserChange, onLogout }: {
  me: User | null; users: User[]; userId: string; onUserChange: (id: string) => void; onLogout?: () => void
}) {
  const short = me ? initials(me.name.split(',')[0]) : ''
  return <Popover position="bottom-end" shadow="md" withinPortal trapFocus returnFocus>
    <Popover.Target>
      <button className="account-trigger" aria-label={me ? `Account: ${me.name}` : 'Account'} title={me?.name}>
        <span className="account-avatar" aria-hidden>{short || <Icon icon="user" size={14} />}</span><Icon icon="chevron-down" size={12} />
      </button>
    </Popover.Target>
    <Popover.Dropdown className="workspace-popover account-popover">
      <h2>{me?.name ?? 'Signing in…'}</h2>
      <p>{me ? `${me.agency} · ${ROLE_LABEL[me.role] ?? me.role}` : ''}</p>
      {users.length > 0 && <label className="account-switcher">Demonstration account<select value={userId} onChange={(event) => onUserChange(event.target.value)}>{users.map((user) => <option key={user.id} value={user.id}>{user.agency} · {user.name}</option>)}</select></label>}
      {onLogout && <div className="account-actions"><Button icon="log-out" onClick={onLogout}>Sign out</Button></div>}
      <div className="account-note"><Icon icon="shield" size={14} /><span>Access follows your role, agency and active case. Every look-up is recorded.</span></div>
    </Popover.Dropdown>
  </Popover>
}
