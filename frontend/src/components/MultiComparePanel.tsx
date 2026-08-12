// === STAGE 21.19 MONSTER-AWARE COMPARE DISPLAY ===
import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  calculateStatus,
  calculateStatusDamage,
  getEquipmentItemMeta,
  parseNote,
} from '../api'
import {
  normalizeSnapshot,
  type WebBuildSnapshot,
} from '../buildProject'
import { snapshotToCalculatePayload } from '../compareBuild'
import {
  readBrowserBuilds,
  subscribeBrowserBuilds,
  type BrowserStoredBuild,
} from '../browserBuildStorage'
import {
  isEffectTextHidden,
  type EffectDisplayFilters,
} from '../effectDisplay'
import {
  attackElementText,
  monsterTargetText,
} from '../damageDisplay'
import {
  ALL_EQUIPMENT_SLOTS,
  DEFAULT_GRADE_OPTIONS,
  createEmptyEquipmentSlotState,
  supports,
} from '../equipmentSlots'
import type {
  CalculateResponse,
  CharacterStatusResult,
  DamageResult,
  ItemSummary,
  JobSummary,
} from '../types'
import ToggleButton from './ToggleButton'

interface CompareBundle {
  effect: CalculateResponse
  status: CharacterStatusResult
  damage: DamageResult | null
}

interface FrozenCompareEntry {
  id: string
  name: string
  snapshot: WebBuildSnapshot
  bundle: CompareBundle | null
  loading: boolean
  error: string
}

interface CompareColumn {
  id: string
  name: string
  snapshot: WebBuildSnapshot
  bundle: CompareBundle | null
  loading: boolean
  error: string
  isCurrent: boolean
}

interface CompareCell {
  display: string
  numeric?: number
}

interface ResultRow {
  key: string
  label: string
  alwaysShow?: boolean
}

interface ParsedCompareNote {
  lines: string[]
  loading: boolean
  error: string
}

interface CompareDelta {
  direction: 'up' | 'down'
  amount: string
  percent: string
}

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function itemName(item: ItemSummary | null): string {
  if (!item) return ''
  return (
    item.base_name ||
    item.name ||
    `Item ${item.item_id}`
  )
}

function gradeLabel(
  slotId: number,
  grade: number,
): string {
  const definition = ALL_EQUIPMENT_SLOTS.find(
    (row) => row.slotId === slotId,
  )
  const options =
    definition?.gradeOptions ??
    DEFAULT_GRADE_OPTIONS
  return (
    options.find(
      (option) => option.value === grade,
    )?.label ?? String(grade)
  )
}

function equipmentCell(
  column: CompareColumn,
  slotId: number,
  kind:
    | 'item'
    | 'refine'
    | 'grade'
    | 'card1'
    | 'card2'
    | 'card3'
    | 'card4'
    | 'note',
): string {
  const slot = column.snapshot.equipment[slotId]
  if (!slot) return ''

  if (kind === 'item') {
    return itemName(slot.item)
  }
  if (kind === 'refine') {
    return String(slot.refine)
  }
  if (kind === 'grade') {
    return gradeLabel(slotId, slot.grade)
  }
  if (kind === 'note') {
    return slot.note.trim()
  }

  const cardIndex = Number(kind.slice(-1)) - 1
  return slot.cards[cardIndex]?.trim() ?? ''
}

function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return '—'

  if (Number.isInteger(value)) {
    return value.toLocaleString()
  }

  return value.toLocaleString(undefined, {
    maximumFractionDigits: 3,
  })
}

function columnPendingText(
  column: CompareColumn,
): string {
  if (column.loading) return '計算中…'
  if (column.error) return `錯誤：${column.error}`
  return '—'
}

interface InputRow {
  key: string
  label: string
  value: (
    column: CompareColumn,
    jobs: JobSummary[],
  ) => string
}

function jobLabel(
  column: CompareColumn,
  jobs: JobSummary[],
): string {
  const jobId = column.snapshot.character.jobId
  if (jobId === null) return '—'

  const match = jobs.find(
    (job) => Number(job.job_id) === Number(jobId),
  )
  return match?.name
    ? `${match.name} (${jobId})`
    : String(jobId)
}

function joinedSkillLevels(
  levels: Record<number, number>,
): string {
  const rows = Object.entries(levels)
    .filter(([, level]) => Number(level) > 0)
    .sort(
      ([left], [right]) =>
        Number(left) - Number(right),
    )
    .map(
      ([skillId, level]) =>
        `${skillId}:${level}`,
    )
  return rows.join(', ')
}

