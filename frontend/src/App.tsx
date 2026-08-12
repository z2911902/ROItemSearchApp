// === STAGE 21.18 COMPARE + RUNTIME DAMAGE CONTEXT ===
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  calculateStatus,
  calculateStatusDamage,
  getEquipmentItemMeta,
  getHealth,
  getItem,
  getJobs,
  searchEquipmentItems,
} from './api'
import type {
  ApiHealth,
  CalculatePayload,
  CalculateResponse,
  ItemDetail,
  ItemSummary,
  JobSummary,
  AdvancedCharacterState,
  CharacterStatusResult,
  DamageResult,
  DamageState,
  StatusSettingsState,
} from './types'
import BuildManager from './components/BuildManager'
import DamagePanel from './components/DamagePanel'
import CharacterAdvancedPanel from './components/CharacterAdvancedPanel'
import EnchantToolModal from './components/EnchantToolModal'
import EquipmentSlotEditor from './components/EquipmentSlotEditor'
import LapineToolModal from './components/LapineToolModal'
import MultiComparePanel from './components/MultiComparePanel'
import ToggleButton from './components/ToggleButton'
import {
  DEFAULT_EFFECT_DISPLAY_FILTERS,
  filterEffectLines,
  searchEffectLines,
  type EffectDisplayFilters,
} from './effectDisplay'
import {
  defenseAfterDamagePercents,
  monsterTargetText,
} from './damageDisplay'
import SkillTreePanel from './components/SkillTreePanel'
import {
  ALL_EQUIPMENT_SLOTS,
  EQUIPMENT_GROUPS,
  createEmptyEquipmentSlotState,
  type EquipmentSlotState,
} from './equipmentSlots'
import {
  normalizeSnapshot,
  type WebBuildSnapshot,
} from './buildProject'
import {
  loadBrowserDraft,
  saveBrowserDraft,
} from './browserStorage'
import {
  descriptionToSafeHtml,
} from './itemDescription'

const GID = {
  baseLv: 11,
  jobLv: 12,
  job: 19,
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
  mhp: 200,
  msp: 202,
  runeSlots: 263,
  runeRefine: 264,
} as const

const AUTO_CALCULATE_DEBOUNCE_MS = 300

