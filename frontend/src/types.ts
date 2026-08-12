export interface ApiHealth {
  ok: boolean
  core_ready: boolean
  startup_error: string | null
  data_dir: string
  include_kro: boolean
  item_count: number
  equipment_block_count: number
  skill_entry_count: number
  skill_name_count: number
  job_count: number
  api_version: string
}

export interface ItemSummary {
  item_id: number
  name: string
  base_name: string
  kr_name: string
  slot: number
  is_equipment: boolean

  // Stage 21 equipment metadata. Older Web Builds may not contain these.
  description_preview?: string
  equip_type?: string
  weapon_type?: number | null
  blocks_left_hand?: boolean
}

export interface ItemSearchResponse {
  query: string
  total: number
  offset: number
  limit: number
  items: ItemSummary[]
}

export interface ItemDetail extends ItemSummary {
  description: unknown[]
  equipment_block?: string | null
}

export interface JobSummary {
  job_id: number | string
  name: string
  code: string
  job_name: string
  job_name_online: string
  selectskill: string
  point: string
  pure_job_ids: number[]
  job_bonus: number[]
}

export interface JobsResponse {
  total: number
  jobs: JobSummary[]
}

export interface EquipmentSlotPayload {
  part_name: string
  slot_id: number
  equip_name: string
  grade: number
  cards: string[]
  note: string
}

export interface CalculatePayload {
  get_values: Record<number, number>
  refine_inputs: Record<number, number>
  slots: EquipmentSlotPayload[]
  enabled_skill_names: string[]
  hide_unrecognized: boolean
  hide_physical: boolean
  hide_magical: boolean
  show_source: boolean
  sort_mode: string
  context_variables: Record<string, number | string | boolean>
  enabled_skill_levels: Record<number, number>
}

export interface EffectEntry {
  value: number
  source: string
}

export interface EffectTotal {
  key: string
  unit: string
  total: number
  entries: EffectEntry[]
}

export interface CalculateResponse {
  effects: EffectTotal[]
  combined_lines: string[]
  combo_lines: string[]
  triggered_combo_ids: number[]
  warnings: string[]
}


export interface SkillEntrySummary {
  name: string
  type: string
  buff: unknown
  job: unknown
  exclusive: unknown
  code?: unknown
}

export interface SkillMapSummary {
  skill_id: number
  name: string
}

export interface SkillEntriesResponse {
  source: 'entries'
  query: string
  total: number
  offset: number
  limit: number
  skills: SkillEntrySummary[]
}

export interface SkillMapResponse {
  source: 'map'
  query: string
  total: number
  offset: number
  limit: number
  skills: SkillMapSummary[]
}

export interface CalculationMetaOption {
  value: number
  label: string
}

export interface CalculationMeta {
  elements: CalculationMetaOption[]
  races: CalculationMetaOption[]
  sizes: CalculationMetaOption[]
  classes: CalculationMetaOption[]
  extended_stat_gids: Record<string, number>
}

export interface AdvancedCharacterState {
  pow: number
  sta: number
  wis: number
  spl: number
  con: number
  crt: number
  enabledSkillNames: string[]
  enabledSkillLevels: Record<number, number>
  targetElement: number
  targetRace: number
  targetSize: number
  targetClass: number
}

export interface EnchantMaterial {
  raw_name: string
  name: string
  item_id: number | null
  count: number
}

export interface EnchantEntry {
  type: 'enchant' | 'perfect' | 'upgrade' | 'perfect_upgrade' | 'random_upgrade'
  name: string
  output_name: string
  grade?: number
  rate_raw: number | null
  rate_percent: number
  zeny: number
  materials: EnchantMaterial[]
  from_name?: string
  to_name?: string
}

export interface EnchantSlotInfo {
  slot_id: number
  entries: EnchantEntry[]
}

export interface EnchantToolItem {
  item_id: number
  name: string
  display_name: string
  kr_name: string
  table_id: number
  slot_order: number[]
  slots: EnchantSlotInfo[]
  reset: {
    enable: boolean
    reset_rate: number
    enchant_rate: number
    materials: EnchantMaterial[]
  } | null
}

export interface EnchantRollResponse {
  success: boolean
  mode: 'enchant' | 'random_upgrade'
  item_id: number
  table_id: number
  slot_id: number
  current_enchant: string
  roll: number | null
  roll_range: number
  candidates: Array<{
    type: string
    rate: number
    output_name: string
    from_name?: string
    effective_rate_percent: number
  }>
  result: {
    type: string
    rate: number
    output_name: string
    from_name?: string
  } | null
}

export interface LapineProfileRow {
  group: string
  option_code: string
  probability: number
  min_value: number
  max_value: number
  value_choices: number[]
  display_preview: string
  lua_preview: string
}

