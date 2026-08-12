// === STAGE 15 WEB/DESKTOP BUILD PROJECT FORMAT ===
import { getBuffEntries, getDamageSkills, searchItems } from './api'
import {
  ALL_EQUIPMENT_SLOTS,
  DEFAULT_GRADE_OPTIONS,
  createEmptyEquipmentSlotState,
  type EquipmentSlotState,
} from './equipmentSlots'
import type {
  AdvancedCharacterState,
  BuffListEntry,
  DamageState,
  ItemSummary,
  JobSummary,
  StatusSettingsState,
} from './types'

export const WEB_BUILD_FORMAT = 'ROItemSearchApp-WebBuild'
export const WEB_BUILD_VERSION = 1

export interface CharacterBuildState {
  jobId: number | null
  baseLv: number
  jobLv: number
  str: number
  agi: number
  vit: number
  intStat: number
  dex: number
  luk: number
}

export interface WebBuildSnapshot {
  character: CharacterBuildState
  advanced: AdvancedCharacterState
  equipment: Record<number, EquipmentSlotState<ItemSummary>>
  damage: DamageState
  status: StatusSettingsState
}

export interface WebBuildProject {
  format: typeof WEB_BUILD_FORMAT
  version: typeof WEB_BUILD_VERSION
  saved_at: string
  name: string
  state: WebBuildSnapshot
}

export interface BuildImportResult {
  project: WebBuildProject
  warnings: string[]
  source: 'web' | 'desktop'
}

const STAT_KEYS = [
  'BaseLv',
  'JobLv',
  'STR',
  'AGI',
  'VIT',
  'INT',
  'DEX',
  'LUK',
  'POW',
  'STA',
  'WIS',
  'SPL',
  'CON',
  'CRT',
] as const

