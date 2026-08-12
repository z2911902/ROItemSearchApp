// === STAGE 21.19 DAMAGE / MONSTER DISPLAY HELPERS ===
import type {
  DamageResult,
  MonsterDamageState,
} from './types'

const ELEMENT_LABELS: Record<number, string> = {
  0: '無屬性',
  1: '水屬性',
  2: '地屬性',
  3: '火屬性',
  4: '風屬性',
  5: '毒屬性',
  6: '聖屬性',
  7: '暗屬性',
  8: '念屬性',
  9: '不死屬性',
  10: '全屬性',
  999: '（不使用）',
}

const RACE_LABELS: Record<number, string> = {
  0: '無形',
  1: '不死',
  2: '動物',
  3: '植物',
  4: '昆蟲',
  5: '魚貝',
  6: '惡魔',
  7: '人形',
  8: '天使',
  9: '龍族',
  10: '玩家（人類）',
  11: '玩家（貓族）',
  9999: '全種族',
}

const SIZE_LABELS: Record<number, string> = {
  0: '小型',
  1: '中型',
  2: '大型',
}

const CLASS_LABELS: Record<number, string> = {
  0: '一般',
  1: '首領',
  2: '監護人',
}

function labelFor(
  map: Record<number, string>,
  value: number,
  fallbackPrefix: string,
): string {
  return map[value] ?? `${fallbackPrefix}${value}`
}

export function elementLabel(value: number): string {
  return labelFor(ELEMENT_LABELS, value, '屬性')
}

export function raceLabel(value: number): string {
  return labelFor(RACE_LABELS, value, '種族')
}

export function sizeLabel(value: number): string {
  return labelFor(SIZE_LABELS, value, '體型')
}

export function classLabel(value: number): string {
  return labelFor(CLASS_LABELS, value, '階級')
}

export function monsterTargetText(
  monster: Pick<
    MonsterDamageState,
    'size' | 'race' | 'element' | 'elementLv' | 'classId'
  >,
): string {
  return [
    sizeLabel(monster.size),
    raceLabel(monster.race),
    `${elementLabel(monster.element)} Lv.${monster.elementLv}`,
    classLabel(monster.classId),
  ].join(' / ')
}

export function attackElementText(value: number): string {
  return `${elementLabel(value)} (${value})`
}

function breakdownValue(
  result: DamageResult,
  keys: string[],
): number | null {
  const rows = result.breakdown?.rows ?? []
  const row = rows.find((entry) => keys.includes(entry.key))
  return row && Number.isFinite(row.value) ? row.value : null
}

export function defenseAfterDamagePercents(
  result: DamageResult | null,
): {
  defenseLabel: string
  defensePercent: number | null
  traitLabel: string
  traitPercent: number | null
} {
  const empty = {
    defenseLabel: '魔物最終防禦後傷害',
    defensePercent: null,
    traitLabel: '特性防禦後傷害',
    traitPercent: null,
  }

  if (!result || result.skill.attack_type === 'shield') {
    return empty
  }

  const magic = result.skill.attack_type === 'magic'
  const defenseFromBreakdown = breakdownValue(
    result,
    magic
      ? ['magic_after_def_damage']
      : ['physical_after_def_damage'],
  )
  const traitFromBreakdown = breakdownValue(
    result,
    magic
      ? ['magic_after_res_damage']
      : ['physical_after_res_damage'],
  )

  return {
    defenseLabel: empty.defenseLabel,
    defensePercent:
      defenseFromBreakdown ??
      (magic
        ? result.base.mdef_multiplier
        : result.base.def_multiplier) * 100,
    traitLabel: empty.traitLabel,
    traitPercent:
      traitFromBreakdown ??
      (magic
        ? result.base.mres_multiplier
        : result.base.res_multiplier) * 100,
  }
}
