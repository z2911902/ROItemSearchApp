// === STAGE 21.6 CURRENT DRAFT + LAST BUILD NAME ONLY ===
import type { WebBuildSnapshot } from './buildProject'
import type { EffectDisplayFilters } from './effectDisplay'

const CURRENT_DRAFT_KEY =
  'roitemsearchapp:web:current-draft:v1'
const LAST_BUILD_NAME_KEY =
  'roitemsearchapp:web:last-build-name:v1'

export interface BrowserDraftRecord {
  version: 1
  savedAt: string
  snapshot: WebBuildSnapshot
  effectDisplayFilters: EffectDisplayFilters
}

function readJson(key: string): unknown {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const raw = window.localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch (error) {
    console.warn(
      `Browser storage read failed: ${key}`,
      error,
    )
    return null
  }
}

function writeJson(
  key: string,
  value: unknown,
): boolean {
  if (typeof window === 'undefined') {
    return false
  }

  try {
    window.localStorage.setItem(
      key,
      JSON.stringify(value),
    )
    return true
  } catch (error) {
    console.warn(
      `Browser storage write failed: ${key}`,
      error,
    )
    return false
  }
}

function removeKey(key: string): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.removeItem(key)
  } catch (error) {
    console.warn(
      `Browser storage remove failed: ${key}`,
      error,
    )
  }
}

function isObject(
  value: unknown,
): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value)
  )
}

export function loadBrowserDraft():
  BrowserDraftRecord | null {
  const row = readJson(CURRENT_DRAFT_KEY)

  if (
    !isObject(row) ||
    row.version !== 1 ||
    typeof row.savedAt !== 'string' ||
    !isObject(row.snapshot)
  ) {
    return null
  }

  return row as unknown as BrowserDraftRecord
}

export function saveBrowserDraft(
  snapshot: WebBuildSnapshot,
  effectDisplayFilters: EffectDisplayFilters,
): BrowserDraftRecord | null {
  const record: BrowserDraftRecord = {
    version: 1,
    savedAt: new Date().toISOString(),
    snapshot,
    effectDisplayFilters,
  }

  return writeJson(CURRENT_DRAFT_KEY, record)
    ? record
    : null
}

export function clearBrowserDraft(): void {
  removeKey(CURRENT_DRAFT_KEY)
}

export function loadLastBuildName(
  fallback = '我的配裝',
): string {
  if (typeof window === 'undefined') {
    return fallback
  }

  try {
    const stored =
      window.localStorage.getItem(
        LAST_BUILD_NAME_KEY,
      )
    const normalized =
      String(stored ?? '').trim()

    return normalized || fallback
  } catch {
    return fallback
  }
}

export function saveLastBuildName(
  name: string,
): boolean {
  const normalized =
    String(name ?? '').trim()

  // Do not destroy the last meaningful name while the user temporarily
  // clears/retypes the input.
  if (!normalized) {
    return false
  }

  if (typeof window === 'undefined') {
    return false
  }

  try {
    window.localStorage.setItem(
      LAST_BUILD_NAME_KEY,
      normalized,
    )
    return true
  } catch (error) {
    console.warn(
      'Last build name write failed',
      error,
    )
    return false
  }
}