export interface LapineBoxInfo {
  key: string
  source_item_id: number
  source_name: string
  need_refine_min: number
  need_refine_max: number
  need_option_num_min: number
  not_socket_enchant_item: boolean
  need_source_string: string
  profile: {
    title: string
    box_item_id: number | null
    updated_at: string | null
    groups: Array<{ name: string; probability: number }>
    rows: LapineProfileRow[]
  } | null
}

export interface LapineToolItem {
  item_id: number
  name: string
  display_name: string
  kr_name: string
  boxes: LapineBoxInfo[]
}

export interface LapineRollResponse {
  success: boolean
  item_id: number
  table_key: string
  results: Array<{
    group: string
    option_code: string
    value: number
    display_text: string
    lua_effect: string
    success: true
  }>
  attempts: unknown[]
  lua_effect: string
}


export interface BuffListEntry {
  source_index: number
  name: string
  type: string
  buff: unknown
  job_ids: string[]
  exclusive: unknown
  job_match: boolean
}

export interface BuffListResponse {
  source: 'data/all_skill_entries.py'
  query: string
  job_code: string
  total: number
  entries: BuffListEntry[]
}


export interface DamageSkillSummary {
  skill_id: number
  code: string
  name: string
  attack_type: 'physical' | 'magic' | 'd_b' | 'shield' | string
  default_level: number
  formula: string
  hits: string
  element: number
  critical_hit: number
  has_combo: boolean
  source_index: number
}

export interface DamageSkillsResponse {
  query: string
  job_id: number
  total: number
  skills: DamageSkillSummary[]
}

export interface MonsterDamageState {
  size: number
  element: number
  elementLv: number
  race: number
  classId: number
  def: number
  defc: number
  res: number
  mdef: number
  mdefc: number
  mres: number
  damageMultiplierPercent: number
  betelgeuseReductionPercent: number
}

export interface SpecialDamageState {
  wanzih: boolean
  poisonWeak: boolean
  magicPoison: boolean
  attributeSeal: boolean
  sneakAttack: boolean
  sporeAttack: boolean
  darkCrow: boolean
  rushAttack: boolean
  oleumAttack: boolean
  lexAeterna: boolean
  totalSrl: number
}

export interface DamageState {
  skillId: number | null
  skillLevel: number
  attackElement: number | null
  formulaOverride: string
  special: SpecialDamageState
  mhp: number
  msp: number
  mhpNow: number
  mspNow: number
  monster: MonsterDamageState
}

export interface DamageStep {
  name: string
  value: number
  mode: number | string | null
}

export interface DamageSegment {
  round: number
  label: string
  formula: string
  formula_expanded: string
  skill_result: number
  damage_by_hit_min: number
  damage_by_hit: number
  total_damage_min: number
  total_damage: number
  times: number
  user_attack_element: number
  steps: DamageStep[]
}


export interface DamageBreakdownRow {
  key: string
  label: string
  value: number
  unit: string
  digits?: number
}

export interface DamageBreakdown {
  mode: 'physical' | 'magic' | 'd_b' | 'shield' | string
  label: string
  rows: DamageBreakdownRow[]
}

export interface DamageResult {
  coverage: string
  skill: {
    skill_id: number
    name: string
    code: string
    level: number
    attack_type: string
    attack_element: number
    formula: string
    formula_source: 'csv' | 'special' | 'override' | string
    hits: number
  }
  monster: Record<string, number>
  base: {
    front_atk: number
    weapon_atk_min: number
    weapon_atk_max: number
    magic_min: number
    magic_max: number
    total_patk: number
    total_smatk: number
    def_multiplier: number
    res_multiplier: number
    mdef_multiplier: number
    mres_multiplier: number
  }
  breakdown?: DamageBreakdown
  segments: DamageSegment[]
  total_damage_min: number
  total_damage: number
  warnings: string[]
}

export interface DamageCalculateResponse {
  effect: CalculateResponse
  damage: DamageResult
}


export interface MonsterPresetSummary {
  source_index: number
  name: string
  id: number
}

export interface MonsterPresetsResponse {
  source: 'data/monsters.json'
  query: string
  total: number
  items: MonsterPresetSummary[]
}

export interface MonsterLookupData {
  monster_id: number
  name: string
  level: number
  element_id: number
  element_lv: number
  size_id: number
  race_id: number
  class_id: number
  def_before: number
  mdef_before: number
  def_after: number
  mdef_after: number
  res: number
  mres: number
  monster_f_atk: number
  monster_c_atk: number
  monster_f_matk: number
  monster_c_matk: number
}

export interface MonsterLookupResponse {
  monster_id: number
  source: 'cache' | 'api'
  monster: MonsterLookupData
}


