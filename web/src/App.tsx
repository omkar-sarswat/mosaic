import { authMode, isDemo, logout } from './auth'
import { Classes, Icon, NonIdealState, type IconName } from '@blueprintjs/core'
import { Button } from './components/Button'
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { api, setIdentity, type CaseRow, type User } from './api'
import { CaseContext, Logo } from './components/Diary'
import Omnibox from './components/Omnibox'
import { AccountMenu, MobileNavigation } from './components/WorkspaceControls'
import { MantineProvider, Modal, Select, TextInput, Textarea, createTheme, type MantineColorsTuple } from '@mantine/core'
const Alerts = lazy(() => import('./views/Alerts'))
const Cases = lazy(() => import('./views/Cases'))
const Connect = lazy(() => import('./views/Connect'))
const Dossier = lazy(() => import('./views/Dossier'))
const Explore = lazy(() => import('./views/Explore'))
const FaceSearch = lazy(() => import('./views/FaceSearch'))
const Globe = lazy(() => import('./views/Globe'))
import Investigate from './views/Investigate'
const Leads = lazy(() => import('./views/Leads'))
const DataStudio = lazy(() => import('./views/DataStudio'))
const MapView = lazy(() => import('./views/MapView'))
const Money = lazy(() => import('./views/Money'))
const Oversight = lazy(() => import('./views/Oversight'))
const Review = lazy(() => import('./views/Review'))
const Admin = lazy(() => import('./views/Admin'))
const Watchlist = lazy(() => import('./views/Watchlist'))
import { SessionMarking } from './components/Marking'
import { resetMarking } from './lib/marking'
import Today from './views/Today'
import type { Nav, ViewId } from './views/nav'

const RAIL: { id: ViewId; icon: IconName; label: string }[] = [
  { id: 'home', icon: 'home', label: 'Overview' },
  { id: 'cases', icon: 'folder-shared-open', label: 'Cases' },
  { id: 'leads', icon: 'search-around', label: 'Leads' },
  { id: 'alerts', icon: 'flag', label: 'Alerts' },
  { id: 'watch', icon: 'notifications', label: 'Watchlist' },
  { id: 'graph', icon: 'graph', label: 'Network' },
  { id: 'dossier', icon: 'person', label: 'Dossier' },
  { id: 'connect', icon: 'link', label: 'Connections' },
  { id: 'money', icon: 'bank-account', label: 'Money trail' },
  { id: 'globe', icon: 'globe', label: 'Map' },
  { id: 'studio', icon: 'th-derived', label: 'Data studio' },
  { id: 'review', icon: 'people', label: 'Review matches' },
  { id: 'explore', icon: 'search-template', label: 'Explorer' },
  { id: 'faces', icon: 'mugshot', label: 'Face search' },
  { id: 'cop', icon: 'map', label: 'Disaster map' },
  { id: 'oversight', icon: 'eye-open', label: 'Oversight' },
  { id: 'admin', icon: 'cog', label: 'Administration' },
]

const NAV_GROUPS: { label: string; ids: ViewId[] }[] = [
  { label: 'Workspace', ids: ['home', 'cases', 'leads', 'alerts', 'watch'] },
  { label: 'Investigation', ids: ['graph', 'dossier', 'money', 'connect', 'globe'] },
  { label: 'Records', ids: ['explore', 'studio', 'review', 'faces'] },
  { label: 'Operations', ids: ['cop'] },
  { label: 'Governance', ids: ['oversight', 'admin'] },
]

// Who each screen is for. The server enforces access either way; the workspace only offers screens a
// role can use, so nobody lands on a page that can only say "not for you". Unlisted screens are for all.
const INVESTIGATORS = ['io', 'supervisor', 'analyst']
const VIEW_ROLES: Partial<Record<ViewId, string[]>> = {
  cases: [...INVESTIGATORS, 'viewer'], leads: INVESTIGATORS, alerts: INVESTIGATORS, watch: INVESTIGATORS,
  graph: INVESTIGATORS, dossier: [...INVESTIGATORS, 'viewer'], money: INVESTIGATORS, connect: INVESTIGATORS, globe: INVESTIGATORS,
  explore: [...INVESTIGATORS, 'viewer', 'steward'], studio: [...INVESTIGATORS, 'steward'], review: ['analyst', 'supervisor', 'steward'], faces: INVESTIGATORS,
  admin: ['admin', 'steward', 'auditor'],
}
const allowedFor = (me: User | null, v: ViewId) => !VIEW_ROLES[v] || !!me?.roles.some((r) => VIEW_ROLES[v]!.includes(r))

