// Sign-in for deployments with DRISHTI_AUTH=oidc: OpenID Connect Authorization Code flow with PKCE (RFC 7636)
// against Keycloak or any OIDC provider. In dev mode (synthetic data only) nothing here runs.
//
// Tokens are held in memory only, never in localStorage or sessionStorage, so script injected into the page
// cannot lift them from storage. A reload sends the browser back through the provider, which returns at once
// while its own session (an HttpOnly cookie on the provider's domain) is valid. Only the PKCE verifier and
// state live briefly in sessionStorage, between the redirect and the callback.

export type AuthConfig = { mode: 'dev' | 'oidc'; issuer?: string; client_id?: string }
type Discovery = { authorization_endpoint: string; token_endpoint: string; end_session_endpoint?: string }
type Tokens = { access_token: string; refresh_token?: string; id_token?: string; expires_in: number }

let config: AuthConfig = { mode: 'dev' }
let discovery: Discovery | null = null
let tokens: Tokens | null = null
let refreshTimer: number | undefined

const PENDING = 'drishti.oidc.pending'

function b64url(bytes: Uint8Array): string {
  let s = ''
  bytes.forEach((b) => (s += String.fromCharCode(b)))
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function randomString(bytes = 32): string {
  return b64url(crypto.getRandomValues(new Uint8Array(bytes)))
}

async function challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return b64url(new Uint8Array(digest))
}

function redirectUri(): string {
  return `${window.location.origin}/`
}

async function login(): Promise<never> {
  const verifier = randomString(48)
  const state = randomString(16)
  const returnTo = window.location.pathname + window.location.search + window.location.hash
  sessionStorage.setItem(PENDING, JSON.stringify({ verifier, state, returnTo }))
  const params = new URLSearchParams({
    client_id: config.client_id!, response_type: 'code', scope: 'openid', redirect_uri: redirectUri(),
    state, code_challenge: await challenge(verifier), code_challenge_method: 'S256',
  })
  window.location.assign(`${discovery!.authorization_endpoint}?${params}`)
  return new Promise<never>(() => {})
}

async function tokenRequest(body: Record<string, string>): Promise<Tokens> {
  const res = await fetch(discovery!.token_endpoint, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: config.client_id!, ...body }),
  })
  if (!res.ok) throw new Error(`sign-in failed (${res.status})`)
  return res.json()
}

function schedule(t: Tokens) {
  tokens = t
  window.clearTimeout(refreshTimer)
  if (!t.refresh_token) return
  // refresh a minute before expiry; if that fails the next API call gets 401 and sign-in starts again
  refreshTimer = window.setTimeout(async () => {
    try {
      schedule(await tokenRequest({ grant_type: 'refresh_token', refresh_token: tokens!.refresh_token! }))
    } catch {
      tokens = null
    }
  }, Math.max(10, t.expires_in - 60) * 1000)
}

/** Resolve the auth mode; in OIDC mode finish a callback or start sign-in. Returns once a token is held. */
export async function initAuth(): Promise<AuthConfig> {
  config = await (await fetch('/api/auth/config')).json()
  if (config.mode !== 'oidc') return config
  discovery = await (await fetch(`${config.issuer}/.well-known/openid-configuration`)).json()
  const url = new URL(window.location.href)
  const code = url.searchParams.get('code')
  const pending = JSON.parse(sessionStorage.getItem(PENDING) || 'null') as { verifier: string; state: string; returnTo: string } | null
  if (code && pending) {
    sessionStorage.removeItem(PENDING)
    if (url.searchParams.get('state') !== pending.state) throw new Error('sign-in state mismatch')
    schedule(await tokenRequest({ grant_type: 'authorization_code', code, redirect_uri: redirectUri(), code_verifier: pending.verifier }))
    window.history.replaceState(null, '', pending.returnTo || '/')
    return config
  }
  return login()
}

export function bearer(): string | null {
  return tokens?.access_token ?? null
}

export function authMode(): AuthConfig['mode'] {
  return config.mode
}

/** Called when the API answers 401: the token expired or was revoked. */
export function reauthenticate(): void {
  if (config.mode === 'oidc') void login()
}

export function logout(): void {
  const idToken = tokens?.id_token
  tokens = null
  window.clearTimeout(refreshTimer)
  if (config.mode === 'oidc' && discovery?.end_session_endpoint) {
    const params = new URLSearchParams({ client_id: config.client_id!, post_logout_redirect_uri: redirectUri() })
    if (idToken) params.set('id_token_hint', idToken)
    window.location.assign(`${discovery.end_session_endpoint}?${params}`)
  }
}

/** A demonstration build: development sign-in with synthetic records. Demo-only text and helpers show only here. */
export const isDemo = () => authMode() === 'dev'