export interface SkillTreeRequirement {
  code: string
  level: number
  name: string
}

export interface SkillTreeNode {
  code: string
  skill_id: number | null
  name: string
  max_level: number
  quest_skill: boolean
  requires: SkillTreeRequirement[]
  region: number
  depth: number
  position: number
  source_index: number
}

export interface SkillTreeGroup {
  index: number
  jobs: string[]
  label: string
  max_points: number
}

export interface SkillTreeResponse {
  job_id: number
  job_key: string
  job_name: string
  job_chain: string[]
  groups: SkillTreeGroup[]
  nodes: SkillTreeNode[]
}

export interface SkillTreeChangeResponse {
  job_id: number
  levels: Record<string, number>
  note: string
  message: string
  groups: SkillTreeGroup[]
}

export interface RrfImportResponse {
  source: 'rrf' | 'dump'
  desktop_json: Record<string, unknown>
  meta: {
    character_name: string
    job_id: number | null
    main_job_id: number | string | null
    job_name: string
    skill_count: number
    buff_count: number
  }
  warnings: string[]
}


export interface StatusSettingsState {
  mhpInput: number
  mspInput: number
  useLogoutHpsp: boolean
  hpPercent: number
  spPercent: number
}

export interface HpSpStatusResult {
  job_base_hp: number
  job_base_sp: number
  mhp_input: number
  msp_input: number
  adjusted_mhp_input: number
  adjusted_msp_input: number
  use_logout_values: boolean
  hp_flat: number
  sp_flat: number
  hp_percent_bonus: number
  sp_percent_bonus: number
  mhp: number
  msp: number
  mhp_now: number
  msp_now: number
  hp_current_percent: number
  sp_current_percent: number
  source_hp: string
  source_sp: string
}

export interface AspdStatusResult {
  supported: boolean
  value: number | null
  attacks_per_second: number | null
  message: string
  mode: string
  has_shield: boolean
  right_weapon_type: number
  left_weapon_type: number
  cat1_rate: number
  cat1_flat: number
  cat2_rate: number
  cat2_flat: number
}

export interface CharacterStatusResult {
  hpsp: HpSpStatusResult
  aspd: AspdStatusResult
  stats: {
    base_agi: number
    job_agi: number
    equip_agi: number
    total_agi: number
    base_dex: number
    job_dex: number
    equip_dex: number
    total_dex: number
    base_vit: number
    job_vit: number
    equip_vit: number
    total_vit: number
    base_int: number
    job_int: number
    equip_int: number
    total_int: number
  }
  job: {
    job_id: number
    base_lv: number
    name: string
    hpsp_table_available: boolean
    mhp_msp_display: boolean
    hpsp_input_widget: boolean
  }
}

export interface StatusCalculateResponse {
  effect: CalculateResponse
  status: CharacterStatusResult
}

export interface StatusDamageCalculateResponse {
  effect: CalculateResponse
  status: CharacterStatusResult
  damage: DamageResult
}


export interface EquipmentSearchResponse {
  query: string
  keywords: string[]
  match_mode: 'all'
  search_fields: string[]
  total: number
  offset: number
  limit: number
  items: ItemSummary[]
}

export interface EquipmentItemResponse {
  item: ItemSummary
}


// === STAGE 21.9 NOTE EDITOR TYPES ===

export interface NoteParsePayload {
  note: string
  slot_id: number
  grade: number
  get_values: Record<number, number>
  refine_inputs: Record<number, number>
  context_variables: Record<
    string,
    number | string | boolean
  >
  enabled_skill_levels: Record<number, number>
}

export interface NoteParseResponse {
  raw: string
  lines: string[]
  text: string
}

export interface NoteFunctionArg {
  index: number
  name: string
  map: string
  type: string
  fixed_value: string | null
  placeholder: string
}

export interface NoteFunctionDefinition {
  name: string
  desc: string
  syntax: string
  separator: boolean
  args: NoteFunctionArg[]
}

export interface NoteConditionValue {
  key: string
  label: string
  syntax: string
  keywords: string
}

export interface NoteConditionOperator {
  value: string
  label: string
}

export interface NoteControlFlow {
  key: string
  display: string
  desc: string
  template: string
}

export interface NoteFunctionCatalogResponse {
  query: string
  total: number
  functions: NoteFunctionDefinition[]
  condition_values: NoteConditionValue[]
  condition_operators: NoteConditionOperator[]
  control_flow: NoteControlFlow[]
}

export interface NoteFunctionMapOption {
  value: number | string
  label: string
}

export interface NoteFunctionMapResponse {
  map_name: string
  query: string
  total: number
  options: NoteFunctionMapOption[]
}