function readableError(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function numberValue(value: string, fallback = 0): number {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function itemTitle(item: ItemSummary): string {
  return item.base_name || item.name || `物品 ${item.item_id}`
}

function ApiStatus({
  health,
  error,
  loading,
  onRetry,
}: {
  health: ApiHealth | null
  error: string
  loading: boolean
  onRetry: () => void
}) {
  const ready = health?.core_ready === true

  return (
    <section className="status-card" aria-live="polite">
      <div className="status-row">
        <span
          className={`status-dot ${
            loading ? 'status-loading' : ready ? 'status-ok' : 'status-error'
          }`}
          aria-hidden="true"
        />
        <div className="status-copy">
          <strong>
            {loading
              ? '正在連線 API…'
              : ready
                ? 'Core API 已連線'
                : 'Core API 未就緒'}
          </strong>
          <span>
            {ready
              ? `${health.item_count.toLocaleString()} 個物品 · API ${health.api_version}`
              : error || health?.startup_error || '請確認 FastAPI 是否已啟動'}
          </span>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={onRetry}
          disabled={loading}
        >
          重新檢查
        </button>
      </div>
    </section>
  )
}

function ItemResult({
  item,
  selected,
  onSelect,
  actionLabel,
}: {
  item: ItemSummary
  selected: boolean
  onSelect: (itemId: number) => void
  actionLabel?: string
}) {
  return (
    <button
      className={`result-item ${selected ? 'result-item-selected' : ''}`}
      type="button"
      onClick={() => onSelect(item.item_id)}
    >
      <div className="result-title-row">
        <strong>{itemTitle(item)}</strong>
        <div className="badge-row">
          {item.is_equipment && <span className="badge">裝備</span>}
          {actionLabel && <span className="mini-action">{actionLabel}</span>}
        </div>
      </div>
      <div className="result-meta">
        <span>ID {item.item_id}</span>
        {item.slot > 0 && <span>Slot {item.slot}</span>}
        {item.kr_name && <span>{item.kr_name}</span>}
      </div>
    </button>
  )
}

function DetailPanel({
  detail,
  loading,
  error,
}: {
  detail: ItemDetail | null
  loading: boolean
  error: string
}) {
  const descriptionHtml = useMemo(
    () =>
      descriptionToSafeHtml(
        detail?.description ?? [],
      ),
    [detail?.description],
  )

  if (loading) {
    return (
      <section className="detail-panel empty-panel">
        <div className="spinner" aria-hidden="true" />
        <p>讀取物品資料中…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="detail-panel empty-panel">
        <p className="error-text">{error}</p>
      </section>
    )
  }

  if (!detail) {
    return (
      <section className="detail-panel empty-panel">
        <p>從左側搜尋結果選一個物品。</p>
      </section>
    )
  }

  const title = itemTitle(detail)

  return (
    <article className="detail-panel">
      <header className="detail-header">
        <div>
          <div className="eyebrow">ITEM DETAIL</div>
          <h2>{title}</h2>
          {detail.name && detail.name !== title && (
            <p className="muted">{detail.name}</p>
          )}
        </div>
        {detail.is_equipment && <span className="badge badge-large">裝備</span>}
      </header>

      <dl className="facts-grid">
        <div>
          <dt>Item ID</dt>
          <dd>{detail.item_id}</dd>
        </div>
        <div>
          <dt>Slot</dt>
          <dd>{detail.slot}</dd>
        </div>
        <div>
          <dt>Resource Name</dt>
          <dd>{detail.kr_name || '—'}</dd>
        </div>
        <div>
          <dt>類型</dt>
          <dd>{detail.is_equipment ? 'Equipment' : 'Item'}</dd>
        </div>
      </dl>

      <section className="description-section">
        <h3>物品說明</h3>
        {descriptionHtml ? (
          <div
            className="description-lines description-html"
            dangerouslySetInnerHTML={{
              __html: descriptionHtml,
            }}
          />
        ) : (
          <p className="muted">目前沒有說明文字。</p>
        )}
      </section>
    </article>
  )
}

function createInitialEquipmentState(): Record<
  number,
  EquipmentSlotState<ItemSummary>
> {
  return Object.fromEntries(
    ALL_EQUIPMENT_SLOTS.map((slot) => [
      slot.slotId,
      createEmptyEquipmentSlotState<ItemSummary>(),
    ]),
  ) as Record<number, EquipmentSlotState<ItemSummary>>
}

type AutoCalcPhase =
  | 'idle'
  | 'scheduled'
  | 'calculating'
  | 'ready'
  | 'error'

interface AutoCalcDockState {
  phase: AutoCalcPhase
  jobReady: boolean
  activeSlotCount: number
  selectedSlotCount: number
  lastCalculatedAt: Date | null
  lastCalculationDurationMs: number | null
  draftSavedAt: Date | null
  draftRestored: boolean
}

interface DamageDockState {
  sectionVisible: boolean
  skillId: number | null
  skillName: string
  skillLevel: number
  totalMin: number | null
  totalMax: number | null
  targetText: string
  defenseAfterLabel: string
  defenseAfterPercent: number | null
  traitDefenseAfterLabel: string
  traitDefenseAfterPercent: number | null
  calculating: boolean
  error: string
}

const EMPTY_AUTO_CALC_DOCK: AutoCalcDockState = {
  phase: 'idle',
  jobReady: false,
  activeSlotCount: 0,
  selectedSlotCount: 0,
  lastCalculatedAt: null,
  lastCalculationDurationMs: null,
  draftSavedAt: null,
  draftRestored: false,
}

const EMPTY_DAMAGE_DOCK: DamageDockState = {
  sectionVisible: false,
  skillId: null,
  skillName: '',
  skillLevel: 1,
  totalMin: null,
  totalMax: null,
  targetText: '',
  defenseAfterLabel: '魔物最終防禦後傷害',
  defenseAfterPercent: null,
  traitDefenseAfterLabel: '特性防禦後傷害',
  traitDefenseAfterPercent: null,
  calculating: false,
  error: '',
}

function autoCalcLabel(
  apiReady: boolean,
  state: AutoCalcDockState,
): string {
  if (!apiReady) return '自動計算：API 未就緒'
  if (!state.jobReady) return '自動計算：等待職業'
  if (state.phase === 'scheduled') return '自動計算：等待輸入停止…'
  if (state.phase === 'calculating') return '自動計算：Python Core 計算中…'
  if (state.phase === 'ready') return '自動計算：已更新'
  if (state.phase === 'error') return '自動計算：失敗'
  return '自動計算：待命'
}

function AutoCalcTopStatus({
  apiReady,
  state,
}: {
  apiReady: boolean
  state: AutoCalcDockState
}) {
  return (
    <section
      className="auto-calc-status auto-calc-status-top"
      aria-live="polite"
    >
      <div
        className={`auto-calc-indicator auto-calc-${state.phase}`}
        aria-hidden="true"
      />
      <div className="auto-calc-copy">
        <strong>{autoCalcLabel(apiReady, state)}</strong>
        <span>
          {state.activeSlotCount
            ? `${state.activeSlotCount} 個有內容部位 · ${state.selectedSlotCount} 個主裝備`
            : '角色值改變仍會自動重算'}
          {state.lastCalculatedAt &&
            ` · 計算 ${state.lastCalculatedAt.toLocaleTimeString()}`}
          {state.lastCalculationDurationMs !== null &&
            ` · 處理 ${Math.round(state.lastCalculationDurationMs)}ms`}
          {state.draftSavedAt &&
            ` · 瀏覽器草稿 ${state.draftSavedAt.toLocaleTimeString()}`}
          {state.draftRestored && !state.draftSavedAt &&
            ' · 已還原瀏覽器草稿'}
        </span>
      </div>
      <span className="auto-calc-debounce">
        {AUTO_CALCULATE_DEBOUNCE_MS}ms
      </span>
    </section>
  )
}

function compactDamagePercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(2)}%`
}

function compactDamageText(
  state: DamageDockState,
): string {
  if (state.skillId === null) {
    return '技能傷害｜未選技能'
  }

  const skill =
    state.skillName || `技能 ${state.skillId}`
  const target = state.targetText
    ? `｜目標 ${state.targetText}`
    : ''
  const defense =
    `｜${state.defenseAfterLabel} ${compactDamagePercent(state.defenseAfterPercent)}` +
    `｜${state.traitDefenseAfterLabel} ${compactDamagePercent(state.traitDefenseAfterPercent)}`

  if (state.error) {
    return `技能傷害｜${skill} Lv.${state.skillLevel}｜錯誤：${state.error}${target}${defense}`
  }

  if (state.calculating) {
    return `技能傷害｜${skill} Lv.${state.skillLevel}｜計算中…${target}${defense}`
  }

  if (
    state.totalMin !== null &&
    state.totalMax !== null
  ) {
    const total =
      state.totalMin === state.totalMax
        ? state.totalMax.toLocaleString()
        : `${state.totalMin.toLocaleString()} ~ ${state.totalMax.toLocaleString()}`

    return `技能傷害｜${skill} Lv.${state.skillLevel}｜${total}${target}${defense}`
  }

  return `技能傷害｜${skill} Lv.${state.skillLevel}｜等待結果${target}${defense}`
}

function CompactDamageDock({
  state,
}: {
  state: DamageDockState
}) {
  if (state.sectionVisible) {
    return null
  }

  return (
    <button
      className="compact-damage-dock"
      type="button"
      onClick={() => {
        document
          .getElementById('skill-monster-damage-section')
          ?.scrollIntoView({
            behavior: 'smooth',
            block: 'start',
          })
      }}
      title="前往技能 / 魔物 / 傷害區"
    >
      <span className="compact-damage-dot" />
      <strong>{compactDamageText(state)}</strong>
      <span>前往技能 / 魔物 / 傷害 ↓</span>
    </button>
  )
}

function Calculator({
  apiReady,
  onAutoCalcDockChange,
  onDamageDockChange,
}: {
  apiReady: boolean
  onAutoCalcDockChange: (
    state: AutoCalcDockState,
  ) => void
  onDamageDockChange: (
    state: DamageDockState,
  ) => void
}) {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)
  const [jobsError, setJobsError] = useState('')
  const [jobId, setJobId] = useState<number | null>(null)

  const [baseLv, setBaseLv] = useState(260)
  const [jobLv, setJobLv] = useState(60)
  const [str, setStr] = useState(1)
  const [agi, setAgi] = useState(1)
  const [vit, setVit] = useState(1)
  const [intStat, setIntStat] = useState(1)
  const [dex, setDex] = useState(1)
  const [luk, setLuk] = useState(1)

  const [equipment, setEquipment] = useState<
    Record<number, EquipmentSlotState<ItemSummary>>
  >(createInitialEquipmentState)

  const [advanced, setAdvanced] = useState<AdvancedCharacterState>({
    pow: 0,
    sta: 0,
    wis: 0,
    spl: 0,
    con: 0,
    crt: 0,
    enabledSkillNames: [],
    enabledSkillLevels: {},
    targetElement: 0,
    targetRace: 0,
    targetSize: 1,
    targetClass: 0,
  })

  const [damageState, setDamageState] = useState<DamageState>({
    skillId: null,
    skillLevel: 1,
    attackElement: null,
    formulaOverride: '',
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
    mhp: 0,
    msp: 0,
    mhpNow: 0,
    mspNow: 0,
    monster: {
      size: 1,
      element: 0,
      elementLv: 1,
      race: 0,
      classId: 0,
      def: 0,
      defc: 0,
      res: 0,
      mdef: 0,
      mdefc: 0,
      mres: 0,
      damageMultiplierPercent: 100,
      betelgeuseReductionPercent: 0,
    },
  })
  const [damageResult, setDamageResult] = useState<DamageResult | null>(null)
  const [statusSettings, setStatusSettings] = useState<StatusSettingsState>({
    mhpInput: 0,
    mspInput: 0,
    useLogoutHpsp: false,
    hpPercent: 100,
    spPercent: 100,
  })
  const [statusResult, setStatusResult] =
    useState<CharacterStatusResult | null>(null)
  const [leftHandBlocked, setLeftHandBlocked] =
    useState(false)
  const [effectDisplayFilters, setEffectDisplayFilters] =
    useState<EffectDisplayFilters>({
      ...DEFAULT_EFFECT_DISPLAY_FILTERS,
    })
  const [effectSearchText, setEffectSearchText] =
    useState('')
  const [effectView, setEffectView] =
    useState<'total' | 'combo'>('total')

  const [toolTarget, setToolTarget] = useState<{
    kind: 'enchant' | 'lapine'
    slotId: number
  } | null>(null)

  const [calculating, setCalculating] = useState(false)
  const [calculateError, setCalculateError] = useState('')
  const [result, setResult] = useState<CalculateResponse | null>(null)
  const [autoCalcStatus, setAutoCalcStatus] = useState<
    'idle' | 'scheduled' | 'calculating' | 'ready' | 'error'
  >('idle')
  const [lastCalculatedAt, setLastCalculatedAt] = useState<Date | null>(null)
  const [lastCalculationDurationMs, setLastCalculationDurationMs] =
    useState<number | null>(null)
  const calculationSequenceRef = useRef(0)
  const browserDraftHydratedRef = useRef(false)
  const [browserDraftSavedAt, setBrowserDraftSavedAt] =
    useState<Date | null>(null)
  const [browserDraftRestored, setBrowserDraftRestored] =
    useState(false)
  const damageSectionRef =
    useRef<HTMLDivElement | null>(null)
  const [damageSectionVisible, setDamageSectionVisible] =
    useState(false)

  useEffect(() => {
    const node = damageSectionRef.current

    if (
      !node ||
      typeof IntersectionObserver === 'undefined'
    ) {
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setDamageSectionVisible(
          Boolean(entry?.isIntersecting),
        )
      },
      {
        threshold: [0, 0.08, 0.2],
        rootMargin: '-110px 0px -25% 0px',
      },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!apiReady) {
      setJobsLoading(false)
      return
    }

    const controller = new AbortController()

    void (async () => {
      setJobsLoading(true)
      setJobsError('')

      try {
        const response = await getJobs(controller.signal)
        const numericJobs = response.jobs.filter(
          (job): job is JobSummary & { job_id: number } =>
            typeof job.job_id === 'number' && Boolean(job.name.trim()),
        )
        setJobs(numericJobs)

        const firstJob =
          numericJobs.find((job) => job.job_id !== 0) ?? numericJobs[0]
        if (firstJob) {
          setJobId((current) =>
            current ?? firstJob.job_id
          )
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setJobsError(readableError(error))
        }
      } finally {
        if (!controller.signal.aborted) {
          setJobsLoading(false)
        }
      }
    })()

    return () => controller.abort()
  }, [apiReady])

  const rightHandItem =
    equipment[4]?.item ?? null

  useEffect(() => {
    if (!rightHandItem) {
      setLeftHandBlocked(false)
      return
    }

    let disposed = false
    const controller = new AbortController()

    const applyBlocked = (blocked: boolean) => {
      if (disposed) return

      setLeftHandBlocked(blocked)

      if (!blocked) return

      // Exact Desktop behavior when left-hand UI is hidden:
      // clear equipment/refine/Grade/cards/note instead of merely hiding CSS.
      setEquipment((current) => {
        const left =
          current[3] ??
          createEmptyEquipmentSlotState<ItemSummary>()

        const hasContent = Boolean(
          left.item ||
          left.refine ||
          left.grade ||
          left.cards.some((card) => card.trim()) ||
          left.note.trim(),
        )

        if (!hasContent) {
          return current
        }

        return {
          ...current,
          [3]:
            createEmptyEquipmentSlotState<ItemSummary>(),
        }
      })

      setToolTarget((current) =>
        current?.slotId === 3 ? null : current,
      )
    }

    if (
      typeof rightHandItem.blocks_left_hand ===
      'boolean'
    ) {
      applyBlocked(
        rightHandItem.blocks_left_hand,
      )
      return () => {
        disposed = true
        controller.abort()
      }
    }

    if (!apiReady || rightHandItem.item_id <= 0) {
      return () => {
        disposed = true
        controller.abort()
      }
    }

    void (async () => {
      try {
        const response =
          await getEquipmentItemMeta(
            rightHandItem.item_id,
            controller.signal,
          )

        if (controller.signal.aborted) return

        const blocked =
          response.item.blocks_left_hand === true

        // Cache the metadata into the selected item so Web Build snapshots
        // preserve it and subsequent renders do not need another request.
        setEquipment((current) => {
          const right = current[4]
          if (
            !right?.item ||
            right.item.item_id !==
              rightHandItem.item_id
          ) {
            return current
          }

          return {
            ...current,
            [4]: {
              ...right,
              item: {
                ...right.item,
                ...response.item,
              },
            },
          }
        })

        applyBlocked(blocked)
      } catch (error) {
        if (!controller.signal.aborted) {
          console.warn(
            'Stage21 weapon metadata lookup failed',
            error,
          )
          setLeftHandBlocked(false)
        }
      }
    })()

    return () => {
      disposed = true
      controller.abort()
    }
  }, [
    apiReady,
    rightHandItem?.blocks_left_hand,
    rightHandItem?.item_id,
  ])

  const displayedTotalEffectLines = useMemo(
    () =>
      filterEffectLines(
        result?.combined_lines ?? [],
        effectDisplayFilters,
      ),
    [
      effectDisplayFilters,
      result?.combined_lines,
    ],
  )

  const displayedComboEffectLines = useMemo(
    () =>
      filterEffectLines(
        result?.combo_lines ?? [],
        effectDisplayFilters,
      ),
    [
      effectDisplayFilters,
      result?.combo_lines,
    ],
  )

  const activeEffectLines =
    effectView === 'combo'
      ? displayedComboEffectLines
      : displayedTotalEffectLines

  const searchedEffectLines = useMemo(
    () =>
      searchEffectLines(
        activeEffectLines,
        effectSearchText,
      ),
    [
      activeEffectLines,
      effectSearchText,
    ],
  )

  const selectedSlotCount = useMemo(
    () =>
      ALL_EQUIPMENT_SLOTS.filter(
        (definition) => equipment[definition.slotId]?.item,
      ).length,
    [equipment],
  )

  const activeSlotCount = useMemo(
    () =>
      ALL_EQUIPMENT_SLOTS.filter((definition) => {
        const slot = equipment[definition.slotId]
        return Boolean(
          slot?.item ||
          slot?.cards.some((card) => card.trim()) ||
          slot?.note.trim(),
        )
      }).length,
    [equipment],
  )

  useEffect(() => {
    onAutoCalcDockChange({
      phase: autoCalcStatus,
      jobReady: jobId !== null,
      activeSlotCount,
      selectedSlotCount,
      lastCalculatedAt,
      lastCalculationDurationMs,
      draftSavedAt: browserDraftSavedAt,
      draftRestored: browserDraftRestored,
    })
  }, [
    activeSlotCount,
    autoCalcStatus,
    browserDraftRestored,
    browserDraftSavedAt,
    jobId,
    lastCalculatedAt,
    lastCalculationDurationMs,
    onAutoCalcDockChange,
    selectedSlotCount,
  ])

  useEffect(() => {
    const defense =
      defenseAfterDamagePercents(damageResult)

    onDamageDockChange({
      sectionVisible: damageSectionVisible,
      skillId: damageState.skillId,
      skillName: damageResult?.skill.name ?? '',
      skillLevel:
        damageResult?.skill.level ??
        damageState.skillLevel,
      totalMin:
        damageResult?.total_damage_min ?? null,
      totalMax:
        damageResult?.total_damage ?? null,
      targetText: monsterTargetText(
        damageState.monster,
      ),
      defenseAfterLabel: defense.defenseLabel,
      defenseAfterPercent:
        defense.defensePercent,
      traitDefenseAfterLabel: defense.traitLabel,
      traitDefenseAfterPercent:
        defense.traitPercent,
      calculating,
      error: calculateError,
    })
  }, [
    calculateError,
    calculating,
    damageResult,
    damageSectionVisible,
    damageState.monster,
    damageState.skillId,
    damageState.skillLevel,
    onDamageDockChange,
  ])

  const selectedJob = useMemo(
    () => jobs.find((job) => job.job_id === jobId) ?? null,
    [jobId, jobs],
  )

  const payload = useMemo<CalculatePayload | null>(() => {
    if (jobId === null) {
      return null
    }

    const refineInputs = Object.fromEntries(
      ALL_EQUIPMENT_SLOTS.map((definition) => [
        definition.slotId,
        equipment[definition.slotId]?.refine ?? 0,
      ]),
    ) as Record<number, number>

    const slots = ALL_EQUIPMENT_SLOTS.flatMap((definition) => {
      const slot = equipment[definition.slotId]
      if (!slot) {
        return []
      }

      const cards = slot.cards.map((card) => card.trim()) as [
        string,
        string,
        string,
        string,
      ]
      const note = slot.note.trim()
      const hasSupplement = cards.some(Boolean) || Boolean(note)

      if (!slot.item && !hasSupplement) {
        return []
      }

      return [
        {
          part_name: definition.label,
          slot_id: definition.slotId,
          // Keep the exact parsed Desktop/Core display name when possible.
          equip_name: slot.item ? slot.item.name || slot.item.base_name : '',
          grade: slot.grade,
          cards,
          note,
        },
      ]
    })

    return {
      get_values: {
        [GID.baseLv]: baseLv,
        [GID.jobLv]: jobLv,
        [GID.job]: jobId,
        [GID.str]: str,
        [GID.agi]: agi,
        [GID.vit]: vit,
        [GID.int]: intStat,
        [GID.dex]: dex,
        [GID.luk]: luk,
        [GID.pow]: advanced.pow,
        [GID.sta]: advanced.sta,
        [GID.wis]: advanced.wis,
        [GID.spl]: advanced.spl,
        [GID.con]: advanced.con,
        [GID.crt]: advanced.crt,
        [GID.mhp]: statusSettings.mhpInput,
        [GID.msp]: statusSettings.mspInput,
        [GID.runeSlots]: equipment[100]?.grade ?? 0,
        [GID.runeRefine]: equipment[100]?.refine ?? 0,
      },
      refine_inputs: refineInputs,
      slots,
      enabled_skill_names: advanced.enabledSkillNames,
      hide_unrecognized:
        effectDisplayFilters.hideRecognition,
      hide_physical:
        effectDisplayFilters.hidePhysical,
      hide_magical:
        effectDisplayFilters.hideMagical,
      show_source: true,
      sort_mode: '來源順序',
      context_variables: {
        target_element: advanced.targetElement,
        target_race: advanced.targetRace,
        target_size: advanced.targetSize,
        target_class: advanced.targetClass,
      },
      enabled_skill_levels: advanced.enabledSkillLevels,
    }
  }, [
    advanced,
    agi,
    baseLv,
    dex,
    equipment,
    effectDisplayFilters.hideMagical,
    effectDisplayFilters.hidePhysical,
    effectDisplayFilters.hideRecognition,
    intStat,
    jobId,
    jobLv,
    luk,
    statusSettings.mhpInput,
    statusSettings.mspInput,
    str,
    vit,
  ])

  useEffect(() => {
    if (!apiReady || !payload) {
      setCalculating(false)
      setAutoCalcStatus('idle')
      return
    }

    const sequence = ++calculationSequenceRef.current
    const controller = new AbortController()

    setCalculateError('')
    setAutoCalcStatus('scheduled')

    const timer = window.setTimeout(() => {
      void (async () => {
        setCalculating(true)
        setAutoCalcStatus('calculating')

        // Actual processing time only.  The 300ms debounce wait above is
        // deliberately excluded so this measures Web -> FastAPI -> Core ->
        // response handling rather than UI input settling time.
        const calculationStartedAt =
          window.performance.now()

        try {
          if (damageState.skillId !== null) {
            const response = await calculateStatusDamage(
              payload,
              damageState,
              statusSettings,
              controller.signal,
            )

            if (
              controller.signal.aborted ||
              sequence !== calculationSequenceRef.current
            ) {
              return
            }

            setResult(response.effect)
            setStatusResult(response.status)
            setDamageResult(response.damage)
          } else {
            const response = await calculateStatus(
              payload,
              statusSettings,
              controller.signal,
            )

            if (
              controller.signal.aborted ||
              sequence !== calculationSequenceRef.current
            ) {
              return
            }

            setResult(response.effect)
            setStatusResult(response.status)
            setDamageResult(null)
          }
          setCalculateError('')
          setLastCalculatedAt(new Date())
          setLastCalculationDurationMs(
            window.performance.now() -
              calculationStartedAt,
          )
          setAutoCalcStatus('ready')
        } catch (error) {
          if (
            controller.signal.aborted ||
            sequence !== calculationSequenceRef.current
          ) {
            return
          }

          setCalculateError(readableError(error))
          setLastCalculationDurationMs(
            window.performance.now() -
              calculationStartedAt,
          )
          setAutoCalcStatus('error')
        } finally {
          if (
            !controller.signal.aborted &&
            sequence === calculationSequenceRef.current
          ) {
            setCalculating(false)
          }
        }
      })()
    }, AUTO_CALCULATE_DEBOUNCE_MS)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [apiReady, damageState, payload, statusSettings])

  function updateEquipmentSlot(
    slotId: number,
    value: EquipmentSlotState<ItemSummary>,
  ) {
    if (slotId === 4) {
      const blocked =
        value.item?.blocks_left_hand

      if (blocked === true) {
        setLeftHandBlocked(true)
        setEquipment((current) => ({
          ...current,
          [4]: value,
          [3]:
            createEmptyEquipmentSlotState<ItemSummary>(),
        }))
        setToolTarget((current) =>
          current?.slotId === 3 ? null : current,
        )
        setCalculateError('')
        return
      }

      if (blocked === false || !value.item) {
        setLeftHandBlocked(false)
      }
    }

    setEquipment((current) => ({
      ...current,
      [slotId]: value,
    }))
    setCalculateError('')
  }

  function clearAllEquipment() {
    setEquipment(createInitialEquipmentState())
    setCalculateError('')
    setToolTarget(null)
  }

  const toolDefinition = toolTarget
    ? ALL_EQUIPMENT_SLOTS.find(
        (definition) => definition.slotId === toolTarget.slotId,
      ) ?? null
    : null
  const toolSlot = toolDefinition
    ? equipment[toolDefinition.slotId] ?? null
    : null

  function applyEnchant(slotId: number, enchantSlotId: number, enchantName: string) {
    const slot = equipment[slotId]
    if (!slot || enchantSlotId < 0 || enchantSlotId > 3) {
      return
    }
    const cards = [...slot.cards] as [string, string, string, string]
    cards[enchantSlotId] = enchantName
    updateEquipmentSlot(slotId, { ...slot, cards })
  }

  function applyLapineLua(slotId: number, luaEffect: string) {
    const slot = equipment[slotId]
    const normalized = luaEffect.trim()
    if (!slot || !normalized) {
      return
    }

    // New enchant replaces the previous option text for this part.
    updateEquipmentSlot(slotId, {
      ...slot,
      note: normalized,
    })
  }

  const buildSnapshot = useMemo<WebBuildSnapshot>(
    () => ({
      character: {
        jobId,
        baseLv,
        jobLv,
        str,
        agi,
        vit,
        intStat,
        dex,
        luk,
      },
      advanced,
      equipment,
      damage: damageState,
      status: statusSettings,
    }),
    [
      advanced,
      damageState,
      agi,
      baseLv,
      dex,
      equipment,
      intStat,
      jobId,
      jobLv,
      luk,
      statusSettings,
      str,
      vit,
    ],
  )

  function loadBuildSnapshot(snapshot: WebBuildSnapshot) {
    const character = snapshot.character

    setJobId(character.jobId)
    setBaseLv(character.baseLv)
    setJobLv(character.jobLv)
    setStr(character.str)
    setAgi(character.agi)
    setVit(character.vit)
    setIntStat(character.intStat)
    setDex(character.dex)
    setLuk(character.luk)
    setAdvanced(snapshot.advanced)
    setEquipment(snapshot.equipment)
    setDamageState({
      ...snapshot.damage,
      special: {
        ...snapshot.damage.special,
        // Stage21.8 intentionally leaves the legacy formula variable blank.
        totalSrl: 0,
      },
    })
    setStatusSettings(snapshot.status)
    setStatusResult(null)
    setDamageResult(null)

    setToolTarget(null)
    setCalculateError('')
  }

  useEffect(() => {
    if (browserDraftHydratedRef.current) {
      return
    }

    const stored = loadBrowserDraft()

    if (stored) {
      try {
        loadBuildSnapshot(
          normalizeSnapshot(stored.snapshot),
        )

        const filters =
          stored.effectDisplayFilters

        if (
          filters &&
          typeof filters.hidePhysical === 'boolean' &&
          typeof filters.hideMagical === 'boolean' &&
          typeof filters.hideRecognition === 'boolean'
        ) {
          setEffectDisplayFilters({
            hidePhysical: filters.hidePhysical,
            hideMagical: filters.hideMagical,
            hideRecognition: filters.hideRecognition,
          })
        }

        const savedAt = new Date(stored.savedAt)
        if (!Number.isNaN(savedAt.getTime())) {
          setBrowserDraftSavedAt(savedAt)
        }
        setBrowserDraftRestored(true)
      } catch (error) {
        console.warn(
          'Stage21.3 browser draft restore failed',
          error,
        )
      }
    }

    browserDraftHydratedRef.current = true
  }, [])

  useEffect(() => {
    if (!browserDraftHydratedRef.current) {
      return
    }

    const save = () => {
      const record = saveBrowserDraft(
        buildSnapshot,
        effectDisplayFilters,
      )

      if (record) {
        const savedAt = new Date(record.savedAt)
        setBrowserDraftSavedAt(savedAt)
      }
    }

    const timer = window.setTimeout(
      save,
      220,
    )

    // pagehide also covers Vite/full page reload and mobile tab disposal.
    const flush = () => save()
    window.addEventListener(
      'pagehide',
      flush,
    )

    return () => {
      window.clearTimeout(timer)
      window.removeEventListener(
        'pagehide',
        flush,
      )
    }
  }, [
    buildSnapshot,
    effectDisplayFilters,
  ])

  return (
    <section className="calculator-card">
      <div className="section-heading">
        <div>
          <div className="eyebrow">STAGE 21 · TWO-HAND + LIVE SEARCH + MULTI COMPARE</div>
          <h2>一般裝備部位</h2>
          <p>
            雙手武器會自動清空/隱藏左手；裝備搜尋支援 Desktop 多條件 AND；多配裝比對仍走同一套 Python Core。
          </p>
        </div>
        <div className="section-heading-actions">
          <span className="badge badge-large">
            {selectedSlotCount}/{ALL_EQUIPMENT_SLOTS.length} 已裝備
          </span>
          <button
            className="button button-secondary"
            type="button"
            onClick={clearAllEquipment}
            disabled={selectedSlotCount === 0}
          >
            清空裝備
          </button>
        </div>
      </div>

      <BuildManager
        snapshot={buildSnapshot}
        jobs={jobs}
        onLoad={loadBuildSnapshot}
      />

      <MultiComparePanel
        apiReady={apiReady}
        currentSnapshot={buildSnapshot}
        currentEffect={result}
        currentStatus={statusResult}
        currentDamage={damageResult}
        jobs={jobs}
        displayFilters={effectDisplayFilters}
        onDisplayFiltersChange={setEffectDisplayFilters}
      />

      <CharacterAdvancedPanel
        character={{
          jobId,
          baseLv,
          jobLv,
          str,
          agi,
          vit,
          intStat,
          dex,
          luk,
        }}
        onCharacterChange={(next) => {
          setJobId(next.jobId)
          setBaseLv(next.baseLv)
          setJobLv(next.jobLv)
          setStr(next.str)
          setAgi(next.agi)
          setVit(next.vit)
          setIntStat(next.intStat)
          setDex(next.dex)
          setLuk(next.luk)
          setCalculateError('')
        }}
        value={advanced}
        jobCode={selectedJob?.code ?? ''}
        jobs={jobs}
        jobsLoading={jobsLoading}
        jobsError={jobsError}
        onChange={(next) => {
          // target* and enabledSkillLevels stay in state for backward
          // compatibility / DamagePanel / SkillTree, but their duplicate
          // controls are intentionally removed from this panel.
          setAdvanced(next)
          setCalculateError('')
        }}
        apiReady={apiReady}
        statusSettings={statusSettings}
        statusResult={statusResult}
        onStatusChange={(next) => {
          setStatusSettings(next)
          setCalculateError('')
        }}
      />

      <SkillTreePanel
        apiReady={apiReady}
        jobId={jobId}
        note={equipment[102]?.note ?? ''}
        onNoteChange={(note) => {
          const current =
            equipment[102] ??
            createEmptyEquipmentSlotState<ItemSummary>()
          updateEquipmentSlot(102, {
            ...current,
            note,
          })
        }}
      />

      <div
        id="skill-monster-damage-section"
        ref={damageSectionRef}
        className="damage-section-anchor"
      >
        <DamagePanel
          apiReady={apiReady}
          jobId={jobId}
          value={damageState}
          onChange={(next) => {
            setDamageState(next)
            setAdvanced((current) => ({
              ...current,
              targetSize: next.monster.size,
              targetElement: next.monster.element,
              targetRace: next.monster.race,
              targetClass: next.monster.classId,
            }))
            setCalculateError('')
          }}
          result={damageResult}
          calculating={calculating}
        />
      </div>

      <div className="equipment-groups">
        {EQUIPMENT_GROUPS.map((group) => {
          const allDefinitions =
            ALL_EQUIPMENT_SLOTS.filter(
              (definition) =>
                definition.group === group.key,
            )
          const definitions =
            allDefinitions.filter(
              (definition) =>
                !(
                  leftHandBlocked &&
                  definition.slotId === 3
                ),
            )
          const hidesLeftHand =
            group.key === 'equipment' &&
            leftHandBlocked

          return (
            <section className="equipment-group" key={group.key}>
              <header className="equipment-group-header">
                <div>
                  <h3>{group.label}</h3>
                  <p>{group.description}</p>
                </div>
                <span>
                  {definitions.length} 部位
                  {hidesLeftHand && ' · 左手已隱藏'}
                </span>
              </header>

              {hidesLeftHand && (
                <div className="left-hand-blocked-notice">
                  <strong>左手(盾牌) 已清空並隱藏</strong>
                  <span>
                    目前右手武器依 Desktop weapon class 規則不可使用左手。
                    換回可持副手的武器後會自動重新顯示。
                  </span>
                </div>
              )}

              <div className="equipment-slot-grid">
                {definitions.map((definition) => (
                  <EquipmentSlotEditor
                    key={definition.slotId}
                    definition={definition}
                    value={
                      equipment[definition.slotId] ??
                      createEmptyEquipmentSlotState<ItemSummary>()
                    }
                    apiReady={apiReady}
                    previewContext={payload}
                    onChange={(value) =>
                      updateEquipmentSlot(definition.slotId, value)
                    }
                    onOpenEnchant={() =>
                      setToolTarget({
                        kind: 'enchant',
                        slotId: definition.slotId,
                      })
                    }
                    onOpenLapine={() =>
                      setToolTarget({
                        kind: 'lapine',
                        slotId: definition.slotId,
                      })
                    }
                  />
                ))}
              </div>
            </section>
          )
        })}
      </div>

      {calculateError && (
        <div className="calculation-result error-result">
          <strong>計算失敗</strong>
          <p>{calculateError}</p>
        </div>
      )}

      {result && (
        <div
          className={`calculation-result ${
            autoCalcStatus === 'scheduled' ||
            autoCalcStatus === 'calculating'
              ? 'calculation-result-stale'
              : ''
          }`}
        >
          <div className="result-summary">
            <strong>
              {effectView === 'combo'
                ? `套裝效果 ${displayedComboEffectLines.length} 條`
                : `總效果 ${displayedTotalEffectLines.length} 條`}
              {effectSearchText.trim() &&
                ` · 搜尋命中 ${searchedEffectLines.length} 條`}
            </strong>

            {result.triggered_combo_ids.length > 0 && (
              <span>
                觸發套裝：{result.triggered_combo_ids.join(', ')}
              </span>
            )}
          </div>

          <div className="effect-display-toolbar">
            <div
              className="effect-view-tabs"
              role="tablist"
              aria-label="效果顯示分頁"
            >
              <button
                type="button"
                role="tab"
                aria-selected={effectView === 'total'}
                className={`effect-view-tab ${
                  effectView === 'total'
                    ? 'effect-view-tab-active'
                    : ''
                }`}
                onClick={() => setEffectView('total')}
              >
                總效果
                <span>{displayedTotalEffectLines.length}</span>
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={effectView === 'combo'}
                className={`effect-view-tab ${
                  effectView === 'combo'
                    ? 'effect-view-tab-active'
                    : ''
                }`}
                onClick={() => setEffectView('combo')}
              >
                套裝效果
                <span>{result.triggered_combo_ids.length}</span>
              </button>
            </div>

            <div className="effect-search-control">
              <input
                type="search"
                value={effectSearchText}
                onChange={(event) =>
                  setEffectSearchText(event.target.value)
                }
                placeholder={
                  effectView === 'combo'
                    ? '搜尋套裝效果：只顯示包含文字的行'
                    : '搜尋總效果：只顯示包含文字的行'
                }
                aria-label="搜尋顯示效果"
              />

              {effectSearchText && (
                <button
                  type="button"
                  className="button button-secondary compact-button"
                  onClick={() => setEffectSearchText('')}
                >
                  清除
                </button>
              )}
            </div>
          </div>

          <div className="effect-display-filter-bar">
            <strong>效果顯示</strong>

            <ToggleButton
              pressed={effectDisplayFilters.hidePhysical}
              className="toggle-button-compact"
              onPressedChange={(hidePhysical) =>
                setEffectDisplayFilters((current) => ({
                  ...current,
                  hidePhysical,
                }))
              }
            >
              隱藏物理
            </ToggleButton>

            <ToggleButton
              pressed={effectDisplayFilters.hideMagical}
              className="toggle-button-compact"
              onPressedChange={(hideMagical) =>
                setEffectDisplayFilters((current) => ({
                  ...current,
                  hideMagical,
                }))
              }
            >
              隱藏魔法
            </ToggleButton>

            <ToggleButton
              pressed={effectDisplayFilters.hideRecognition}
              className="toggle-button-compact"
              onPressedChange={(hideRecognition) =>
                setEffectDisplayFilters((current) => ({
                  ...current,
                  hideRecognition,
                }))
              }
            >
              隱藏辨識 / 解析
            </ToggleButton>
          </div>

          {result.warnings.length > 0 && (
            <div className="warning-box">
              {result.warnings.map((warning, index) => (
                <p key={`${index}-${warning}`}>{warning}</p>
              ))}
            </div>
          )}

          {searchedEffectLines.length > 0 ? (
            <pre
              className={`effect-output ${
                effectView === 'combo'
                  ? 'effect-output-combo'
                  : 'effect-output-total'
              }`}
            >
              {searchedEffectLines.join('\n')}
            </pre>
          ) : (
            <div className="muted result-empty effect-empty-state">
              {effectSearchText.trim()
                ? `沒有包含「${effectSearchText.trim()}」的行。`
                : effectView === 'combo'
                  ? result.triggered_combo_ids.length > 0
                    ? '已觸發套裝，但目前沒有可顯示的套裝效果行。'
                    : '目前沒有觸發套裝效果。'
                  : 'Core 正常回應，但目前輸入沒有產生可顯示效果。'}
            </div>
          )}

          <details className="request-preview">
            <summary>查看這次送出的 request</summary>
            <pre>{JSON.stringify(payload, null, 2)}</pre>
          </details>
        </div>
      )}

      {toolTarget?.kind === 'enchant' &&
        toolDefinition &&
        toolSlot?.item && (
          <EnchantToolModal
            item={toolSlot.item}
            partName={toolDefinition.label}
            currentCards={toolSlot.cards}
            onApply={(enchantSlotId, enchantName) =>
              applyEnchant(
                toolDefinition.slotId,
                enchantSlotId,
                enchantName,
              )
            }
            onClose={() => setToolTarget(null)}
          />
        )}

      {toolTarget?.kind === 'lapine' &&
        toolDefinition &&
        toolSlot?.item && (
          <LapineToolModal
            item={toolSlot.item}
            partName={toolDefinition.label}
            refine={toolSlot.refine}
            onApplyLua={(luaEffect) =>
              applyLapineLua(toolDefinition.slotId, luaEffect)
            }
            onClose={() => setToolTarget(null)}
          />
        )}
    </section>
  )
}

export default function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState('')
  const [autoCalcDock, setAutoCalcDock] =
    useState<AutoCalcDockState>({
      ...EMPTY_AUTO_CALC_DOCK,
    })
  const [damageDock, setDamageDock] =
    useState<DamageDockState>({
      ...EMPTY_DAMAGE_DOCK,
    })
  const runtimeDockRef =
    useRef<HTMLDivElement | null>(null)

  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [items, setItems] = useState<ItemSummary[]>([])
  const [total, setTotal] = useState(0)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const equipmentSearchSequenceRef = useRef(0)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<ItemDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealthError('')

    try {
      const response = await getHealth()
      setHealth(response)
    } catch (error) {
      setHealth(null)
      setHealthError(readableError(error))
    } finally {
      setHealthLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  // A temporary backend disconnect should not require a page refresh.
  // Keep the current React/browser-draft state and retry health in place.
  useEffect(() => {
    if (health?.core_ready === true) {
      return
    }

    const timer = window.setInterval(() => {
      void refreshHealth()
    }, 2500)

    return () => window.clearInterval(timer)
  }, [
    health?.core_ready,
    refreshHealth,
  ])

  // DamagePanel has its own sticky result card.  Measure the real top dock
  // height (it changes when the compact damage line appears/disappears) and
  // expose that height as a CSS variable so the damage card never slides
  // underneath the runtime dock.
  useEffect(() => {
    const node = runtimeDockRef.current

    if (!node) {
      return
    }

    const update = () => {
      const height = Math.ceil(
        node.getBoundingClientRect().height,
      )
      document.documentElement.style.setProperty(
        '--runtime-dock-height',
        `${height}px`,
      )
    }

    update()

    if (
      typeof ResizeObserver === 'undefined'
    ) {
      window.addEventListener('resize', update)
      return () => {
        window.removeEventListener(
          'resize',
          update,
        )
        document.documentElement.style.removeProperty(
          '--runtime-dock-height',
        )
      }
    }

    const observer = new ResizeObserver(update)
    observer.observe(node)

    return () => {
      observer.disconnect()
      document.documentElement.style.removeProperty(
        '--runtime-dock-height',
      )
    }
  }, [])

  const loadDetail = useCallback(async (itemId: number) => {
    setSelectedId(itemId)
    setDetailLoading(true)
    setDetailError('')

    try {
      const response = await getItem(itemId)
      setDetail(response)
    } catch (error) {
      setDetail(null)
      setDetailError(readableError(error))
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    const normalized = query.trim()
    const sequence =
      ++equipmentSearchSequenceRef.current
    const controller = new AbortController()

    setSubmittedQuery(normalized)
    setSearchError('')

    if (
      health?.core_ready !== true ||
      !normalized
    ) {
      setSearching(false)
      setItems([])
      setTotal(0)
      setSelectedId(null)
      setDetail(null)
      setDetailError('')
      return () => controller.abort()
    }

    setSearching(true)

    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const response =
            await searchEquipmentItems(
              normalized,
              controller.signal,
              100,
            )

          if (
            controller.signal.aborted ||
            sequence !==
              equipmentSearchSequenceRef.current
          ) {
            return
          }

          setItems(response.items)
          setTotal(response.total)

          if (response.items.length > 0) {
            void loadDetail(
              response.items[0].item_id,
            )
          } else {
            setSelectedId(null)
            setDetail(null)
            setDetailError('')
          }
        } catch (error) {
          if (
            !controller.signal.aborted &&
            sequence ===
              equipmentSearchSequenceRef.current
          ) {
            setItems([])
            setTotal(0)
            setSelectedId(null)
            setDetail(null)
            setSearchError(
              readableError(error),
            )
          }
        } finally {
          if (
            !controller.signal.aborted &&
            sequence ===
              equipmentSearchSequenceRef.current
          ) {
            setSearching(false)
          }
        }
      })()
    }, 180)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [
    health?.core_ready,
    loadDetail,
    query,
  ])

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">ROITEMSEARCHAPP · WEB DEV</div>
          <h1>RO 裝備資料搜尋</h1>
          <p>
            Desktop 與 Web 共用同一套 Python Core。Stage 21.19 延續 Breakdown 架構，保留防禦後傷害百分比並精簡體種屬階顯示。
          </p>
        </div>
      </header>

      <main className="content">
        <div ref={runtimeDockRef} className="runtime-sticky-dock">
          <div className="runtime-status-row">
            <ApiStatus
              health={health}
              error={healthError}
              loading={healthLoading}
              onRetry={() => void refreshHealth()}
            />
            <AutoCalcTopStatus
              apiReady={health?.core_ready === true}
              state={autoCalcDock}
            />
          </div>

          <CompactDamageDock state={damageDock} />
        </div>

        <Calculator
          apiReady={health?.core_ready === true}
          onAutoCalcDockChange={setAutoCalcDock}
          onDamageDockChange={setDamageDock}
        />

        <section className="search-card">
          <div className="search-form">
            <label htmlFor="item-search">
              裝備多條件即時搜尋
            </label>
            <div className="search-controls search-controls-live">
              <input
                id="item-search"
                type="search"
                value={query}
                onChange={(event) =>
                  setQuery(event.target.value)
                }
                placeholder="例如：時光 力量 STR；空白分隔全部條件"
                autoComplete="off"
              />
              <span className="live-search-status">
                {searching
                  ? '搜尋中…'
                  : submittedQuery
                    ? `${total} 筆`
                    : '輸入即搜尋'}
              </span>
            </div>
            <small className="equipment-search-hint">
              與 Desktop 相同：空白切成多個關鍵字，每個關鍵字都必須命中
              Item ID、裝備名稱或描述。
            </small>
          </div>
        </section>

        <div className="workspace">
          <aside className="results-panel">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">SEARCH RESULTS</div>
                <h2>搜尋結果</h2>
              </div>
              <span className="result-count">
                {submittedQuery || items.length ? `${total} 筆` : '—'}
              </span>
            </div>

            {searchError && <p className="error-text panel-message">{searchError}</p>}

            {!searching && !searchError && items.length === 0 && (
              <p className="muted panel-message">
                輸入裝備名稱、Item ID 或描述；多個條件用空白分隔。
              </p>
            )}

            <div className="result-list">
              {items.map((item) => (
                <ItemResult
                  key={item.item_id}
                  item={item}
                  selected={selectedId === item.item_id}
                  onSelect={(itemId) => void loadDetail(itemId)}
                />
              ))}
            </div>
          </aside>

          <DetailPanel
            detail={detail}
            loading={detailLoading}
            error={detailError}
          />
        </div>
      </main>
    </div>
  )
}
