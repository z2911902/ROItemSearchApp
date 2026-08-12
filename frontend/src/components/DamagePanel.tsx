// === STAGE 21.17 DESKTOP DAMAGE BREAKDOWN PANEL ===
import { useEffect, useMemo, useState } from 'react'
import { getCalculationMeta, getDamageSkills, getMonsterDetail, getMonsterPresets } from '../api'
import ToggleButton from './ToggleButton'
import type {
  CalculationMeta,
  DamageResult,
  DamageSkillSummary,
  DamageState,
  MonsterLookupData,
  MonsterPresetSummary,
} from '../types'

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function intValue(value: string, fallback = 0): number {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function floatValue(value: string, fallback = 0): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function damageText(min: number, max: number): string {
  if (min === max) return max.toLocaleString()
  return `${min.toLocaleString()} ~ ${max.toLocaleString()}`
}

function breakdownValue(
  value: number,
  unit: string,
  digits?: number,
): string {
  const fractionDigits =
    digits ??
    (
      Number.isInteger(value)
        ? 0
        : 2
    )

  const formatted =
    value.toLocaleString(
      undefined,
      {
        minimumFractionDigits:
          fractionDigits,
        maximumFractionDigits:
          fractionDigits,
      },
    )

  return `${formatted}${unit}`
}

function FieldNumber({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(floatValue(event.target.value))}
      />
    </label>
  )
}

