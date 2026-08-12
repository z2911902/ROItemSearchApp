import type {
  ApiHealth,
  CalculatePayload,
  CalculateResponse,
  ItemDetail,
  ItemSearchResponse,
  EquipmentItemResponse,
  EquipmentSearchResponse,
  JobsResponse,
  CalculationMeta,
  EnchantRollResponse,
  EnchantToolItem,
  LapineRollResponse,
  LapineToolItem,
  SkillEntriesResponse,
  SkillMapResponse,
  BuffListResponse,
  DamageCalculateResponse,
  MonsterLookupResponse,
  MonsterPresetsResponse,
  RrfImportResponse,
  SkillTreeChangeResponse,
  SkillTreeResponse,
  StatusCalculateResponse,
  StatusDamageCalculateResponse,
  StatusSettingsState,
  DamageSkillsResponse,
  DamageState,
  NoteParsePayload,
  NoteParseResponse,
  NoteFunctionCatalogResponse,
  NoteFunctionMapResponse,
} from './types'

const configuredBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim()
const API_BASE = configuredBase.replace(/\/+$/, '')

function url(path: string): string {
  return `${API_BASE}${path}`
}

async function fetchJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`

    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string' && body.detail.trim()) {
        detail = body.detail
      }
    } catch {
      // Keep HTTP status text when response is not JSON.
    }

    throw new Error(detail)
  }

  return (await response.json()) as T
}

export function getHealth(signal?: AbortSignal): Promise<ApiHealth> {
  return fetchJson<ApiHealth>('/api/health', { signal })
}

export function searchItems(
  query: string,
  signal?: AbortSignal,
): Promise<ItemSearchResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: '50',
  })

  return fetchJson<ItemSearchResponse>(
    `/api/items/search?${params.toString()}`,
    { signal },
  )
}

export function getItem(
  itemId: number,
  signal?: AbortSignal,
): Promise<ItemDetail> {
  return fetchJson<ItemDetail>(`/api/items/${itemId}`, { signal })
}

export function getJobs(signal?: AbortSignal): Promise<JobsResponse> {
  return fetchJson<JobsResponse>('/api/jobs', { signal })
}

export function calculateEquipment(
  payload: CalculatePayload,
  signal?: AbortSignal,
): Promise<CalculateResponse> {
  return fetchJson<CalculateResponse>('/api/calculate', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}


export function searchSkillEntries(
  query: string,
  signal?: AbortSignal,
): Promise<SkillEntriesResponse> {
  const params = new URLSearchParams({
    source: 'entries',
    q: query,
    limit: '200',
  })
  return fetchJson<SkillEntriesResponse>(
    `/api/skills?${params.toString()}`,
    { signal },
  )
}

export function searchSkillMap(
  query: string,
  signal?: AbortSignal,
): Promise<SkillMapResponse> {
  const params = new URLSearchParams({
    source: 'map',
    q: query,
    limit: '100',
  })
  return fetchJson<SkillMapResponse>(
    `/api/skills?${params.toString()}`,
    { signal },
  )
}

export function getCalculationMeta(
  signal?: AbortSignal,
): Promise<CalculationMeta> {
  return fetchJson<CalculationMeta>('/api/meta/calculation', { signal })
}

export function getEnchantToolItem(
  itemId: number,
  signal?: AbortSignal,
): Promise<EnchantToolItem> {
  return fetchJson<EnchantToolItem>(
    `/api/tools/enchant/items/${itemId}`,
    { signal },
  )
}

export function rollEnchant(
  itemId: number,
  slotId: number,
  currentEnchant: string,
): Promise<EnchantRollResponse> {
  return fetchJson<EnchantRollResponse>('/api/tools/enchant/roll', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      item_id: itemId,
      slot_id: slotId,
      current_enchant: currentEnchant,
    }),
  })
}

export function getLapineToolItem(
  itemId: number,
  showAll = false,
  signal?: AbortSignal,
): Promise<LapineToolItem> {
  const params = new URLSearchParams({
    show_all: String(showAll),
  })
  return fetchJson<LapineToolItem>(
    `/api/tools/lapine/items/${itemId}?${params.toString()}`,
    { signal },
  )
}

export function rollLapine(
  itemId: number,
  tableKey: string,
): Promise<LapineRollResponse> {
  return fetchJson<LapineRollResponse>('/api/tools/lapine/roll', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      item_id: itemId,
      table_key: tableKey,
    }),
  })
}


export function getBuffEntries(
  query = '',
  jobCode = '',
  signal?: AbortSignal,
): Promise<BuffListResponse> {
  const params = new URLSearchParams({
    q: query,
    job_code: jobCode,
  })
  return fetchJson<BuffListResponse>(
    `/api/buffs?${params.toString()}`,
    { signal },
  )
}


export function getDamageSkills(
  jobId: number,
  query = '',
  signal?: AbortSignal,
): Promise<DamageSkillsResponse> {
  const params = new URLSearchParams({
    job_id: String(jobId),
    q: query,
    limit: '500',
  })
  return fetchJson<DamageSkillsResponse>(
    `/api/damage/skills?${params.toString()}`,
    { signal },
  )
}

export function calculateDamage(
  equipment: CalculatePayload,
  state: DamageState,
  signal?: AbortSignal,
): Promise<DamageCalculateResponse> {
  return fetchJson<DamageCalculateResponse>('/api/damage/calculate', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      equipment,
      skill_id: state.skillId,
      skill_level: state.skillLevel,
      attack_element: state.attackElement,
      formula_override: state.formulaOverride,
      special: {
        wanzih: state.special.wanzih,
        poison_weak: state.special.poisonWeak,
        magic_poison: state.special.magicPoison,
        attribute_seal: state.special.attributeSeal,
        sneak_attack: state.special.sneakAttack,
        spore_attack: state.special.sporeAttack,
        dark_crow: state.special.darkCrow,
        rush_attack: state.special.rushAttack,
        oleum_attack: state.special.oleumAttack,
        lex_aeterna: state.special.lexAeterna,
        total_srl: state.special.totalSrl,
      },
      mhp: state.mhp,
      msp: state.msp,
      mhp_now: state.mhpNow,
      msp_now: state.mspNow,
      monster: {
        size: state.monster.size,
        element: state.monster.element,
        element_lv: state.monster.elementLv,
        race: state.monster.race,
        class: state.monster.classId,
        def: state.monster.def,
        defc: state.monster.defc,
        res: state.monster.res,
        mdef: state.monster.mdef,
        mdefc: state.monster.mdefc,
        mres: state.monster.mres,
        damage_multiplier_percent: state.monster.damageMultiplierPercent,
        betelgeuse_reduction_percent:
          state.monster.betelgeuseReductionPercent,
      },
    }),
  })
}


export function getMonsterPresets(
  query = '',
  limit = 500,
  signal?: AbortSignal,
): Promise<MonsterPresetsResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  })
  return fetchJson<MonsterPresetsResponse>(
    `/api/monsters/presets?${params.toString()}`,
    { signal },
  )
}

export function getMonsterDetail(
  monsterId: number,
  refresh = false,
  signal?: AbortSignal,
): Promise<MonsterLookupResponse> {
  const params = new URLSearchParams({
    refresh: String(refresh),
  })
  return fetchJson<MonsterLookupResponse>(
    `/api/monsters/${monsterId}?${params.toString()}`,
    { signal },
  )
}


export function getSkillTree(
  jobId: number,
  signal?: AbortSignal,
): Promise<SkillTreeResponse> {
  return fetchJson<SkillTreeResponse>(
    `/api/skill-tree/${jobId}`,
    { signal },
  )
}

export function changeSkillTreeLevel(
  jobId: number,
  levels: Record<string, number>,
  code: string,
  level: number,
  signal?: AbortSignal,
): Promise<SkillTreeChangeResponse> {
  return fetchJson<SkillTreeChangeResponse>(
    '/api/skill-tree/change',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, levels, code, level }),
      signal,
    },
  )
}

export function importRrf(
  filename: string,
  contentBase64: string,
): Promise<RrfImportResponse> {
  return fetchJson<RrfImportResponse>(
    '/api/rrf/import',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename,
        content_base64: contentBase64,
      }),
    },
  )
}


export function calculateStatus(
  equipment: CalculatePayload,
  status: StatusSettingsState,
  signal?: AbortSignal,
): Promise<StatusCalculateResponse> {
  return fetchJson<StatusCalculateResponse>('/api/status/calculate', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      equipment,
      status: {
        mhp_input: status.mhpInput,
        msp_input: status.mspInput,
        use_logout_hpsp: status.useLogoutHpsp,
        hp_percent: status.hpPercent,
        sp_percent: status.spPercent,
      },
    }),
  })
}

export function calculateStatusDamage(
  equipment: CalculatePayload,
  state: DamageState,
  status: StatusSettingsState,
  signal?: AbortSignal,
): Promise<StatusDamageCalculateResponse> {
  return fetchJson<StatusDamageCalculateResponse>('/api/status/damage', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      equipment,
      status: {
        mhp_input: status.mhpInput,
        msp_input: status.mspInput,
        use_logout_hpsp: status.useLogoutHpsp,
        hp_percent: status.hpPercent,
        sp_percent: status.spPercent,
      },
      skill_id: state.skillId,
      skill_level: state.skillLevel,
      attack_element: state.attackElement,
      formula_override: state.formulaOverride,
      special: {
        wanzih: state.special.wanzih,
        poison_weak: state.special.poisonWeak,
        magic_poison: state.special.magicPoison,
        attribute_seal: state.special.attributeSeal,
        sneak_attack: state.special.sneakAttack,
        spore_attack: state.special.sporeAttack,
        dark_crow: state.special.darkCrow,
        rush_attack: state.special.rushAttack,
        oleum_attack: state.special.oleumAttack,
        lex_aeterna: state.special.lexAeterna,
        total_srl: state.special.totalSrl,
      },
      monster: {
        size: state.monster.size,
        element: state.monster.element,
        element_lv: state.monster.elementLv,
        race: state.monster.race,
        class: state.monster.classId,
        def: state.monster.def,
        defc: state.monster.defc,
        res: state.monster.res,
        mdef: state.monster.mdef,
        mdefc: state.monster.mdefc,
        mres: state.monster.mres,
        damage_multiplier_percent:
          state.monster.damageMultiplierPercent,
        betelgeuse_reduction_percent:
          state.monster.betelgeuseReductionPercent,
      },
    }),
  })
}


export function searchEquipmentItems(
  query: string,
  signal?: AbortSignal,
  limit = 50,
): Promise<EquipmentSearchResponse> {
  const params = new URLSearchParams({
    q: query,
    offset: '0',
    limit: String(limit),
  })
  return fetchJson<EquipmentSearchResponse>(
    `/api/equipment/search?${params.toString()}`,
    { signal },
  )
}

export function getEquipmentItemMeta(
  itemId: number,
  signal?: AbortSignal,
): Promise<EquipmentItemResponse> {
  return fetchJson<EquipmentItemResponse>(
    `/api/equipment/items/${itemId}`,
    { signal },
  )
}


// === STAGE 21.9 NOTE EDITOR API ===

export function parseNote(
  payload: NoteParsePayload,
  signal?: AbortSignal,
): Promise<NoteParseResponse> {
  return fetchJson<NoteParseResponse>(
    '/api/note/parse',
    {
      method: 'POST',
      signal,
      headers: {
        'Content-Type':
          'application/json',
      },
      body: JSON.stringify(payload),
    },
  )
}

export function getNoteFunctions(
  query = '',
  signal?: AbortSignal,
): Promise<NoteFunctionCatalogResponse> {
  const params = new URLSearchParams({
    q: query,
  })

  return fetchJson<NoteFunctionCatalogResponse>(
    `/api/note/functions?${params.toString()}`,
    { signal },
  )
}

export function getNoteFunctionMap(
  mapName: string,
  query = '',
  limit = 200,
  signal?: AbortSignal,
): Promise<NoteFunctionMapResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  })

  return fetchJson<NoteFunctionMapResponse>(
    `/api/note/maps/${encodeURIComponent(
      mapName,
    )}?${params.toString()}`,
    { signal },
  )
}