function finiteInt(value: unknown, fallback = 0): number {
  const parsed = Number.parseInt(String(value ?? ''), 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function text(value: unknown): string {
  return String(value ?? '').trim()
}

function normalizeCards(value: unknown): [string, string, string, string] {
  const source = Array.isArray(value) ? value : []
  return [0, 1, 2, 3].map((index) => text(source[index])) as [
    string,
    string,
    string,
    string,
  ]
}

function normalizeItem(value: unknown): ItemSummary | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  const row = value as Partial<ItemSummary>
  const name = text(row.name)
  const baseName = text(row.base_name)
  if (!name && !baseName) {
    return null
  }
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

function normalizeAdvanced(value: unknown): AdvancedCharacterState {
  const row =
    value && typeof value === 'object'
      ? (value as Partial<AdvancedCharacterState>)
      : {}

  const rawLevels =
    row.enabledSkillLevels && typeof row.enabledSkillLevels === 'object'
      ? row.enabledSkillLevels
      : {}

  return {
    pow: finiteInt(row.pow, 0),
    sta: finiteInt(row.sta, 0),
    wis: finiteInt(row.wis, 0),
    spl: finiteInt(row.spl, 0),
    con: finiteInt(row.con, 0),
    crt: finiteInt(row.crt, 0),
    enabledSkillNames: Array.isArray(row.enabledSkillNames)
      ? row.enabledSkillNames.map(String).filter(Boolean)
      : [],
    enabledSkillLevels: Object.fromEntries(
      Object.entries(rawLevels)
        .map(([skillId, level]) => [
          finiteInt(skillId, 0),
          finiteInt(level, 0),
        ])
        .filter(([skillId]) => Number(skillId) > 0),
    ) as Record<number, number>,
    targetElement: finiteInt(row.targetElement, 0),
    targetRace: finiteInt(row.targetRace, 0),
    targetSize: finiteInt(row.targetSize, 1),
    targetClass: finiteInt(row.targetClass, 0),
  }
}

function normalizeDamage(value: unknown): DamageState {
  const row = value && typeof value === 'object' ? value as Partial<DamageState> : {}
  const monster = row.monster && typeof row.monster === 'object'
    ? row.monster as Partial<DamageState['monster']>
    : {}
  const special =
    row.special && typeof row.special === 'object'
      ? row.special as Partial<DamageState['special']>
      : {}

  return {
    skillId: row.skillId === null || row.skillId === undefined ? null : finiteInt(row.skillId, 0),
    skillLevel: finiteInt(row.skillLevel, 1),
    attackElement: row.attackElement === null || row.attackElement === undefined
      ? null
      : finiteInt(row.attackElement, 0),
    formulaOverride: text(row.formulaOverride),
    special: {
      wanzih: Boolean(special.wanzih),
      poisonWeak: Boolean(special.poisonWeak),
      magicPoison: Boolean(special.magicPoison),
      attributeSeal: Boolean(special.attributeSeal),
      sneakAttack: Boolean(special.sneakAttack),
      sporeAttack: Boolean(special.sporeAttack),
      darkCrow: Boolean(special.darkCrow),
      rushAttack: Boolean(special.rushAttack),
      oleumAttack: Boolean(special.oleumAttack),
      lexAeterna: Boolean(special.lexAeterna),
      totalSrl: 0,
    },
    mhp: finiteInt(row.mhp, 0),
    msp: finiteInt(row.msp, 0),
    mhpNow: finiteInt(row.mhpNow, 0),
    mspNow: finiteInt(row.mspNow, 0),
    monster: {
      size: finiteInt(monster.size, 1),
      element: finiteInt(monster.element, 0),
      elementLv: finiteInt(monster.elementLv, 1),
      race: finiteInt(monster.race, 0),
      classId: finiteInt(monster.classId, 0),
      def: finiteInt(monster.def, 0),
      defc: finiteInt(monster.defc, 0),
      res: finiteInt(monster.res, 0),
      mdef: finiteInt(monster.mdef, 0),
      mdefc: finiteInt(monster.mdefc, 0),
      mres: finiteInt(monster.mres, 0),
      damageMultiplierPercent: Number(monster.damageMultiplierPercent ?? 100),
      betelgeuseReductionPercent: Number(monster.betelgeuseReductionPercent ?? 0),
    },
  }
}

function normalizeStatus(value: unknown): StatusSettingsState {
  const row =
    value && typeof value === 'object'
      ? value as Partial<StatusSettingsState>
      : {}

  return {
    mhpInput: finiteInt(row.mhpInput, 0),
    mspInput: finiteInt(row.mspInput, 0),
    useLogoutHpsp: Boolean(row.useLogoutHpsp),
    hpPercent: Math.max(
      0,
      Math.min(100, finiteInt(row.hpPercent, 100)),
    ),
    spPercent: Math.max(
      0,
      Math.min(100, finiteInt(row.spPercent, 100)),
    ),
  }
}

export function normalizeSnapshot(value: unknown): WebBuildSnapshot {
  const row =
    value && typeof value === 'object'
      ? (value as Partial<WebBuildSnapshot>)
      : {}

  const character =
    row.character && typeof row.character === 'object'
      ? row.character
      : ({} as Partial<CharacterBuildState>)

  const rawEquipment =
    row.equipment && typeof row.equipment === 'object'
      ? row.equipment
      : {}

  const equipment = Object.fromEntries(
    ALL_EQUIPMENT_SLOTS.map((definition) => {
      const raw =
        (rawEquipment as Record<string, unknown>)[String(definition.slotId)] ??
        (rawEquipment as Record<number, unknown>)[definition.slotId]

      const source =
        raw && typeof raw === 'object'
          ? (raw as Partial<EquipmentSlotState<ItemSummary>>)
          : {}

      return [
        definition.slotId,
        {
          item: normalizeItem(source.item),
          refine: finiteInt(source.refine, 0),
          grade: finiteInt(source.grade, 0),
          cards: normalizeCards(source.cards),
          note: text(source.note),
        },
      ]
    }),
  ) as Record<number, EquipmentSlotState<ItemSummary>>

  return {
    character: {
      jobId:
        character.jobId === null || character.jobId === undefined
          ? null
          : finiteInt(character.jobId, 0),
      baseLv: finiteInt(character.baseLv, 260),
      jobLv: finiteInt(character.jobLv, 60),
      str: finiteInt(character.str, 1),
      agi: finiteInt(character.agi, 1),
      vit: finiteInt(character.vit, 1),
      intStat: finiteInt(character.intStat, 1),
      dex: finiteInt(character.dex, 1),
      luk: finiteInt(character.luk, 1),
    },
    advanced: normalizeAdvanced(row.advanced),
    equipment,
    damage: normalizeDamage(row.damage),
    status: normalizeStatus(
      row.status ?? (
        row.damage && typeof row.damage === 'object'
          ? {
              mhpInput: (row.damage as Partial<DamageState>).mhp ?? 0,
              mspInput: (row.damage as Partial<DamageState>).msp ?? 0,
              useLogoutHpsp: false,
              hpPercent: 100,
              spPercent: 100,
            }
          : undefined
      ),
    ),
  }
}

export function createWebBuildProject(
  snapshot: WebBuildSnapshot,
  name = '未命名配裝',
): WebBuildProject {
  return {
    format: WEB_BUILD_FORMAT,
    version: WEB_BUILD_VERSION,
    saved_at: new Date().toISOString(),
    name: name.trim() || '未命名配裝',
    state: normalizeSnapshot(snapshot),
  }
}

export function isWebBuildProject(value: unknown): value is WebBuildProject {
  if (!value || typeof value !== 'object') {
    return false
  }
  const row = value as Partial<WebBuildProject>
  return row.format === WEB_BUILD_FORMAT && row.version === WEB_BUILD_VERSION
}

function gradeLabel(slotId: number, grade: number): string {
  const definition = ALL_EQUIPMENT_SLOTS.find((row) => row.slotId === slotId)
  const options = definition?.gradeOptions ?? DEFAULT_GRADE_OPTIONS
  return options.find((option) => option.value === grade)?.label ?? String(grade)
}

function gradeIndex(slotId: number, value: unknown): number {
  const definition = ALL_EQUIPMENT_SLOTS.find((row) => row.slotId === slotId)
  const options = definition?.gradeOptions ?? DEFAULT_GRADE_OPTIONS
  const raw = text(value)

  const byLabel = options.find((option) => option.label === raw)
  if (byLabel) {
    return byLabel.value
  }

  const numeric = finiteInt(raw, 0)
  return options.some((option) => option.value === numeric) ? numeric : 0
}

function buffIds(value: unknown): Set<string> {
  if (value === null || value === undefined) {
    return new Set()
  }

  if (Array.isArray(value)) {
    return new Set(
      value
        .flatMap((item) => Array.from(buffIds(item)))
        .map(String)
        .filter(Boolean),
    )
  }

  if (typeof value === 'number') {
    return new Set([String(Math.trunc(value))])
  }

  return new Set(
    String(value)
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  )
}

function exclusiveGroups(value: unknown): string[] {
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((group) => group.trim())
      .filter(Boolean)
  }
  if (Array.isArray(value)) {
    return value.map(String).map((group) => group.trim()).filter(Boolean)
  }
  return []
}

function namesFromDesktopBuff(
  rawBuff: unknown,
  entries: BuffListEntry[],
): string[] {
  const targets = buffIds(rawBuff)
  if (!targets.size) {
    return []
  }

  const usedGroups = new Set<string>()
  const names: string[] = []

  for (const entry of entries) {
    const entryIds = buffIds(entry.buff)
    if (![...entryIds].some((id) => targets.has(id))) {
      continue
    }

    const groups = exclusiveGroups(entry.exclusive)
    if (groups.some((group) => usedGroups.has(group))) {
      continue
    }

    names.push(entry.name)
    groups.forEach((group) => usedGroups.add(group))
  }

  return names
}

async function resolveLegacyItem(name: string): Promise<ItemSummary | null> {
  const normalized = name.trim()
  if (!normalized) {
    return null
  }

  try {
    const response = await searchItems(normalized)
    const exact = response.items.find(
      (item) =>
        [item.name, item.base_name, item.kr_name]
          .map((value) => value.trim())
          .includes(normalized),
    )
    if (exact) {
      return exact
    }
  } catch {
    // Keep legacy display name as a fallback below.
  }

  // Core equipment lookup is name-based, so keep the legacy name even when
  // the current item index cannot resolve an ID.
  return {
    item_id: 0,
    name: normalized,
    base_name: normalized,
    kr_name: '',
    slot: 0,
    is_equipment: true,
  }
}

function resolveLegacyJob(value: unknown, jobs: JobSummary[]): number | null {
  const raw = text(value)
  if (!raw) {
    return null
  }

  const numeric = Number.parseInt(raw, 10)
  if (Number.isFinite(numeric)) {
    const direct = jobs.find((job) => job.job_id === numeric)
    if (direct && typeof direct.job_id === 'number') {
      return direct.job_id
    }
  }

  const matched = jobs.find((job) =>
    [
      job.name,
      job.code,
      job.job_name,
      job.job_name_online,
      String(job.job_id),
    ].some((candidate) => text(candidate) === raw),
  )

  return matched && typeof matched.job_id === 'number'
    ? matched.job_id
    : null
}

export async function desktopJsonToProject(
  desktopData: Record<string, unknown>,
  jobs: JobSummary[],
): Promise<BuildImportResult> {
  if (
    desktopData._web_stage15 &&
    isWebBuildProject(desktopData._web_stage15)
  ) {
    const embedded = desktopData._web_stage15
    return {
      project: {
        ...embedded,
        state: normalizeSnapshot(embedded.state),
      },
      warnings: [],
      source: 'web',
    }
  }

  const warnings: string[] = []
  const buffs = await getBuffEntries('', '')
  const legacyJobId = resolveLegacyJob(desktopData.JOB, jobs)
  const equipment = Object.fromEntries(
    ALL_EQUIPMENT_SLOTS.map((definition) => [
      definition.slotId,
      createEmptyEquipmentSlotState<ItemSummary>(),
    ]),
  ) as Record<number, EquipmentSlotState<ItemSummary>>

  const equipNames = new Map<number, string>()
  for (const definition of ALL_EQUIPMENT_SLOTS) {
    equipNames.set(
      definition.slotId,
      text(desktopData[`${definition.label}_equip`]),
    )
  }

  const resolved = await Promise.all(
    [...equipNames.entries()].map(async ([slotId, name]) => [
      slotId,
      await resolveLegacyItem(name),
    ] as const),
  )

  for (const [slotId, item] of resolved) {
    const definition = ALL_EQUIPMENT_SLOTS.find(
      (row) => row.slotId === slotId,
    )
    if (!definition) {
      continue
    }

    const rawName = equipNames.get(slotId) ?? ''
    if (rawName && item?.item_id === 0) {
      warnings.push(
        `${definition.label}：找不到目前資料庫 Item ID，已保留舊名稱「${rawName}」`,
      )
    }

    equipment[slotId] = {
      item,
      refine: finiteInt(desktopData[definition.label], 0),
      grade: gradeIndex(
        slotId,
        desktopData[`${definition.label}_階級`],
      ),
      cards: [1, 2, 3, 4].map((index) =>
        text(desktopData[`${definition.label}_card${index}`]),
      ) as [string, string, string, string],
      note: text(desktopData[`${definition.label}_note`]),
    }
  }

  let legacySkillId: number | null = null
  const rawLegacySkillLevel =
    desktopData.skill_lv ?? desktopData.skill_level ?? desktopData.Sklv
  let legacySkillLevel =
    rawLegacySkillLevel === undefined || rawLegacySkillLevel === null || text(rawLegacySkillLevel) === ''
      ? 0
      : finiteInt(rawLegacySkillLevel, 0)
  let legacyAttackElement: number | null = null
  const legacySkillName = text(desktopData.skill_name)
  if (legacySkillName) {
    try {
      const response = await getDamageSkills(
        legacyJobId ?? 0,
        legacySkillName,
      )
      const match = response.skills.find((skill) =>
        [skill.name, skill.code, String(skill.skill_id)].includes(legacySkillName),
      ) ?? response.skills[0]
      if (match) {
        legacySkillId = match.skill_id
        legacySkillLevel = legacySkillLevel > 0 ? legacySkillLevel : match.default_level
        legacyAttackElement = match.element
      } else {
        warnings.push(`Desktop skill_name「${legacySkillName}」在目前 skillneme.csv 找不到。`)
      }
    } catch {
      warnings.push(`Desktop skill_name「${legacySkillName}」解析失敗，其他配裝仍已載入。`)
    }
  }

  const project = createWebBuildProject(
    {
      character: {
        jobId: legacyJobId,
        baseLv: finiteInt(desktopData.BaseLv, 260),
        jobLv: finiteInt(desktopData.JobLv, 60),
        str: finiteInt(desktopData.STR, 1),
        agi: finiteInt(desktopData.AGI, 1),
        vit: finiteInt(desktopData.VIT, 1),
        intStat: finiteInt(desktopData.INT, 1),
        dex: finiteInt(desktopData.DEX, 1),
        luk: finiteInt(desktopData.LUK, 1),
      },
      advanced: {
        pow: finiteInt(desktopData.POW, 0),
        sta: finiteInt(desktopData.STA, 0),
        wis: finiteInt(desktopData.WIS, 0),
        spl: finiteInt(desktopData.SPL, 0),
        con: finiteInt(desktopData.CON, 0),
        crt: finiteInt(desktopData.CRT, 0),
        enabledSkillNames: namesFromDesktopBuff(
          desktopData.buff,
          buffs.entries,
        ),
        enabledSkillLevels: {},
        targetElement: finiteInt(desktopData.element, 0),
        targetRace: finiteInt(desktopData.race, 0),
        targetSize: finiteInt(desktopData.size, 1),
        targetClass: finiteInt(desktopData.class, 0),
      },
      equipment,
      damage: {
        skillId: legacySkillId,
        skillLevel: legacySkillLevel > 0 ? legacySkillLevel : 1,
        attackElement: legacyAttackElement,
        formulaOverride: text(desktopData.skill_formula),
        special: {
          wanzih: false,
          poisonWeak: false,
          magicPoison: false,
          attributeSeal: false,
          sneakAttack: false,
          sporeAttack: false,
          darkCrow: false,
          rushAttack: false,
          oleumAttack: false,
          lexAeterna: false,
          totalSrl: 0,
        },
        mhp: finiteInt(desktopData.MHP, 0),
        msp: finiteInt(desktopData.MSP, 0),
        mhpNow: finiteInt(desktopData.MHP_NOW, finiteInt(desktopData.MHP, 0)),
        mspNow: finiteInt(desktopData.MSP_NOW, finiteInt(desktopData.MSP, 0)),
        monster: {
          size: finiteInt(desktopData.size, 1),
          element: finiteInt(desktopData.element, 0),
          elementLv: finiteInt(desktopData.element_lv, 1),
          race: finiteInt(desktopData.race, 0),
          classId: finiteInt(desktopData.class, 0),
          def: finiteInt(desktopData.def, 0),
          defc: finiteInt(desktopData.defc, 0),
          res: finiteInt(desktopData.res, 0),
          mdef: finiteInt(desktopData.mdef, 0),
          mdefc: finiteInt(desktopData.mdefc, 0),
          mres: finiteInt(desktopData.mres, 0),
          damageMultiplierPercent: Number(desktopData.damage_reduction ?? 100),
          betelgeuseReductionPercent: Number(desktopData.betelgeuse_reduction ?? 0),
        },
      },
      status: {
        mhpInput: finiteInt(desktopData.MHP, 0),
        mspInput: finiteInt(desktopData.MSP, 0),
        useLogoutHpsp: false,
        hpPercent: 100,
        spPercent: 100,
      },
    },
    'Desktop 匯入',
  )

  return { project, warnings, source: 'desktop' }
}

export async function parseBuildFile(
  raw: string,
  jobs: JobSummary[],
): Promise<BuildImportResult> {
  const parsed = JSON.parse(raw) as unknown

  if (isWebBuildProject(parsed)) {
    return {
      project: {
        ...parsed,
        state: normalizeSnapshot(parsed.state),
      },
      warnings: [],
      source: 'web',
    }
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('JSON 必須是 Web Build 或 Desktop 專案物件')
  }

  return desktopJsonToProject(
    parsed as Record<string, unknown>,
    jobs,
  )
}

export async function projectToDesktopJson(
  project: WebBuildProject,
  jobs: JobSummary[],
): Promise<Record<string, unknown>> {
  const snapshot = normalizeSnapshot(project.state)
  const selectedJob = jobs.find(
    (job) => job.job_id === snapshot.character.jobId,
  )
  const buffEntries = await getBuffEntries('', '')
  const selectedNames = new Set(snapshot.advanced.enabledSkillNames)
  const selectedBuffIds = new Set<string>()
  let selectedDamageSkillName = ''
  if (snapshot.damage.skillId !== null) {
    try {
      const response = await getDamageSkills(
        snapshot.character.jobId ?? 0,
        String(snapshot.damage.skillId),
      )
      selectedDamageSkillName = response.skills.find(
        (skill) => skill.skill_id === snapshot.damage.skillId,
      )?.name ?? ''
    } catch {
      selectedDamageSkillName = ''
    }
  }

  for (const entry of buffEntries.entries) {
    if (!selectedNames.has(entry.name)) {
      continue
    }
    buffIds(entry.buff).forEach((id) => selectedBuffIds.add(id))
  }

  const data: Record<string, unknown> = {
    BaseLv: String(snapshot.character.baseLv),
    JobLv: String(snapshot.character.jobLv),
    JOB: selectedJob?.name ?? String(snapshot.character.jobId ?? ''),
    STR: String(snapshot.character.str),
    AGI: String(snapshot.character.agi),
    VIT: String(snapshot.character.vit),
    INT: String(snapshot.character.intStat),
    DEX: String(snapshot.character.dex),
    LUK: String(snapshot.character.luk),
    POW: String(snapshot.advanced.pow),
    STA: String(snapshot.advanced.sta),
    WIS: String(snapshot.advanced.wis),
    SPL: String(snapshot.advanced.spl),
    CON: String(snapshot.advanced.con),
    CRT: String(snapshot.advanced.crt),
    MHP: String(snapshot.status.mhpInput),
    MSP: String(snapshot.status.mspInput),
    石碑開啟格數: String(snapshot.equipment[100]?.grade ?? 0),
    石碑精煉: String(snapshot.equipment[100]?.refine ?? 0),
    size: snapshot.damage.monster.size,
    element: snapshot.damage.monster.element,
    race: snapshot.damage.monster.race,
    class: snapshot.damage.monster.classId,
    def: String(snapshot.damage.monster.def),
    defc: String(snapshot.damage.monster.defc),
    res: String(snapshot.damage.monster.res),
    mdef: String(snapshot.damage.monster.mdef),
    mdefc: String(snapshot.damage.monster.mdefc),
    mres: String(snapshot.damage.monster.mres),
    element_lv: String(snapshot.damage.monster.elementLv),
    skill_name: selectedDamageSkillName,
    skill_lv: String(snapshot.damage.skillLevel),
    skill_formula: snapshot.damage.formulaOverride,
    damage_reduction: snapshot.damage.monster.damageMultiplierPercent,
    betelgeuse_reduction: snapshot.damage.monster.betelgeuseReductionPercent,
    buff: [...selectedBuffIds].sort((a, b) => {
      const ai = Number.parseInt(a, 10)
      const bi = Number.parseInt(b, 10)
      if (Number.isFinite(ai) && Number.isFinite(bi)) {
        return ai - bi
      }
      return a.localeCompare(b)
    }).join(','),
    _web_stage15: project,
  }

  for (const definition of ALL_EQUIPMENT_SLOTS) {
    const slot =
      snapshot.equipment[definition.slotId] ??
      createEmptyEquipmentSlotState<ItemSummary>()

    data[definition.label] = String(slot.refine)
    data[`${definition.label}_階級`] = gradeLabel(
      definition.slotId,
      slot.grade,
    )
    data[`${definition.label}_equip`] =
      slot.item?.name || slot.item?.base_name || ''
    slot.cards.forEach((card, index) => {
      data[`${definition.label}_card${index + 1}`] = card
    })
    data[`${definition.label}_note`] = slot.note
  }

  return data
}

export function downloadJson(
  data: unknown,
  filename: string,
): void {
  const blob = new Blob(
    [JSON.stringify(data, null, 2)],
    { type: 'application/json;charset=utf-8' },
  )
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(href)
}

export function safeFilename(value: string): string {
  return (
    value
      .trim()
      .replace(/[\\/:*?"<>|]+/g, '_')
      .replace(/\s+/g, ' ')
      .slice(0, 80) || 'ROBuild'
  )
}