const INPUT_ROWS: InputRow[] = [
  {
    key: 'input:job',
    label: '角色｜JOB',
    value: jobLabel,
  },
  {
    key: 'input:baseLv',
    label: '角色｜BaseLv',
    value: (column) =>
      String(column.snapshot.character.baseLv),
  },
  {
    key: 'input:jobLv',
    label: '角色｜JobLv',
    value: (column) =>
      String(column.snapshot.character.jobLv),
  },
  ...(
    [
      ['str', 'STR'],
      ['agi', 'AGI'],
      ['vit', 'VIT'],
      ['intStat', 'INT'],
      ['dex', 'DEX'],
      ['luk', 'LUK'],
    ] as const
  ).map(([key, label]) => ({
    key: `input:${label}`,
    label: `角色｜${label}`,
    value: (column: CompareColumn) =>
      String(column.snapshot.character[key]),
  })),
  ...(
    [
      ['pow', 'POW'],
      ['sta', 'STA'],
      ['wis', 'WIS'],
      ['spl', 'SPL'],
      ['con', 'CON'],
      ['crt', 'CRT'],
    ] as const
  ).map(([key, label]) => ({
    key: `input:${label}`,
    label: `角色｜${label}`,
    value: (column: CompareColumn) =>
      String(column.snapshot.advanced[key]),
  })),
  {
    key: 'input:buffs',
    label: '角色｜料理 / Buff',
    value: (column) =>
      column.snapshot.advanced.enabledSkillNames.join(', '),
  },
  {
    key: 'input:skill-levels',
    label: '角色｜啟用技能等級',
    value: (column) =>
      joinedSkillLevels(
        column.snapshot.advanced.enabledSkillLevels,
      ),
  },
  {
    key: 'input:monster-target',
    label: '魔物｜體型 / 種族 / 屬性 / 階級',
    value: (column) =>
      monsterTargetText(column.snapshot.damage.monster),
  },
  {
    key: 'input:monster-defense',
    label: '魔物｜後 DEF / 前 DEF / RES',
    value: (column) => {
      const row = column.snapshot.damage.monster
      return `${row.def} / ${row.defc} / ${row.res}`
    },
  },
  {
    key: 'input:monster-magic-defense',
    label: '魔物｜後 MDEF / 前 MDEF / MRES',
    value: (column) => {
      const row = column.snapshot.damage.monster
      return `${row.mdef} / ${row.mdefc} / ${row.mres}`
    },
  },
  {
    key: 'input:monster-damage-multiplier',
    label: '魔物｜怪物強制倍率',
    value: (column) =>
      `${column.snapshot.damage.monster.damageMultiplierPercent}%`,
  },
  {
    key: 'input:monster-betelgeuse-reduction',
    label: '魔物｜星座塔減傷',
    value: (column) =>
      `${column.snapshot.damage.monster.betelgeuseReductionPercent}%`,
  },
  {
    key: 'input:damage-skill',
    label: '傷害｜技能 ID / Lv',
    value: (column) =>
      column.snapshot.damage.skillId === null
        ? '未選技能'
        : `${column.snapshot.damage.skillId} / ${column.snapshot.damage.skillLevel}`,
  },
  {
    key: 'input:hpsp',
    label: '狀態｜MHP / MSP 輸入',
    value: (column) =>
      `${column.snapshot.status.mhpInput} / ${column.snapshot.status.mspInput}`,
  },
  {
    key: 'input:hpsp-percent',
    label: '狀態｜HP% / SP%',
    value: (column) =>
      `${column.snapshot.status.hpPercent}% / ${column.snapshot.status.spPercent}%`,
  },
]

function resultMap(
  column: CompareColumn,
): Map<string, CompareCell> {
  const map = new Map<string, CompareCell>()
  const bundle = column.bundle

  if (!bundle) {
    const state = columnPendingText(column)
    ;[
      ['skill:name', ''],
      ['skill:level', ''],
      ['skill:attack-element', ''],
      ['status:hp', state],
      ['status:sp', state],
      ['status:aspd', state],
      ['status:aps', state],
      ['damage:min', state],
      ['damage:max', state],
    ].forEach(([key, display]) => {
      map.set(key, { display })
    })
    return map
  }

  map.set('skill:name', {
    display: bundle.damage?.skill.name ?? '未選技能',
  })
  map.set('skill:level', {
    display:
      bundle.damage?.skill.level !== undefined
        ? String(bundle.damage.skill.level)
        : '—',
    numeric: bundle.damage?.skill.level,
  })

  map.set('skill:attack-element', {
    display:
      bundle.damage?.skill.attack_element !== undefined
        ? attackElementText(bundle.damage.skill.attack_element)
        : '—',
  })

  map.set('status:hp', {
    display:
      `${formatNumber(bundle.status.hpsp.mhp_now)} / ` +
      formatNumber(bundle.status.hpsp.mhp),
    numeric: bundle.status.hpsp.mhp,
  })
  map.set('status:sp', {
    display:
      `${formatNumber(bundle.status.hpsp.msp_now)} / ` +
      formatNumber(bundle.status.hpsp.msp),
    numeric: bundle.status.hpsp.msp,
  })

  map.set('status:aspd', {
    display:
      bundle.status.aspd.supported &&
      bundle.status.aspd.value !== null
        ? bundle.status.aspd.value.toFixed(3)
        : bundle.status.aspd.message || '—',
    numeric:
      bundle.status.aspd.value ?? undefined,
  })
  map.set('status:aps', {
    display:
      bundle.status.aspd.attacks_per_second !== null
        ? bundle.status.aspd.attacks_per_second.toFixed(2)
        : '—',
    numeric:
      bundle.status.aspd.attacks_per_second ??
      undefined,
  })

  map.set('damage:min', {
    display: bundle.damage
      ? formatNumber(bundle.damage.total_damage_min)
      : '—',
    numeric:
      bundle.damage?.total_damage_min,
  })
  map.set('damage:max', {
    display: bundle.damage
      ? formatNumber(bundle.damage.total_damage)
      : '—',
    numeric:
      bundle.damage?.total_damage,
  })

  bundle.effect.effects.forEach((effect) => {
    const key = `effect:${effect.key}:${effect.unit}`
    const labelUnit = effect.unit
      ? ` ${effect.unit}`
      : ''
    map.set(key, {
      display: `${formatNumber(effect.total)}${labelUnit}`,
      numeric: effect.total,
    })
  })

  return map
}

