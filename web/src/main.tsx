import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@blueprintjs/core/lib/css/blueprint.css'
import '@mantine/core/styles.css'
import 'maplibre-gl/dist/maplibre-gl.css'
// Type: Public Sans for everything, IBM Plex Mono for references and identifiers, Noto for the Indian
// scripts names arrive in (each loads only when its characters appear on screen).
import '@fontsource-variable/public-sans/index.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/noto-sans-devanagari/400.css'
import '@fontsource/noto-sans-devanagari/600.css'
import '@fontsource/noto-sans-gujarati/400.css'
import '@fontsource/noto-sans-gurmukhi/400.css'
import '@fontsource/noto-sans-bengali/400.css'
import '@fontsource/noto-sans-tamil/400.css'
import '@fontsource/noto-sans-telugu/400.css'
import '@fontsource/noto-sans-kannada/400.css'
import '@fontsource/noto-sans-malayalam/400.css'
import '@fontsource/noto-sans-arabic/400.css'
import './styles/workspace.css'
import App from './App.tsx'
import { initAuth } from './auth'

const root = createRoot(document.getElementById('root')!)
initAuth()
  .then(() => root.render(<StrictMode><App /></StrictMode>))
  .catch((e) => root.render(<div className="app-loading" role="alert"><h2>Sign-in failed</h2><p>{String(e?.message || e)}. Reload the page to try again.</p></div>))
