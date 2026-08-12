// === STAGE 21.6 SHARED BROWSER BUILD STORAGE ===
import type { WebBuildProject } from './buildProject'

export const BROWSER_BUILD_STORAGE_KEY =
  'roitemsearchapp.webBuilds.v1'
export const MAX_BROWSER_BUILDS = 20
export const BROWSER_BUILDS_CHANGED_EVENT =
  'roitemsearchapp:browser-builds-changed'

export interface BrowserStoredBuild {
  id: string
  name: string
  saved_at: string
  project: WebBuildProject
}

function normalizeStoredBuild(value: unknown): BrowserStoredBuild | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const row = value as Partial<BrowserStoredBuild>

  if (
    typeof row.id !== 'string' ||
    typeof row.name !== 'string' ||
    typeof row.saved_at !== 'string' ||
    !row.project ||
    typeof row.project !== 'object'
  ) {
    return null
  }

  return {
    id: row.id,
    name: row.name,
    saved_at: row.saved_at,
    project: row.project,
  }
}

export function readBrowserBuilds(): BrowserStoredBuild[] {
  if (typeof window === 'undefined') return []

  try {
    const raw = window.localStorage.getItem(BROWSER_BUILD_STORAGE_KEY)
    if (!raw) return []

    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed
      .map(normalizeStoredBuild)
      .filter((row): row is BrowserStoredBuild => row !== null)
      .slice(0, MAX_BROWSER_BUILDS)
  } catch {
    return []
  }
}

export function writeBrowserBuilds(
  builds: BrowserStoredBuild[],
): BrowserStoredBuild[] {
  const next = builds.slice(0, MAX_BROWSER_BUILDS)

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(
      BROWSER_BUILD_STORAGE_KEY,
      JSON.stringify(next),
    )

    // Native storage event is not emitted in the same tab.
    window.dispatchEvent(
      new CustomEvent(BROWSER_BUILDS_CHANGED_EVENT),
    )
  }

  return next
}

export function subscribeBrowserBuilds(
  listener: () => void,
): () => void {
  if (typeof window === 'undefined') return () => {}

  const customListener = () => listener()
  const storageListener = (event: StorageEvent) => {
    if (event.key === BROWSER_BUILD_STORAGE_KEY) {
      listener()
    }
  }

  window.addEventListener(
    BROWSER_BUILDS_CHANGED_EVENT,
    customListener,
  )
  window.addEventListener('storage', storageListener)

  return () => {
    window.removeEventListener(
      BROWSER_BUILDS_CHANGED_EVENT,
      customListener,
    )
    window.removeEventListener('storage', storageListener)
  }
}