const ink: MantineColorsTuple = ['#f4f4f2', '#e6e6e3', '#cbcbc7', '#aeafaa', '#959691', '#868781', '#7d7e79', '#6a6b66', '#3b3e44', '#24262a']
const workspaceTheme = createTheme({
  fontFamily: 'Public Sans Variable, system-ui, sans-serif',
  colors: { ink }, primaryColor: 'ink', primaryShade: { light: 9, dark: 2 }, defaultRadius: 'xs',
  fontSizes: { xs: '12px', sm: '13px', md: '14px', lg: '16px', xl: '20px' },
  headings: { fontFamily: 'Public Sans Variable, system-ui, sans-serif', fontWeight: '600' },
})

const VIEW_DESCRIPTIONS: Partial<Record<ViewId, string>> = {
  leads: 'Review patterns, check the evidence, and decide what to follow.',
  alerts: 'Review activity flagged in your case.',
  watch: 'People, numbers, vehicles, accounts and places this case follows, and searches that keep running.',
  studio: 'Prepare source records and review them before publication.',
  money: 'Trace transfers, account holders, and destinations.',
  globe: 'Locate case records and examine where events overlap.',
  connect: 'Find shared records and connections between subjects.',
  explore: 'Browse the records available to your role and case.',
  faces: 'Compare an image with the records available to this case.',
  cop: 'View incidents, affected areas, and response resources.',
  review: 'Compare source records and decide whether they describe the same person.',
  oversight: 'Inspect access, decisions, and the audit trail.',
  admin: 'How the detectors and record matching work, how well they perform, and the quality of source data.',
}