function resultCell(
  column: CompareColumn,
  map: Map<string, CompareCell>,
  key: string,
): CompareCell {
  const existing = map.get(key)
  if (existing) return existing

  if (
    column.bundle &&
    key.startsWith('effect:')
  ) {
    // A valid calculation with no such effect means 0, not "missing data".
    return {
      display: '0',
      numeric: 0,
    }
  }

  return {
    display: columnPendingText(column),
  }
}

function compareDelta(
  value: number | undefined,
  base: number | undefined,
): CompareDelta | null {
  if (
    value === undefined ||
    base === undefined ||
    !Number.isFinite(value) ||
    !Number.isFinite(base)
  ) {
    return null
  }

  const delta = value - base

  if (Math.abs(delta) < 1e-12) {
    return null
  }

  const direction:
    CompareDelta['direction'] =
      delta > 0
        ? 'up'
        : 'down'

  const sign =
    delta > 0
      ? '+'
      : ''

  const percent =
    Math.abs(base) > 1e-12
      ? `${sign}${(
          (delta / base) *
          100
        ).toFixed(2)}%`
      : ''

  return {
    direction,
    amount:
      `${sign}${formatNumber(delta)}`,
    percent,
  }
}

function parsedNoteKey(
  columnId: string,
  slotId: number,
): string {
  return `${columnId}:${slotId}`
}