export default function DamagePanel({
  apiReady,
  jobId,
  value,
  onChange,
  result,
  calculating,
}: {
  apiReady: boolean
  jobId: number | null
  value: DamageState
  onChange: (value: DamageState) => void
  result: DamageResult | null
  calculating: boolean
}) {
  const [skills, setSkills] = useState<DamageSkillSummary[]>([])
  const [skillQuery, setSkillQuery] = useState('')
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillsError, setSkillsError] = useState('')
  const [meta, setMeta] = useState<CalculationMeta | null>(null)
  const [metaError, setMetaError] = useState('')
  const [monsterPresets, setMonsterPresets] = useState<MonsterPresetSummary[]>([])
  const [monsterQuery, setMonsterQuery] = useState('')
  const [monsterIdInput, setMonsterIdInput] = useState('')
  const [monsterLoading, setMonsterLoading] = useState(false)
  const [monsterError, setMonsterError] = useState('')
  const [monsterLoaded, setMonsterLoaded] = useState<{
    id: number
    name: string
    source: 'cache' | 'api'
  } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        setMeta(await getCalculationMeta(controller.signal))
      } catch (error) {
        if (!controller.signal.aborted) setMetaError(readableError(error))
      }
    })()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!apiReady) {
      setMonsterPresets([])
      return
    }

    const controller = new AbortController()
    void (async () => {
      try {
        const response = await getMonsterPresets(
          '',
          1000,
          controller.signal,
        )
        setMonsterPresets(response.items)
      } catch (error) {
        if (!controller.signal.aborted) {
          setMonsterPresets([])
          setMonsterError(readableError(error))
        }
      }
    })()

    return () => controller.abort()
  }, [apiReady])

  useEffect(() => {
    if (!apiReady) {
      setSkills([])
      return
    }

    const query = skillQuery.trim()

    if (!query && jobId === null) {
      setSkills([])
      return
    }

    const controller = new AbortController()

    void (async () => {
      setSkillsLoading(true)
      setSkillsError('')

      try {
        // Empty search keeps the normal current-job selector.
        // Any typed search intentionally uses job_id=0 so it can find
        // skills from every profession.
        const response =
          await getDamageSkills(
            query
              ? 0
              : jobId ?? 0,
            query,
            controller.signal,
          )

        if (!controller.signal.aborted) {
          setSkills(response.skills)
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setSkills([])
          setSkillsError(
            readableError(error),
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setSkillsLoading(false)
        }
      }
    })()

    return () => controller.abort()
  }, [
    apiReady,
    jobId,
    skillQuery,
  ])

  const visibleSkills = skills

  const visibleMonsterPresets = useMemo(() => {
    const query = monsterQuery.trim().toLowerCase()
    if (!query) return monsterPresets
    return monsterPresets.filter((monster) =>
      `${monster.id} ${monster.name}`.toLowerCase().includes(query),
    )
  }, [monsterPresets, monsterQuery])

  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.skill_id === value.skillId) ?? null,
    [skills, value.skillId],
  )

  function selectSkill(skill: DamageSkillSummary | null) {
    if (!skill) {
      onChange({ ...value, skillId: null })
      return
    }
    onChange({
      ...value,
      skillId: skill.skill_id,
      skillLevel: Math.max(1, skill.default_level),
      attackElement: skill.element,
      formulaOverride: '',
    })
  }

  function updateMonster(patch: Partial<DamageState['monster']>) {
    onChange({
      ...value,
      monster: {
        ...value.monster,
        ...patch,
      },
    })
  }

  function applyMonsterData(monster: MonsterLookupData) {
    onChange({
      ...value,
      monster: {
        ...value.monster,
        size: monster.size_id,
        element: monster.element_id,
        elementLv: monster.element_lv,
        race: monster.race_id,
        classId: monster.class_id,
        def: monster.def_after,
        defc: monster.def_before,
        res: monster.res,
        mdef: monster.mdef_after,
        mdefc: monster.mdef_before,
        mres: monster.mres,
      },
    })
  }

  async function loadMonster(monsterId: number) {
    if (!apiReady || monsterId <= 0) {
      return
    }

    setMonsterLoading(true)
    setMonsterError('')

    try {
      const response = await getMonsterDetail(monsterId)
      applyMonsterData(response.monster)
      setMonsterLoaded({
        id: response.monster_id,
        name: response.monster.name || `Monster ${response.monster_id}`,
        source: response.source,
      })
      setMonsterIdInput(String(response.monster_id))
    } catch (error) {
      setMonsterError(readableError(error))
    } finally {
      setMonsterLoading(false)
    }
  }

  return (
    <section className="damage-panel">
      <div className="section-heading">
        <div>
          <div className="eyebrow">STAGE 18 · SHARED MONSTER LOOKUP</div>
          <h2>技能 / 魔物 / 傷害</h2>
          <p>
            技能來自 skillneme.csv；怪物可直接從 Desktop 同源 presets/cache/API 套用，套用後 Damage Core 自動重算。
          </p>
        </div>
        <span className={`badge badge-large ${calculating ? 'damage-live' : ''}`}>
          {value.skillId === null
            ? '尚未選傷害技能'
            : calculating
              ? '傷害更新中…'
              : '自動傷害已啟用'}
        </span>
      </div>

      <div className="damage-layout">
        <div className="damage-controls">
          <section className="damage-control-card">
            <h3>技能選擇</h3>
            <input
              className="damage-skill-filter"
              type="search"
              value={skillQuery}
              onChange={(event) => setSkillQuery(event.target.value)}
              placeholder="搜尋全部職業技能名稱 / Code / Skill ID"
            />
            {skillsLoading && <p className="muted compact-message">搜尋技能…</p>}
            {skillsError && <p className="error-text compact-message">{skillsError}</p>}
            <select
              className="damage-skill-select"
              value={value.skillId ?? ''}
              onChange={(event) => {
                const id = intValue(event.target.value, 0)
                selectSkill(skills.find((skill) => skill.skill_id === id) ?? null)
              }}
            >
              <option value="">不計算最終傷害</option>
              {selectedSkill &&
                !visibleSkills.some(
                  (skill) => skill.skill_id === selectedSkill.skill_id,
                ) && (
                  <option value={selectedSkill.skill_id}>
                    {selectedSkill.name} ({selectedSkill.skill_id})
                  </option>
                )}
              {visibleSkills.map((skill) => (
                <option key={skill.skill_id} value={skill.skill_id}>
                  {skill.name} ({skill.skill_id})
                </option>
              ))}
              {value.skillId !== null && !selectedSkill && (
                <option value={value.skillId}>Skill ID {value.skillId}</option>
              )}
            </select>

            {selectedSkill && (
              <div className="damage-skill-meta">
                <span>{selectedSkill.attack_type}</span>
                <span>hits: {selectedSkill.hits}</span>
                {selectedSkill.has_combo && <span>combo</span>}
                <code>{selectedSkill.formula || '無公式'}</code>
              </div>
            )}

            {selectedSkill && (
              <label className="field damage-formula-field">
                <span>技能公式（可覆寫）</span>
                <textarea
                  rows={3}
                  spellCheck={false}
                  value={value.formulaOverride}
                  onChange={(event) =>
                    onChange({
                      ...value,
                      formulaOverride: event.target.value,
                    })
                  }
                  placeholder={selectedSkill.formula || 'skillneme.csv 無公式'}
                />
                <small>
                  留空使用 CSV / 特殊公式；修改後直接交給同一個 Python Formula Core，自動重算。
                </small>
                {value.formulaOverride && (
                  <button
                    className="text-button"
                    type="button"
                    onClick={() =>
                      onChange({
                        ...value,
                        formulaOverride: '',
                      })
                    }
                  >
                    還原 CSV / 特殊公式
                  </button>
                )}
              </label>
            )}

            <div className="damage-short-grid">
              <FieldNumber
                label="技能等級"
                value={value.skillLevel}
                min={0}
                max={100}
                onChange={(skillLevel) => onChange({ ...value, skillLevel })}
              />
              <label className="field">
                <span>攻擊屬性</span>
                <select
                  value={value.attackElement ?? ''}
                  onChange={(event) =>
                    onChange({
                      ...value,
                      attackElement:
                        event.target.value === ''
                          ? null
                          : intValue(event.target.value),
                    })
                  }
                >
                  <option value="">技能預設</option>
                  {(meta?.elements ?? [])
                    .filter((row) => row.value <= 9)
                    .map((row) => (
                      <option key={row.value} value={row.value}>{row.label}</option>
                    ))}
                </select>
              </label>
            </div>
          </section>

          <section className="damage-control-card">
            <h3>魔物狀態</h3>

            <div className="monster-lookup-box">
              <div className="monster-lookup-heading">
                <div>
                  <strong>怪物查詢</strong>
                  <small>data/monsters.json → data/monster 快取 → Divine Pride</small>
                </div>
                {monsterLoaded && (
                  <span className="badge">
                    {monsterLoaded.source === 'cache' ? '快取' : 'API'}
                  </span>
                )}
              </div>

              <input
                type="search"
                value={monsterQuery}
                onChange={(event) => setMonsterQuery(event.target.value)}
                placeholder="搜尋預設怪物名稱 / ID"
              />

              <select
                value=""
                disabled={!apiReady || monsterLoading}
                onChange={(event) => {
                  const monsterId = intValue(event.target.value, 0)
                  if (monsterId > 0) {
                    void loadMonster(monsterId)
                  }
                }}
              >
                <option value="">
                  {monsterLoading
                    ? '怪物資料載入中…'
                    : `選擇預設怪物（${visibleMonsterPresets.length}）`}
                </option>
                {visibleMonsterPresets.map((monster) => (
                  <option key={monster.id} value={monster.id}>
                    {monster.name} ({monster.id})
                  </option>
                ))}
              </select>

              <form
                className="monster-id-row"
                onSubmit={(event) => {
                  event.preventDefault()
                  const monsterId = intValue(monsterIdInput, 0)
                  if (monsterId > 0) {
                    void loadMonster(monsterId)
                  }
                }}
              >
                <input
                  type="number"
                  min={1}
                  value={monsterIdInput}
                  onChange={(event) => setMonsterIdInput(event.target.value)}
                  placeholder="直接輸入怪物 ID"
                />
                <button
                  className="button button-secondary"
                  type="submit"
                  disabled={
                    !apiReady ||
                    monsterLoading ||
                    intValue(monsterIdInput, 0) <= 0
                  }
                >
                  {monsterLoading ? '查詢中…' : '查詢 ID'}
                </button>
              </form>

              {monsterLoaded && (
                <p className="monster-loaded-line">
                  已套用：<strong>{monsterLoaded.name}</strong>
                  {' · '}ID {monsterLoaded.id}
                  {' · '}選擇後已自動更新傷害
                </p>
              )}
              {monsterError && (
                <p className="error-text compact-message">{monsterError}</p>
              )}
            </div>

            {metaError && <p className="error-text compact-message">{metaError}</p>}
            <div className="monster-select-grid">
              <label className="field">
                <span>體型</span>
                <select value={value.monster.size} onChange={(event) => updateMonster({ size: intValue(event.target.value) })}>
                  {(meta?.sizes ?? []).map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span>屬性</span>
                <select value={value.monster.element} onChange={(event) => updateMonster({ element: intValue(event.target.value) })}>
                  {(meta?.elements ?? []).filter((row) => row.value <= 9).map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
                </select>
              </label>
              <FieldNumber label="屬性 Lv" value={value.monster.elementLv} min={1} max={4} onChange={(elementLv) => updateMonster({ elementLv })} />
              <label className="field">
                <span>種族</span>
                <select value={value.monster.race} onChange={(event) => updateMonster({ race: intValue(event.target.value) })}>
                  {(meta?.races ?? []).filter((row) => row.value !== 9999).map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span>階級</span>
                <select value={value.monster.classId} onChange={(event) => updateMonster({ classId: intValue(event.target.value) })}>
                  {(meta?.classes ?? []).map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span>怪物強制倍率</span>
                <select value={value.monster.damageMultiplierPercent} onChange={(event) => updateMonster({ damageMultiplierPercent: floatValue(event.target.value, 100) })}>
                  <option value={100}>100%</option>
                  <option value={10}>10%</option>
                  <option value={1}>1%</option>
                  <option value={0.1}>0.1%</option>
                </select>
              </label>
            </div>

            <div className="monster-defense-grid">
              <FieldNumber label="後 DEF" value={value.monster.def} onChange={(def) => updateMonster({ def })} />
              <FieldNumber label="前 DEF" value={value.monster.defc} onChange={(defc) => updateMonster({ defc })} />
              <FieldNumber label="RES" value={value.monster.res} onChange={(res) => updateMonster({ res })} />
              <FieldNumber label="後 MDEF" value={value.monster.mdef} onChange={(mdef) => updateMonster({ mdef })} />
              <FieldNumber label="前 MDEF" value={value.monster.mdefc} onChange={(mdefc) => updateMonster({ mdefc })} />
              <FieldNumber label="MRES" value={value.monster.mres} onChange={(mres) => updateMonster({ mres })} />
              <FieldNumber label="星座塔減傷 %" value={value.monster.betelgeuseReductionPercent} min={0} max={100} onChange={(betelgeuseReductionPercent) => updateMonster({ betelgeuseReductionPercent })} />
            </div>
          </section>

          <section className="damage-resource-card damage-special-always-open">
            <h4>增傷狀態</h4>
            <div className="damage-special-grid">
              {[
                ['wanzih', '萬紫 / 震裂4'],
                ['poisonWeak', '毒耐性弱化'],
                ['magicPoison', '魔力中毒'],
                ['attributeSeal', '屬性紋章'],
                ['sneakAttack', '潛擊'],
                ['darkCrow', '爪痕'],
                ['rushAttack', '撼動'],
                ['sporeAttack', '孢子'],
                ['oleumAttack', '聖油'],
                ['lexAeterna', '天怒'],
              ].map(([key, label]) => {
                const typedKey =
                  key as keyof Omit<
                    DamageState['special'],
                    'totalSrl'
                  >
                const pressed =
                  Boolean(
                    value.special[
                      typedKey
                    ],
                  )

                return (
                  <ToggleButton
                    key={key}
                    pressed={pressed}
                    className="damage-special-button"
                    onPressedChange={(next) =>
                      onChange({
                        ...value,
                        special: {
                          ...value.special,
                          [key]: next,
                        },
                      })
                    }
                  >
                    {label}
                  </ToggleButton>
                )
              })}
            </div>
          </section>


        </div>

        <aside className="damage-result-card">
          {value.skillId === null ? (
            <div className="damage-empty">
              <strong>選擇技能後開始計算最終傷害</strong>
              <p>未選技能時，裝備效果仍照 Stage 16 自動計算。</p>
            </div>
          ) : result ? (
            <>
              <div className="damage-total">
                <span>總傷害</span>
                <strong>{damageText(result.total_damage_min, result.total_damage)}</strong>
                <small>
                  {result.skill.name} Lv.{result.skill.level}
                  {' · '}
                  公式來源 {result.skill.formula_source}
                </small>
              </div>

              <div className="damage-segments">
                {result.segments.map((segment, index) => (
                  <details key={`${segment.label}-${segment.round}-${index}`} open={result.segments.length <= 3}>
                    <summary>
                      <span>{segment.label} #{segment.round}</span>
                      <strong>{damageText(segment.total_damage_min, segment.total_damage)}</strong>
                    </summary>
                    <div className="damage-segment-body">
                      <p>單次：{damageText(segment.damage_by_hit_min, segment.damage_by_hit)} · hits {segment.times}</p>
                      <p>技能倍率：{segment.skill_result}%</p>
                      <code>{segment.formula}</code>
                      {segment.formula_expanded !== segment.formula && (
                        <code className="damage-formula-expanded">
                          = {segment.formula_expanded}
                        </code>
                      )}
                    </div>
                  </details>
                ))}
              </div>

              {result.breakdown ? (
                <section
                  className={
                    `damage-breakdown-card ` +
                    `damage-breakdown-${result.breakdown.mode}`
                  }
                >
                  <header className="damage-breakdown-header">
                    <div>
                      <span>以下各增傷數值</span>
                      <strong>
                        {result.breakdown.label}
                      </strong>
                    </div>

                    <small>
                      依目前技能類型顯示
                    </small>
                  </header>

                  {result.breakdown.rows.length > 0 ? (
                    <div className="damage-breakdown-grid">
                      {result.breakdown.rows.map(
                        (row) => (
                          <div
                            className="damage-breakdown-row"
                            key={row.key}
                          >
                            <span>
                              {row.label}
                            </span>
                            <strong>
                              {breakdownValue(
                                row.value,
                                row.unit,
                                row.digits,
                              )}
                            </strong>
                          </div>
                        ),
                      )}
                    </div>
                  ) : (
                    <p className="damage-breakdown-empty">
                      此技能類型沒有一般物理 / 魔法增傷欄位。
                    </p>
                  )}
                </section>
              ) : (
                <section className="damage-breakdown-card">
                  <header className="damage-breakdown-header">
                    <div>
                      <span>以下各增傷數值</span>
                      <strong>Core 尚未更新</strong>
                    </div>
                  </header>
                  <p className="damage-breakdown-empty">
                    請重新載入 Stage 21.17 backend；此處不再顯示舊 ATK 卡片。
                  </p>
                </section>
              )}

              {result.warnings.length > 0 && (
                <div className="damage-warning-box">
                  {result.warnings.map((warning, index) => <p key={`${index}-${warning}`}>{warning}</p>)}
                </div>
              )}
            </>
          ) : (
            <div className="damage-empty">
              <strong>{calculating ? 'Damage Core 計算中…' : '等待傷害結果'}</strong>
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}