const load = (k: string, d = '') => {
  try {
    return localStorage.getItem(k) ?? d
  } catch {
    return d
  }
}
const save = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v)
  } catch {
    /* storage unavailable */
  }
}
const systemTheme = () => (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')

const link = new URLSearchParams(window.location.search)
if (link.get('user')) save('drishti.user', link.get('user')!)
if (link.get('case') && link.get('user')) save(`drishti.case.${link.get('user')}`, link.get('case')!)

export default function App() {
  const [users, setUsers] = useState<User[]>([])
  const [userId, setUserId] = useState(load('drishti.user', 'crime.pi'))
  const [me, setMe] = useState<User | null>(null)
  const [cases, setCases] = useState<CaseRow[]>([])
  const [caseId, setCaseId] = useState('')
  const [view, setView] = useState<ViewId>(RAIL.find((item) => item.id === link.get('view'))?.id ?? 'home')
  const [focus, setFocus] = useState<string | null>(null)
  const [entity, setEntity] = useState<string | null>(link.get('id'))
  const [graphRoot, setGraphRoot] = useState<string | null>(link.get('view') === 'graph' ? link.get('id') : null)
  const [traceRoot, setTraceRoot] = useState<string | null>(link.get('view') === 'money' ? link.get('id') : null)
  const [caseView, setCaseView] = useState<string | null>(null)
  const [connectSeed, setConnectSeed] = useState<string | null>(link.get('view') === 'connect' ? link.get('id') : null)
  const [history, setHistory] = useState<string[]>([])
  const [theme, setTheme] = useState(load('drishti.theme', systemTheme()))
  const [openCase, setOpenCase] = useState(false)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)
  const [navOpen, setNavOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.body.classList.toggle(Classes.DARK, theme === 'dark')
    save('drishti.theme', theme)
  }, [theme])

  useEffect(() => {
    if (authMode() === 'dev') api.devUsers().then(setUsers).catch(() => setUsers([]))
  }, [])

  const refreshMe = useCallback(
    (prefer?: string) => {
      setIdentity(userId, '')
      api
        .me()
        .then((r) => {
          setMe(r.user)
          setCases(r.cases)
          const open = r.cases.filter((c) => c.status === 'open')
          const remembered = prefer ?? load(`drishti.case.${userId}`)
          const next = open.find((c) => c.id === remembered)?.id ?? open[0]?.id ?? ''
          setCaseId(next)
          setIdentity(userId, next)
          setTick((t) => t + 1)
        })
        .catch((e) => setError(String(e.message || e)))
    },
    [userId],
  )

  useEffect(() => {
    save('drishti.user', userId)
    refreshMe()
  }, [userId, refreshMe])

  // a new officer or a new case starts a new handling session: the footer marking starts again from RESTRICTED
  useEffect(() => resetMarking(), [userId, caseId])

  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(''), 7000)
    return () => clearTimeout(t)
  }, [error])

  const chooseCase = (id: string) => {
    setCaseId(id)
    save(`drishti.case.${userId}`, id)
    setIdentity(userId, id)
    setTick((t) => t + 1)
  }
  const goTo = (v: ViewId, id: string | null = null) => {
    setFocus(id)
    setView(v)
    setNavOpen(false)
  }

  const nav: Nav = useMemo(
    () => ({
      me,
      caseId,
      activeCase: cases.find((c) => c.id === caseId),
      tick,
      focus,
      setError,
      refresh: () => setTick((t) => t + 1),
      openEntity: (id: string) => {
        setHistory((h) => (entity ? [...h.slice(-30), entity] : h))
        setEntity(id)
        goTo('dossier')
      },
      openTrace: (id: string) => {
        setTraceRoot(id)
        goTo('money')
      },
      openGraph: (id: string) => {
        setGraphRoot(id)
        goTo('graph')
      },
      openCase: (id: string) => {
        if (cases.some((c) => c.id === id && c.status === 'open')) chooseCase(id)
        setCaseView(id)
        goTo('cases')
      },
      openGlobe: () => goTo('globe'),
      openConnect: (id?: string) => {
        if (id) setConnectSeed(id)
        goTo('connect')
      },
      go: (v: ViewId) => goTo(v),
      open: (v: ViewId, id?: string | null) => goTo(v, id ?? null),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [me, caseId, cases, tick, entity, focus],
  )

  const legacy = { me, caseId, activeCase: nav.activeCase, selected: entity, setSelected: (id: string | null) => id && nav.openEntity(id), openGraph: nav.openGraph, tick, setError, refresh: nav.refresh }
  const canOpenCase = !!me && (me.roles.includes('io') || me.roles.includes('supervisor'))
  const allowed = (v: ViewId) => allowedFor(me, v)
  const groups = NAV_GROUPS.map((g) => ({ ...g, ids: g.ids.filter(allowed) })).filter((g) => g.ids.length)
  const current = RAIL.find((r) => r.id === view)
  const group = groups.find((item) => item.ids.includes(view))
  const ready = !!me && me.id === userId
  const navigation = (
    <nav className="rail" aria-label="Applications">
      <div className="brand"><Logo /><div><strong>MOSAIC</strong><small>{me?.agency ?? 'Investigation workspace'}</small></div></div>
      <div className="navigation-groups">
        {groups.map((section) => (
          <div className="nav-group" key={section.label}>
            <div className="nav-group-label">{section.label}</div>
            {section.ids.map((id) => RAIL.find((r) => r.id === id)!).map((item) => (
              <button key={item.id} className={view === item.id ? 'on' : ''} aria-current={view === item.id ? 'page' : undefined} onClick={() => goTo(item.id)}>
                <Icon icon={item.icon} size={16} /><span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="rail-footer"><Icon icon="shield" size={16} /><div><strong>Case-bound access</strong><span>Every look-up is recorded</span></div></div>
    </nav>
  )

  return (
    <MantineProvider theme={workspaceTheme} forceColorScheme={theme === 'dark' ? 'dark' : 'light'}>
    <div className="shell2">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <div className="body2">
        <div className="work-area">
          <header className="appbar">
            <MobileNavigation open={navOpen} onOpenChange={setNavOpen}>{navigation}</MobileNavigation>
            <button className="top-brand" onClick={() => goTo('home')} aria-label="Mosaic overview"><Logo /><strong>MOSAIC</strong></button>
            <nav className="global-navigation" aria-label="Workspace sections">
              {groups.map((section) => <button key={section.label} aria-current={group?.label === section.label ? 'true' : undefined} onClick={() => goTo(section.ids[0])}>{section.label}</button>)}
            </nav>
            <Omnibox key={`${userId}:${caseId}`} onPick={nav.openEntity} className={searchOpen ? 'open-mobile' : ''} autoFocus={searchOpen} onDismiss={() => setSearchOpen(false)} />
            <button className="icon-button search-toggle" aria-label="Search records" aria-expanded={searchOpen} onClick={() => setSearchOpen(true)}><Icon icon="search" size={16} /></button>
            <button className="icon-button theme-toggle" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} title={theme === 'dark' ? 'Light theme' : 'Dark theme'}><Icon icon={theme === 'dark' ? 'flash' : 'moon'} size={16} /></button>
            <AccountMenu me={me} users={users} userId={userId} onUserChange={setUserId} onLogout={authMode() === 'oidc' && me ? logout : undefined} />
          </header>
          <div className="subbar">
            <nav className="tool-navigation" aria-label="Section tools">
              {history.length > 0 && view === 'dossier' && (
                <button aria-label="Back to the previous record" title="Back to the previous record" onClick={() => (setEntity(history.at(-1)!), setHistory((h) => h.slice(0, -1)))}><Icon icon="arrow-left" size={14} /></button>
              )}
              {group?.ids.map((id) => RAIL.find((item) => item.id === id)!).map((item) => <button key={item.id} aria-current={view === item.id ? 'page' : undefined} onClick={() => goTo(item.id)}>{item.label}</button>)}
            </nav>
            {ready && <CaseContext cases={cases} caseId={caseId} onChoose={chooseCase} onNewCase={canOpenCase ? () => setOpenCase(true) : undefined} />}
          </div>
          <main id="main-content" className="stage" tabIndex={-1} aria-label={current?.label}>
            {error && (
              <div className="toast" role="alert">
                <span>{error}</span><Button minimal small icon="cross" aria-label="Dismiss" onClick={() => setError('')} />
              </div>
            )}
            {!ready && (
              <div className="app-loading" role="status"><Icon icon="database" size={26} /><h2>Opening workspace</h2><p>Loading your account and cases.</p>
                {error && <Button onClick={() => refreshMe()}>Try again</Button>}</div>
            )}
            {ready && !allowed(view) && (
              <NonIdealState icon="lock" title={`${current?.label ?? 'This screen'} is not part of your role`}
                description="Access follows your role and agency. The screens you can use are in the navigation above."
                action={<Button intent="primary" onClick={() => goTo('home')}>Go to overview</Button>} />
            )}
            {ready && allowed(view) && (
              <div className={`view-content view-${view}`} key={`${userId}:${caseId}:${view}`}>
                {VIEW_DESCRIPTIONS[view] && <div className="screen-heading"><div><h1>{current?.label}</h1><p>{VIEW_DESCRIPTIONS[view]}</p></div><span className="scope-label"><Icon icon="lock" size={12} />{caseId ? 'Scoped to the active case' : 'Scoped to your role'}</span></div>}
                <Suspense fallback={<div className="app-loading" role="status">Loading {current?.label?.toLowerCase() ?? 'workspace'}…</div>}>
                {view === 'home' && <Today nav={nav} onNewCase={canOpenCase ? () => setOpenCase(true) : undefined} />}
                {view === 'leads' && <Leads nav={nav} />}
                {view === 'studio' && <DataStudio nav={nav} />}
                {view === 'dossier' && <Dossier id={entity} nav={nav} />}
                {view === 'graph' && <Investigate root={graphRoot} nav={nav} />}
                {view === 'money' && <Money root={traceRoot} nav={nav} />}
                {view === 'globe' && <Globe caseId={caseId || null} nav={nav} />}
                {view === 'cases' && <Cases caseId={caseView || caseId} nav={nav} />}
                {view === 'alerts' && <Alerts nav={nav} />}
                {view === 'explore' && <Explore {...legacy} />}
                {view === 'connect' && <Connect nav={nav} seed={connectSeed} />}
                {view === 'faces' && <FaceSearch nav={nav} />}
                {view === 'cop' && <MapView {...legacy} />}
                {view === 'review' && <Review {...legacy} focus={focus} />}
                {view === 'oversight' && <Oversight {...legacy} />}
                {view === 'admin' && <Admin nav={nav} />}
                {view === 'watch' && <Watchlist nav={nav} />}
              </Suspense></div>
            )}
          </main>
        </div>
      </div>
      {isDemo()
        ? <footer className="classif" role="note" aria-label="Handling"><span><span className="status-dot" /><b>Demonstration</b><span className="footer-divider">/</span>Synthetic records</span><span>Access is scoped to your role and active case</span><span><span className="marking-label">Highest marking on screen</span><SessionMarking /></span></footer>
        : <footer className="classif marking" role="note" aria-label="Handling"><span><SessionMarking /><span className="footer-divider">/</span>For authorised officers only</span><span>{nav.activeCase ? `Working under ${nav.activeCase.purpose.replaceAll('_', ' ')} · ${nav.activeCase.id}` : 'No case open: personal records hidden'}</span><span>Every look-up is recorded</span></footer>}
      <OpenCaseDialog
        isOpen={openCase}
        onClose={() => setOpenCase(false)}
        onOpened={(id) => {
          setOpenCase(false)
          save(`drishti.case.${userId}`, id)
          refreshMe(id)
        }}
      />
    </div>
    </MantineProvider>
  )
}

function OpenCaseDialog({ isOpen, onClose, onOpened }: { isOpen: boolean; onClose: () => void; onOpened: (id: string) => void }) {
  const [purposes, setPurposes] = useState<string[]>([])
  const [purpose, setPurpose] = useState('')
  const [title, setTitle] = useState('')
  const [basis, setBasis] = useState('')
  const [fir, setFir] = useState('')
  const [err, setErr] = useState('')
  const [submitting, setSubmitting] = useState(false)
  useEffect(() => {
    if (isOpen)
      api.ontology().then((o) => {
        setPurposes(o.purposes)
        setPurpose((p) => p || o.purposes[0])
      }).catch((error) => setErr(error.message))
  }, [isOpen])
  const submit = () => {
    if (submitting || !purpose || basis.trim().length < 10) return
    setSubmitting(true)
    setErr('')
    api
      .action<{ case_id: string }>('open_case', { purpose, legal_basis: basis, fir_no: fir || undefined, title })
      .then((r) => onOpened(r.case_id))
      .catch((e) => setErr(e.message))
      .finally(() => setSubmitting(false))
  }
  return (
    <Modal opened={isOpen} onClose={onClose} title="Open a case" centered classNames={{ content: 'case-modal', header: 'case-modal-header', body: 'case-modal-body' }}>
      <form onSubmit={(event) => { event.preventDefault(); submit() }}>
        <p className="muted small">Every look-up is recorded against this case and its lawful purpose.</p>
        <TextInput label="Title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Case or operation name" data-autofocus />
        <Select label="Purpose" value={purpose} onChange={(value) => setPurpose(value ?? '')} data={purposes.map((value) => ({ value, label: value.replaceAll('_', ' ') }))} allowDeselect={false} searchable />
        <Textarea label="Legal basis" description="FIR, ECIR, RC, or order and the provisions relied on. At least 10 characters." minRows={3} autosize value={basis} onChange={(event) => setBasis(event.target.value)} />
        <TextInput label="Record number (optional)" description="Matching FIR, ECIR, or RC records enter the case." value={fir} onChange={(event) => setFir(event.target.value)} />
        {err && <p className="err" role="alert">{err}</p>}
        <div className="case-modal-actions"><Button onClick={onClose}>Cancel</Button><Button type="submit" intent="primary" loading={submitting} disabled={!purpose || basis.trim().length < 10}>Open case</Button></div>
      </form>
    </Modal>
  )
}