export default function MultiComparePanel({
  apiReady,
  currentSnapshot,
  currentEffect,
  currentStatus,
  currentDamage,
  jobs,
  displayFilters,
  onDisplayFiltersChange,
}: {
  apiReady: boolean
  currentSnapshot: WebBuildSnapshot
  currentEffect: CalculateResponse | null
  currentStatus: CharacterStatusResult | null
  currentDamage: DamageResult | null
  jobs: JobSummary[]
  displayFilters: EffectDisplayFilters
  onDisplayFiltersChange: (
    filters: EffectDisplayFilters,
  ) => void
}) {
  const [entries, setEntries] =
    useState<FrozenCompareEntry[]>([])
  const [browserBuilds, setBrowserBuilds] =
    useState<BrowserStoredBuild[]>(readBrowserBuilds)
  const [selectedBuildIds, setSelectedBuildIds] =
    useState<string[]>([])
  const [showCurrent, setShowCurrent] =
    useState(true)
  const [onlyDiff, setOnlyDiff] =
    useState(true)
  const [showBaselineMonsterTargetOnly, setShowBaselineMonsterTargetOnly] =
    useState(false)
  const [baselineId, setBaselineId] =
    useState('current')
  const [parsedNotes, setParsedNotes] =
    useState<Record<string, ParsedCompareNote>>({})

  const currentColumn = useMemo<CompareColumn>(
    () => ({
      id: 'current',
      name: '目前設定',
      snapshot: currentSnapshot,
      bundle:
        currentEffect && currentStatus
          ? {
              effect: currentEffect,
              status: currentStatus,
              damage: currentDamage,
            }
          : null,
      loading: false,
      error: '',
      isCurrent: true,
    }),
    [
      currentDamage,
      currentEffect,
      currentSnapshot,
      currentStatus,
    ],
  )

  useEffect(() => {
    const refresh = () => {
      const next = readBrowserBuilds()
      setBrowserBuilds(next)

      const validIds = new Set(
        next.map((row) => row.id),
      )

      setSelectedBuildIds((current) =>
        current.filter((id) => validIds.has(id)),
      )

      setEntries((current) =>
        current.filter((entry) =>
          validIds.has(entry.id),
        ),
      )
    }

    refresh()
    return subscribeBrowserBuilds(refresh)
  }, [])

  const visibleColumns = useMemo<CompareColumn[]>(
    () => [
      ...(showCurrent ? [currentColumn] : []),
      ...entries.map((entry) => ({
        ...entry,
        isCurrent: false,
      })),
    ],
    [currentColumn, entries, showCurrent],
  )

  useEffect(() => {
    if (
      visibleColumns.length > 0 &&
      !visibleColumns.some(
        (column) => column.id === baselineId,
      )
    ) {
      setBaselineId(visibleColumns[0].id)
    }
  }, [baselineId, visibleColumns])

  useEffect(() => {
    const controller =
      new AbortController()

    const timer =
      window.setTimeout(
        () => {
          const requests: Array<{
            key: string
            note: string
            slotId: number
            grade: number
            snapshot: WebBuildSnapshot
          }> = []

          visibleColumns.forEach(
            (column) => {
              ALL_EQUIPMENT_SLOTS.forEach(
                (definition) => {
                  if (
                    !supports(
                      definition,
                      'supportsNote',
                    )
                  ) {
                    return
                  }

                  const slot =
                    column.snapshot
                      .equipment[
                        definition.slotId
                      ]

                  const note =
                    slot?.note.trim() ??
                    ''

                  if (!note) {
                    return
                  }

                  requests.push({
                    key:
                      parsedNoteKey(
                        column.id,
                        definition.slotId,
                      ),
                    note,
                    slotId:
                      definition.slotId,
                    grade:
                      slot?.grade ?? 0,
                    snapshot:
                      column.snapshot,
                  })
                },
              )
            },
          )

          if (
            requests.length === 0
          ) {
            setParsedNotes({})
            return
          }

          const loadingState:
            Record<
              string,
              ParsedCompareNote
            > = {}

          requests.forEach(
            (request) => {
              loadingState[
                request.key
              ] = {
                lines: [],
                loading: true,
                error: '',
              }
            },
          )

          setParsedNotes(
            loadingState,
          )

          if (!apiReady) {
            setParsedNotes(
              Object.fromEntries(
                requests.map(
                  (request) => [
                    request.key,
                    {
                      lines: [],
                      loading: false,
                      error:
                        'Core API 未連線',
                    },
                  ],
                ),
              ),
            )
            return
          }

          void Promise.all(
            requests.map(
              async (request) => {
                const payload =
                  snapshotToCalculatePayload(
                    request.snapshot,
                  )

                if (!payload) {
                  return {
                    key:
                      request.key,
                    value: {
                      lines: [],
                      loading: false,
                      error:
                        '缺少有效 JOB，無法解析中文詞條',
                    } as ParsedCompareNote,
                  }
                }

                try {
                  const response =
                    await parseNote(
                      {
                        note:
                          request.note,
                        slot_id:
                          request.slotId,
                        grade:
                          request.grade,
                        get_values:
                          payload.get_values,
                        refine_inputs:
                          payload.refine_inputs,
                        context_variables:
                          payload
                            .context_variables ??
                          {},
                        enabled_skill_levels:
                          payload
                            .enabled_skill_levels ??
                          {},
                      },
                      controller.signal,
                    )

                  return {
                    key:
                      request.key,
                    value: {
                      lines:
                        response.lines,
                      loading: false,
                      error: '',
                    } as ParsedCompareNote,
                  }
                } catch (
                  noteError
                ) {
                  if (
                    controller.signal
                      .aborted
                  ) {
                    return null
                  }

                  return {
                    key:
                      request.key,
                    value: {
                      lines: [],
                      loading: false,
                      error:
                        readableError(
                          noteError,
                        ),
                    } as ParsedCompareNote,
                  }
                }
              },
            ),
          ).then((rows) => {
            if (
              controller.signal
                .aborted
            ) {
              return
            }

            const next:
              Record<
                string,
                ParsedCompareNote
              > = {}

            rows.forEach((row) => {
              if (!row) {
                return
              }

              next[row.key] =
                row.value
            })

            setParsedNotes(next)
          })
        },
        180,
      )

    return () => {
      window.clearTimeout(
        timer,
      )
      controller.abort()
    }
  }, [
    apiReady,
    visibleColumns,
  ])

  function parsedEquipmentNote(
    column: CompareColumn,
    slotId: number,
  ): string {
    const raw =
      column.snapshot
        .equipment[
          slotId
        ]?.note.trim() ??
      ''

    if (!raw) {
      return ''
    }

    const state =
      parsedNotes[
        parsedNoteKey(
          column.id,
          slotId,
        )
      ]

    if (!state) {
      return '中文解析中…'
    }

    if (state.loading) {
      return '中文解析中…'
    }

    if (state.error) {
      return '中文解析失敗'
    }

    const visibleLines =
      state.lines
        .filter(
          (line) =>
            !isEffectTextHidden(
              line,
              displayFilters,
            ),
        )
        .filter(
          (line) =>
            !/[A-Za-z_][A-Za-z0-9_]*\s*\(/.test(
              line,
            ),
        )

    return (
      visibleLines.join(
        '\n',
      ) ||
      '無可顯示的中文詞條'
    )
  }

  async function normalizeForTwoHand(
    source: WebBuildSnapshot,
  ): Promise<WebBuildSnapshot> {
    const snapshot = normalizeSnapshot(source)
    const rightSlot = snapshot.equipment[4]
    const rightItem = rightSlot?.item

    if (!rightItem) {
      snapshot.damage.special.totalSrl = 0
      return snapshot
    }

    let blocksLeft = rightItem.blocks_left_hand

    if (
      typeof blocksLeft !== 'boolean' &&
      rightItem.item_id > 0
    ) {
      const response = await getEquipmentItemMeta(
        rightItem.item_id,
      )
      blocksLeft =
        response.item.blocks_left_hand === true

      snapshot.equipment[4] = {
        ...rightSlot,
        item: {
          ...rightItem,
          ...response.item,
        },
      }
    }

    if (blocksLeft) {
      snapshot.equipment[3] =
        createEmptyEquipmentSlotState<ItemSummary>()
    }

    snapshot.damage.special.totalSrl = 0

    return snapshot
  }

  async function calculateSnapshot(
    source: WebBuildSnapshot,
  ): Promise<{
    snapshot: WebBuildSnapshot
    bundle: CompareBundle
  }> {
    if (!apiReady) {
      throw new Error('Core API 尚未連線')
    }

    const snapshot =
      await normalizeForTwoHand(source)
    const payload =
      snapshotToCalculatePayload(snapshot)

    if (payload) {
      payload.hide_unrecognized =
        displayFilters.hideRecognition
      payload.hide_physical =
        displayFilters.hidePhysical
      payload.hide_magical =
        displayFilters.hideMagical
    }

    if (!payload) {
      throw new Error('配裝沒有有效 JOB')
    }

    if (snapshot.damage.skillId !== null) {
      const response =
        await calculateStatusDamage(
          payload,
          snapshot.damage,
          snapshot.status,
        )
      return {
        snapshot,
        bundle: {
          effect: response.effect,
          status: response.status,
          damage: response.damage,
        },
      }
    }

    const response = await calculateStatus(
      payload,
      snapshot.status,
    )
    return {
      snapshot,
      bundle: {
        effect: response.effect,
        status: response.status,
        damage: null,
      },
    }
  }

  async function addSnapshot(
    source: WebBuildSnapshot,
    requestedName: string,
    stableId: string,
  ) {
    const id = stableId
    const name =
      requestedName.trim() ||
      '未命名配裝'

    setEntries((current) => [
      ...current.filter((entry) => entry.id !== id),
      {
        id,
        name,
        snapshot: normalizeSnapshot(source),
        bundle: null,
        loading: true,
        error: '',
      },
    ])

    try {
      const calculated =
        await calculateSnapshot(source)

      setEntries((current) =>
        current.map((entry) =>
          entry.id === id
            ? {
                ...entry,
                snapshot: calculated.snapshot,
                bundle: calculated.bundle,
                loading: false,
                error: '',
              }
            : entry,
        ),
      )
    } catch (snapshotError) {
      setEntries((current) =>
        current.map((entry) =>
          entry.id === id
            ? {
                ...entry,
                loading: false,
                error: readableError(snapshotError),
              }
            : entry,
        ),
      )
    }
  }

  async function recalculateEntry(
    entry: FrozenCompareEntry,
  ) {
    setEntries((current) =>
      current.map((row) =>
        row.id === entry.id
          ? {
              ...row,
              loading: true,
              error: '',
            }
          : row,
      ),
    )

    try {
      const calculated =
        await calculateSnapshot(entry.snapshot)

      setEntries((current) =>
        current.map((row) =>
          row.id === entry.id
            ? {
                ...row,
                snapshot: calculated.snapshot,
                bundle: calculated.bundle,
                loading: false,
                error: '',
              }
            : row,
        ),
      )
    } catch (snapshotError) {
      setEntries((current) =>
        current.map((row) =>
          row.id === entry.id
            ? {
                ...row,
                loading: false,
                error: readableError(snapshotError),
              }
            : row,
        ),
      )
    }
  }

  async function toggleBrowserBuild(
    row: BrowserStoredBuild,
  ) {
    const selected =
      selectedBuildIds.includes(row.id)

    if (selected) {
      setSelectedBuildIds((current) =>
        current.filter((id) => id !== row.id),
      )
      setEntries((current) =>
        current.filter((entry) => entry.id !== row.id),
      )
      return
    }

    setSelectedBuildIds((current) => [
      ...current,
      row.id,
    ])

    await addSnapshot(
      row.project.state,
      row.name,
      row.id,
    )
  }

  async function selectAllBrowserBuilds() {
    setSelectedBuildIds(
      browserBuilds.map((row) => row.id),
    )

    for (const row of browserBuilds) {
      if (!entries.some((entry) => entry.id === row.id)) {
        await addSnapshot(
          row.project.state,
          row.name,
          row.id,
        )
      }
    }
  }

  function clearBrowserBuildSelection() {
    setSelectedBuildIds([])
    setEntries([])
    setBaselineId('current')
  }

  const equipmentRows = useMemo(() => {
    const rows: {
      key: string
      label: string
      slotId: number
      kind:
        | 'item'
        | 'refine'
        | 'grade'
        | 'card1'
        | 'card2'
        | 'card3'
        | 'card4'
        | 'note'
    }[] = []

    ALL_EQUIPMENT_SLOTS.forEach((definition) => {
      if (
        supports(
          definition,
          'supportsEquipment',
        )
      ) {
        rows.push({
          key: `${definition.slotId}:item`,
          label: `${definition.label}｜裝備`,
          slotId: definition.slotId,
          kind: 'item',
        })
      }

      if (
        supports(definition, 'supportsRefine')
      ) {
        rows.push({
          key: `${definition.slotId}:refine`,
          label:
            `${definition.label}｜` +
            (definition.refineLabel ?? '精煉'),
          slotId: definition.slotId,
          kind: 'refine',
        })
      }

      if (
        supports(definition, 'supportsGrade')
      ) {
        rows.push({
          key: `${definition.slotId}:grade`,
          label:
            `${definition.label}｜` +
            (definition.gradeLabel ?? 'Grade'),
          slotId: definition.slotId,
          kind: 'grade',
        })
      }

      if (
        supports(definition, 'supportsCards')
      ) {
        ;(['card1', 'card2', 'card3', 'card4'] as const)
          .forEach((kind, index) => {
            rows.push({
              key: `${definition.slotId}:${kind}`,
              label:
                `${definition.label}｜卡片/附魔 ${index + 1}`,
              slotId: definition.slotId,
              kind,
            })
          })
      }

      if (
        supports(definition, 'supportsNote')
      ) {
        rows.push({
          key: `${definition.slotId}:note`,
          label: `${definition.label}｜詞條`,
          slotId: definition.slotId,
          kind: 'note',
        })
      }
    })

    if (!onlyDiff || visibleColumns.length <= 1) {
      return rows
    }

    return rows.filter((row) => {
      const values = visibleColumns.map((column) =>
        equipmentCell(
          column,
          row.slotId,
          row.kind,
        ),
      )
      return new Set(values).size > 1
    })
  }, [onlyDiff, visibleColumns])

  const baselineColumn =
    visibleColumns.find(
      (column) => column.id === baselineId,
    ) ?? visibleColumns[0]

  const inputValue = (
    row: InputRow,
    column: CompareColumn,
  ): string => {
    if (
      showBaselineMonsterTargetOnly &&
      row.key === 'input:monster-target' &&
      baselineColumn
    ) {
      return row.value(baselineColumn, jobs)
    }

    return row.value(column, jobs)
  }

  const inputRows = useMemo(() => {
    if (!onlyDiff || visibleColumns.length <= 1) {
      return INPUT_ROWS
    }

    return INPUT_ROWS.filter((row) => {
      if (
        showBaselineMonsterTargetOnly &&
        row.key === 'input:monster-target'
      ) {
        return true
      }

      const values = visibleColumns.map(
        (column) => {
          if (
            showBaselineMonsterTargetOnly &&
            row.key === 'input:monster-target' &&
            baselineColumn
          ) {
            return row.value(baselineColumn, jobs)
          }
          return row.value(column, jobs)
        },
      )
      return new Set(values).size > 1
    })
  }, [
    baselineColumn,
    jobs,
    onlyDiff,
    showBaselineMonsterTargetOnly,
    visibleColumns,
  ])

  const compareTableMinWidth =
    260 + visibleColumns.length * 340

  const columnResultMaps = useMemo(
    () =>
      new Map(
        visibleColumns.map((column) => [
          column.id,
          resultMap(column),
        ]),
      ),
    [visibleColumns],
  )

  const resultRows = useMemo<ResultRow[]>(() => {
    const rows: ResultRow[] = [
      {
        key: 'skill:name',
        label: '技能名稱',
        alwaysShow: true,
      },
      {
        key: 'skill:level',
        label: '技能等級',
        alwaysShow: true,
      },
      {
        key: 'skill:attack-element',
        label: '技能攻擊屬性',
        alwaysShow: true,
      },
      {
        key: 'damage:max',
        label: '最大總傷害',
        alwaysShow: true,
      },
      {
        key: 'damage:min',
        label: '最小總傷害',
        alwaysShow: true,
      },
      {
        key: 'status:hp',
        label: 'HP（目前 / 最大）',
      },
      {
        key: 'status:sp',
        label: 'SP（目前 / 最大）',
      },
      {
        key: 'status:aspd',
        label: 'ASPD',
      },
      {
        key: 'status:aps',
        label: '每秒攻擊次數',
      },
    ]

    const dynamic = new Map<string, string>()

    visibleColumns.forEach((column) => {
      column.bundle?.effect.effects.forEach(
        (effect) => {
          const label =
            `效果｜${effect.key}` +
            (effect.unit
              ? ` (${effect.unit})`
              : '')

          if (
            isEffectTextHidden(
              label,
              displayFilters,
            )
          ) {
            return
          }

          const key =
            `effect:${effect.key}:${effect.unit}`
          if (!dynamic.has(key)) {
            dynamic.set(key, label)
          }
        },
      )
    })

    ;[...dynamic.entries()]
      .sort((left, right) =>
        left[1].localeCompare(right[1], 'zh-Hant'),
      )
      .forEach(([key, label]) => {
        rows.push({ key, label })
      })

    if (!onlyDiff || visibleColumns.length <= 1) {
      return rows
    }

    return rows.filter((row) => {
      if (row.alwaysShow) return true

      const values = visibleColumns.map(
        (column) =>
          resultCell(
            column,
            columnResultMaps.get(column.id) ??
              new Map<string, CompareCell>(),
            row.key,
          ).display,
      )

      return new Set(values).size > 1
    })
  }, [
    columnResultMaps,
    displayFilters,
    onlyDiff,
    visibleColumns,
  ])

  const baselineMap =
    columnResultMaps.get(baselineId) ??
    new Map<string, CompareCell>()

  return (
    <details className="multi-compare-panel">
      <summary>
        <span>
          多裝備比對
          <small>
            {selectedBuildIds.length} 份瀏覽器配裝
          </small>
        </span>
        <span className="badge">
          Shared Core
        </span>
      </summary>

      <div className="multi-compare-body">
        <section className="compare-browser-source">
          <header>
            <div>
              <strong>比對來源：此瀏覽器存檔</strong>
              <small>
                直接使用上方「配裝存檔 / Desktop JSON 互通」的存檔
              </small>
            </div>

            <span className="badge">
              {selectedBuildIds.length} / {browserBuilds.length} 已選
            </span>
          </header>

          <div className="compare-browser-actions">
            <ToggleButton
              pressed={showCurrent}
              className="toggle-button-compact"
              onPressedChange={setShowCurrent}
            >
              顯示目前設定
            </ToggleButton>

            <button
              className="button button-secondary"
              type="button"
              disabled={
                browserBuilds.length === 0 ||
                !apiReady ||
                selectedBuildIds.length === browserBuilds.length
              }
              onClick={() =>
                void selectAllBrowserBuilds()
              }
            >
              全選存檔
            </button>

            <button
              className="button button-secondary"
              type="button"
              disabled={selectedBuildIds.length === 0}
              onClick={clearBrowserBuildSelection}
            >
              清除選取
            </button>

            <button
              className="button button-secondary"
              type="button"
              disabled={entries.length === 0 || !apiReady}
              onClick={() => {
                entries.forEach((entry) => {
                  void recalculateEntry(entry)
                })
              }}
            >
              全部重算
            </button>
          </div>

          {browserBuilds.length === 0 ? (
            <p className="muted compact-message">
              上方目前沒有「此瀏覽器存檔」。
              請先設定配裝名稱並按「存到此瀏覽器」。
            </p>
          ) : (
            <div className="compare-browser-build-list">
              {browserBuilds.map((row) => {
                const selected =
                  selectedBuildIds.includes(row.id)
                const entry =
                  entries.find(
                    (item) => item.id === row.id,
                  )

                return (
                  <ToggleButton
                    key={row.id}
                    pressed={selected}
                    disabled={!apiReady}
                    className="compare-browser-build"
                    onPressedChange={() => {
                      void toggleBrowserBuild(row)
                    }}
                  >
                    <span>
                      <strong>{row.name}</strong>
                      <small>
                        {new Date(row.saved_at).toLocaleString()}
                        {entry?.loading && ' · 計算中…'}
                        {entry?.error && ` · ${entry.error}`}
                      </small>
                    </span>
                  </ToggleButton>
                )
              })}
            </div>
          )}
        </section>

        <div className="multi-compare-options">
          <ToggleButton
            pressed={onlyDiff}
            className="toggle-button-compact"
            onPressedChange={setOnlyDiff}
          >
            只顯示差異
          </ToggleButton>

          <ToggleButton
            pressed={showBaselineMonsterTargetOnly}
            className="toggle-button-compact"
            disabled={visibleColumns.length === 0}
            onPressedChange={setShowBaselineMonsterTargetOnly}
          >
            只顯示基準魔物的體種屬階
          </ToggleButton>

          <ToggleButton
            pressed={displayFilters.hidePhysical}
            className="toggle-button-compact"
            onPressedChange={(hidePhysical) =>
              onDisplayFiltersChange({
                ...displayFilters,
                hidePhysical,
              })
            }
          >
            隱藏物理
          </ToggleButton>

          <ToggleButton
            pressed={displayFilters.hideMagical}
            className="toggle-button-compact"
            onPressedChange={(hideMagical) =>
              onDisplayFiltersChange({
                ...displayFilters,
                hideMagical,
              })
            }
          >
            隱藏魔法
          </ToggleButton>

          <ToggleButton
            pressed={displayFilters.hideRecognition}
            className="toggle-button-compact"
            onPressedChange={(hideRecognition) =>
              onDisplayFiltersChange({
                ...displayFilters,
                hideRecognition,
              })
            }
          >
            隱藏辨識 / 解析
          </ToggleButton>

          <label>
            <span>比對基準</span>
            <select
              value={baselineId}
              disabled={
                visibleColumns.length === 0
              }
              onChange={(event) =>
                setBaselineId(
                  event.target.value,
                )
              }
            >
              {visibleColumns.map((column) => (
                <option
                  key={column.id}
                  value={column.id}
                >
                  {column.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="multi-compare-help">
          多裝備比對本身不保存另一套配裝資料。
          固定比較欄只來自上方「此瀏覽器存檔」；
          新增、覆蓋或刪除存檔後這裡會立即同步。
          「目前設定」可選擇是否一起比較，點欄名可切換基準。
          開啟「只顯示基準魔物的體種屬階」時，其他欄位的體型 / 種族 / 屬性 / 階級只顯示基準值，不改寫各配裝原本的傷害計算。
        </p>

        {visibleColumns.length === 0 ? (
          <p className="muted">
            請顯示目前設定，或從上方瀏覽器存檔選至少一份配裝。
          </p>
        ) : (
          <>
            <details
              className="multi-compare-section multi-compare-result-section"
              open
            >
              <summary>
                計算結果差異
                <span>{resultRows.length} 列</span>
              </summary>

              <div className="multi-compare-table-scroll">
                <table
                  className="multi-compare-table"
                  style={{
                    minWidth: `${compareTableMinWidth}px`,
                    width: '100%',
                  }}
                >
                  <colgroup>
                    <col className="multi-compare-label-col" />
                    {visibleColumns.map((column) => (
                      <col
                        key={column.id}
                        className="multi-compare-value-col"
                      />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th>項目</th>
                      {visibleColumns.map((column) => (
                        <th
                          key={column.id}
                          className={
                            baselineId === column.id
                              ? 'multi-compare-base'
                              : ''
                          }
                        >
                          <button
                            type="button"
                            onClick={() =>
                              setBaselineId(column.id)
                            }
                          >
                            {column.name}
                            {column.loading && (
                              <small>計算中</small>
                            )}
                            {baselineId === column.id && (
                              <small>基準</small>
                            )}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {resultRows.map((row) => {
                      const base =
                        baselineMap.get(row.key)

                      return (
                        <tr
                          key={row.key}
                          className={
                            row.key.startsWith(
                              'damage:',
                            )
                              ? 'multi-compare-damage-row'
                              : ''
                          }
                        >
                          <th>{row.label}</th>
                          {visibleColumns.map(
                            (column) => {
                              const map =
                                columnResultMaps.get(column.id) ??
                                new Map<string, CompareCell>()
                              const cell = resultCell(
                                column,
                                map,
                                row.key,
                              )

                              const delta =
                                column.id ===
                                baselineId
                                  ? null
                                  : compareDelta(
                                      cell.numeric,
                                      base?.numeric,
                                    )

                              return (
                                <td
                                  key={column.id}
                                  className={
                                    column.id ===
                                    baselineId
                                      ? 'multi-compare-base'
                                      : ''
                                  }
                                >
                                  <span>
                                    {cell.display ||
                                      '—'}
                                  </span>
                                  {delta && (
                                    <small
                                      className={
                                        `multi-compare-delta ` +
                                        `multi-compare-delta-${delta.direction}`
                                      }
                                    >
                                      <span
                                        className="multi-compare-delta-arrow"
                                        aria-hidden="true"
                                      >
                                        {delta.direction === 'up'
                                          ? '↑'
                                          : '↓'}
                                      </span>
                                      <span>
                                        {delta.amount}
                                      </span>
                                      {
                                        row.key.startsWith('damage:') &&
                                        delta.percent && (
                                          <span className="multi-compare-delta-percent">
                                            ({delta.percent})
                                          </span>
                                        )
                                      }
                                    </small>
                                  )}
                                </td>
                              )
                            },
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </details>

            <details
              className="multi-compare-section"
              open
            >
              <summary>
                裝備差異
                <span>{equipmentRows.length} 列</span>
              </summary>

              <div className="multi-compare-table-scroll">
                <table
                  className="multi-compare-table"
                  style={{
                    minWidth: `${compareTableMinWidth}px`,
                    width: '100%',
                  }}
                >
                  <colgroup>
                    <col className="multi-compare-label-col" />
                    {visibleColumns.map((column) => (
                      <col
                        key={column.id}
                        className="multi-compare-value-col"
                      />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th>項目</th>
                      {visibleColumns.map((column) => (
                        <th
                          key={column.id}
                          className={
                            baselineId === column.id
                              ? 'multi-compare-base'
                              : ''
                          }
                        >
                          <button
                            type="button"
                            onClick={() =>
                              setBaselineId(column.id)
                            }
                          >
                            {column.name}
                            {baselineId === column.id && (
                              <small>基準</small>
                            )}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {equipmentRows.map((row) => (
                      <tr key={row.key}>
                        <th>{row.label}</th>
                        {visibleColumns.map(
                          (column) => (
                            <td
                              key={column.id}
                              className={
                                row.kind === 'note'
                                  ? 'multi-compare-note-cell'
                                  : ''
                              }
                            >
                              {(
                                row.kind === 'note'
                                  ? parsedEquipmentNote(
                                      column,
                                      row.slotId,
                                    )
                                  : equipmentCell(
                                      column,
                                      row.slotId,
                                      row.kind,
                                    )
                              ) || '—'}
                            </td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>

            <details
              className="multi-compare-section"
              open
            >
              <summary>
                角色 / 目標輸入差異
                <span>{inputRows.length} 列</span>
              </summary>

              <div className="multi-compare-table-scroll">
                <table
                  className="multi-compare-table"
                  style={{
                    minWidth: `${compareTableMinWidth}px`,
                    width: '100%',
                  }}
                >
                  <colgroup>
                    <col className="multi-compare-label-col" />
                    {visibleColumns.map((column) => (
                      <col
                        key={column.id}
                        className="multi-compare-value-col"
                      />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th>項目</th>
                      {visibleColumns.map((column) => (
                        <th
                          key={column.id}
                          className={
                            baselineId === column.id
                              ? 'multi-compare-base'
                              : ''
                          }
                        >
                          <button
                            type="button"
                            onClick={() =>
                              setBaselineId(column.id)
                            }
                          >
                            {column.name}
                            {baselineId === column.id && (
                              <small>基準</small>
                            )}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {inputRows.map((row) => (
                      <tr key={row.key}>
                        <th>{row.label}</th>
                        {visibleColumns.map((column) => (
                          <td
                            key={column.id}
                            className={
                              column.id === baselineId
                                ? 'multi-compare-base'
                                : ''
                            }
                          >
                            {inputValue(row, column) || '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </div>
    </details>
  )
}
