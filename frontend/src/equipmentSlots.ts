export interface GradeOption {
  value: number
  label: string
}

export type EquipmentGroupKey =
  | 'equipment'
  | 'shadow'
  | 'costume'
  | 'special'

export interface EquipmentSlotDefinition {
  slotId: number
  label: string
  key: string
  group: EquipmentGroupKey
  supportsEquipment?: boolean
  supportsRefine?: boolean
  supportsGrade?: boolean
  supportsCards?: boolean
  supportsNote?: boolean
  supportsTools?: boolean
  refineLabel?: string
  gradeLabel?: string
  gradeOptions?: readonly GradeOption[]
}

export interface EquipmentSlotState<TItem> {
  item: TItem | null
  refine: number
  grade: number
  cards: [string, string, string, string]
  note: string
}

export function createEmptyEquipmentSlotState<TItem>(): EquipmentSlotState<TItem> {
  return {
    item: null,
    refine: 0,
    grade: 0,
    cards: ['', '', '', ''],
    note: '',
  }
}

export const DEFAULT_GRADE_OPTIONS: readonly GradeOption[] = [
  { value: 0, label: 'N' },
  { value: 1, label: 'D' },
  { value: 2, label: 'C' },
  { value: 3, label: 'B' },
  { value: 4, label: 'A' },
] as const

export const RUNE_OPEN_SLOT_OPTIONS: readonly GradeOption[] = [
  { value: 0, label: '0' },
  { value: 1, label: '1' },
  { value: 2, label: '2' },
  { value: 3, label: '3' },
  { value: 4, label: '4' },
  { value: 5, label: '5' },
  { value: 6, label: '6' },
] as const

export const PET_INTIMACY_OPTIONS: readonly GradeOption[] = [
  { value: 0, label: '非常陌生' },
  { value: 1, label: '稍微陌生' },
  { value: 2, label: '普通' },
  { value: 3, label: '稍微親密' },
  { value: 4, label: '非常親密' },
] as const

export const EQUIPMENT_GROUPS: readonly {
  key: EquipmentGroupKey
  label: string
  description: string
}[] = [
  { key: 'equipment', label: '一般裝備', description: '一般裝備、武器、盾牌、投擲物品與飾品' },
  { key: 'shadow', label: '影子裝備', description: 'Desktop 影子 slot 30～35' },
  { key: 'costume', label: '服飾', description: '服飾頭上 / 頭中 / 頭下 / 斗篷' },
  { key: 'special', label: '特殊', description: '符文石碑、寵物蛋與技能詞條' },
] as const

// Exact Desktop refine_parts mapping.
export const ALL_EQUIPMENT_SLOTS: readonly EquipmentSlotDefinition[] = [
  { key: 'head_upper', label: '頭上', slotId: 10, group: 'equipment' },
  { key: 'head_middle', label: '頭中', slotId: 11, group: 'equipment' },
  { key: 'head_lower', label: '頭下', slotId: 12, group: 'equipment' },
  { key: 'armor', label: '鎧甲', slotId: 2, group: 'equipment' },
  { key: 'right_hand', label: '右手(武器)', slotId: 4, group: 'equipment' },
  {
    key: 'projectile', label: '投擲物品', slotId: 110, group: 'equipment',
    supportsRefine: false, supportsGrade: false, supportsCards: false,
    supportsNote: false, supportsTools: false,
  },
  { key: 'left_hand', label: '左手(盾牌)', slotId: 3, group: 'equipment' },
  { key: 'garment', label: '披肩', slotId: 5, group: 'equipment' },
  { key: 'shoes', label: '鞋子', slotId: 6, group: 'equipment' },
  { key: 'accessory_right', label: '飾品右', slotId: 7, group: 'equipment' },
  { key: 'accessory_left', label: '飾品左', slotId: 8, group: 'equipment' },

  { key: 'shadow_armor', label: '影子鎧甲', slotId: 30, group: 'shadow' },
  { key: 'shadow_glove', label: '影子手套', slotId: 31, group: 'shadow' },
  { key: 'shadow_shield', label: '影子盾牌', slotId: 32, group: 'shadow' },
  { key: 'shadow_shoes', label: '影子鞋子', slotId: 33, group: 'shadow' },
  { key: 'shadow_earring', label: '影子耳環右', slotId: 34, group: 'shadow' },
  { key: 'shadow_pendant', label: '影子墬子左', slotId: 35, group: 'shadow' },

  { key: 'costume_upper', label: '服飾頭上', slotId: 41, group: 'costume' },
  { key: 'costume_middle', label: '服飾頭中', slotId: 42, group: 'costume' },
  { key: 'costume_lower', label: '服飾頭下', slotId: 43, group: 'costume' },
  { key: 'costume_garment', label: '服飾斗篷', slotId: 44, group: 'costume' },

  {
    key: 'rune_monument', label: '符文石碑', slotId: 100, group: 'special',
    supportsCards: false, supportsNote: false, supportsTools: false,
    refineLabel: '石碑精煉', gradeLabel: '開啟格數',
    gradeOptions: RUNE_OPEN_SLOT_OPTIONS,
  },
  {
    key: 'pet_egg', label: '寵物蛋', slotId: 101, group: 'special',
    supportsRefine: false, supportsCards: false, supportsNote: false,
    supportsTools: false, gradeLabel: '親密度',
    gradeOptions: PET_INTIMACY_OPTIONS,
  },
  {
    key: 'skill_note', label: '技能', slotId: 102, group: 'special',
    supportsEquipment: false, supportsRefine: false, supportsGrade: false,
    supportsCards: false, supportsNote: true, supportsTools: false,
  },
] as const

export function supports(
  definition: EquipmentSlotDefinition,
  capability:
    | 'supportsEquipment'
    | 'supportsRefine'
    | 'supportsGrade'
    | 'supportsCards'
    | 'supportsNote'
    | 'supportsTools',
): boolean {
  return definition[capability] !== false
}
