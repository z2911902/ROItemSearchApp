// === STAGE 21.11 PER-SLOT BROWSER STORAGE ===
import type { EquipmentSlotState } from './equipmentSlots'
import type { ItemSummary } from './types'

export const BROWSER_SLOT_STORAGE_KEY =
  'roitemsearchapp.webSlotBuilds.v1'

export const BROWSER_SLOT_BUILDS_CHANGED_EVENT =
  'roitemsearchapp:slot-builds-changed'

export const MAX_BROWSER_SLOT_BUILDS_PER_SLOT = 30

export interface BrowserStoredSlotBuild {
  id: string
  slot_id: number
  slot_key: string
  slot_label: string
  name: string
  saved_at: string
  value: EquipmentSlotState<ItemSummary>
}

function text(value: unknown): string {
  return String(value ?? '').trim()
}

function finiteInt(value: unknown, fallback = 0): number {
  const parsed = Number.parseInt(String(value ?? ''), 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function normalizeItem(value: unknown): ItemSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const row = value as Partial<ItemSummary>
  const name = text(row.name)
  const baseName = text(row.base_name)

  if (!name && !baseName) return null

  return {
    item_id: finiteInt(row.item_id, 0),
    name: name || baseName,
    base_name: baseName || name,
    kr_name: text(row.kr_name),
    slot: finiteInt(row.slot, 0),
    is_equipment: row.is_equipment !== false,
    description_preview: text(row.description_preview),
    equip_type: text(row.equip_type),
    weapon_type:
      row.weapon_type === null || row.weapon_type === undefined
        ? null
        : finiteInt(row.weapon_type, 0),
    blocks_left_hand:
      typeof row.blocks_left_hand === 'boolean'
        ? row.blocks_left_hand
        : undefined,
  }
}

export function cloneEquipmentSlotState(
  value: EquipmentSlotState<ItemSummary>,
): EquipmentSlotState<ItemSummary> {
  return {
    item: value.item ? { ...value.item } : null,
    refine: finiteInt(value.refine, 0),
    grade: finiteInt(value.grade, 0),
    cards: [
      text(value.cards?.[0]),
      text(value.cards?.[1]),
      text(value.cards?.[2]),
      text(value.cards?.[3]),
    ],
    note: String(value.note ?? ''),
  }
}

function normalizeSlotState(
  value: unknown,
): EquipmentSlotState<ItemSummary> {
  const row =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Partial<EquipmentSlotState<ItemSummary>>)
      : {}

  const cards = Array.isArray(row.cards) ? row.cards : []

  return {
    item: normalizeItem(row.item),
    refine: finiteInt(row.refine, 0),
    grade: finiteInt(row.grade, 0),
    cards: [
      text(cards[0]),
      text(cards[1]),
      text(cards[2]),
      text(cards[3]),
    ],
    note: String(row.note ?? ''),
  }
}

function normalizeRecord(value: unknown): BrowserStoredSlotBuild | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const row = value as Partial<BrowserStoredSlotBuild>

  if (
    typeof row.id !== 'string' ||
    typeof row.slot_id !== 'number' ||
    typeof row.name !== 'string' ||
    typeof row.saved_at !== 'string'
  ) {
    return null
  }

  return {
    id: row.id,
    slot_id: row.slot_id,
    slot_key: text(row.slot_key),
    slot_label: text(row.slot_label),
    name: row.name,
    saved_at: row.saved_at,
    value: normalizeSlotState(row.value),
  }
}

export function slotHasData(
  value: EquipmentSlotState<ItemSummary>,
): boolean {
  return Boolean(
    value.item ||
      value.refine !== 0 ||
      value.grade !== 0 ||
      value.cards.some((card) => card.trim()) ||
      value.note.trim(),
  )
}

export function readBrowserSlotBuilds(): BrowserStoredSlotBuild[] {
  if (typeof window === 'undefined') return []

  try {
    const raw = window.localStorage.getItem(BROWSER_SLOT_STORAGE_KEY)
    if (!raw) return []

    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed
      .map(normalizeRecord)
      .filter(
        (row): row is BrowserStoredSlotBuild => row !== null,
      )
  } catch {
    return []
  }
}

export function writeBrowserSlotBuilds(
  builds: BrowserStoredSlotBuild[],
): BrowserStoredSlotBuild[] {
  const counts = new Map<number, number>()

  const next = builds.filter((row) => {
    const count = counts.get(row.slot_id) ?? 0

    if (count >= MAX_BROWSER_SLOT_BUILDS_PER_SLOT) {
      return false
    }

    counts.set(row.slot_id, count + 1)
    return true
  })

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(
      BROWSER_SLOT_STORAGE_KEY,
      JSON.stringify(next),
    )
    window.dispatchEvent(
      new CustomEvent(BROWSER_SLOT_BUILDS_CHANGED_EVENT),
    )
  }

  return next
}

export function subscribeBrowserSlotBuilds(
  listener: () => void,
): () => void {
  if (typeof window === 'undefined') return () => {}

  const customListener = () => listener()
  const storageListener = (event: StorageEvent) => {
    if (event.key === BROWSER_SLOT_STORAGE_KEY) {
      listener()
    }
  }

  window.addEventListener(
    BROWSER_SLOT_BUILDS_CHANGED_EVENT,
    customListener,
  )
  window.addEventListener('storage', storageListener)

  return () => {
    window.removeEventListener(
      BROWSER_SLOT_BUILDS_CHANGED_EVENT,
      customListener,
    )
    window.removeEventListener('storage', storageListener)
  }
}
