// === STAGE 21 MULTI COMPARE TRANSPORT ===
import type {
  CalculatePayload,
  ItemSummary,
} from './types'
import {
  ALL_EQUIPMENT_SLOTS,
  type EquipmentSlotState,
} from './equipmentSlots'
import type { WebBuildSnapshot } from './buildProject'

const GID = {
  baseLv: 11,
  jobLv: 12,
  job: 19,
  mhp: 200,
  msp: 202,
  str: 32,
  agi: 33,
  vit: 34,
  int: 35,
  dex: 36,
  luk: 37,
  pow: 255,
  sta: 256,
  wis: 257,
  spl: 258,
  con: 259,
  crt: 260,
  runeSlots: 263,
  runeRefine: 264,
} as const

export function snapshotToCalculatePayload(
  snapshot: WebBuildSnapshot,
): CalculatePayload | null {
  if (snapshot.character.jobId === null) {
    return null
  }

  const equipment = snapshot.equipment

  const refineInputs = Object.fromEntries(
    ALL_EQUIPMENT_SLOTS.map((definition) => [
      definition.slotId,
      equipment[definition.slotId]?.refine ?? 0,
    ]),
  ) as Record<number, number>

  const slots = ALL_EQUIPMENT_SLOTS.flatMap(
    (definition) => {
      const slot = equipment[definition.slotId]
      if (!slot) return []

      const cards = slot.cards.map((card) =>
        card.trim()
      )
      const note = slot.note.trim()
      const hasSupplement =
        cards.some(Boolean) || Boolean(note)

      if (!slot.item && !hasSupplement) {
        return []
      }

      return [
        {
          part_name: definition.label,
          slot_id: definition.slotId,
          equip_name: slot.item
            ? slot.item.name || slot.item.base_name
            : '',
          grade: slot.grade,
          cards,
          note,
        },
      ]
    },
  )

  return {
    get_values: {
      [GID.baseLv]: snapshot.character.baseLv,
      [GID.jobLv]: snapshot.character.jobLv,
      [GID.job]: snapshot.character.jobId,
      [GID.str]: snapshot.character.str,
      [GID.agi]: snapshot.character.agi,
      [GID.vit]: snapshot.character.vit,
      [GID.int]: snapshot.character.intStat,
      [GID.dex]: snapshot.character.dex,
      [GID.luk]: snapshot.character.luk,
      [GID.pow]: snapshot.advanced.pow,
      [GID.sta]: snapshot.advanced.sta,
      [GID.wis]: snapshot.advanced.wis,
      [GID.spl]: snapshot.advanced.spl,
      [GID.con]: snapshot.advanced.con,
      [GID.crt]: snapshot.advanced.crt,
      [GID.mhp]: snapshot.status.mhpInput,
      [GID.msp]: snapshot.status.mspInput,
      [GID.runeSlots]:
        equipment[100]?.grade ?? 0,
      [GID.runeRefine]:
        equipment[100]?.refine ?? 0,
    },
    refine_inputs: refineInputs,
    slots,
    enabled_skill_names:
      snapshot.advanced.enabledSkillNames,
    hide_unrecognized: false,
    hide_physical: false,
    hide_magical: false,
    show_source: true,
    sort_mode: '來源順序',
    context_variables: {
      target_element:
        snapshot.advanced.targetElement,
      target_race:
        snapshot.advanced.targetRace,
      target_size:
        snapshot.advanced.targetSize,
      target_class:
        snapshot.advanced.targetClass,
    },
    enabled_skill_levels:
      snapshot.advanced.enabledSkillLevels,
  }
}

export function cloneEquipmentSlot(
  slot: EquipmentSlotState<ItemSummary>,
): EquipmentSlotState<ItemSummary> {
  return {
    item: slot.item
      ? {
          ...slot.item,
        }
      : null,
    refine: slot.refine,
    grade: slot.grade,
    cards: [
      slot.cards[0],
      slot.cards[1],
      slot.cards[2],
      slot.cards[3],
    ],
    note: slot.note,
  }
}
