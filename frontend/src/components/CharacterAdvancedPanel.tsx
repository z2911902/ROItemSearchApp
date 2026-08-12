// === STAGE 21.13.2 TWO-COLUMN CHARACTER LAYOUT ===
import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import { getBuffEntries } from '../api'
import type {
  AdvancedCharacterState,
  BuffListEntry,
  CharacterStatusResult,
  JobSummary,
  StatusSettingsState,
} from '../types'
import ToggleButton from './ToggleButton'
import CharacterStatusPanel from './CharacterStatusPanel'

export interface BasicCharacterFields {
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

function readableError(
  error: unknown,
): string {
  return error instanceof Error
    ? error.message
    : String(error)
}

function numberValue(
  value: string,
  fallback = 0,
): number {
  const parsed = Number.parseInt(
    value,
    10,
  )
  return Number.isFinite(parsed)
    ? parsed
    : fallback
}

function exclusiveGroups(
  value: unknown,
): string[] {
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((group) =>
        group.trim(),
      )
      .filter(Boolean)
  }

  if (Array.isArray(value)) {
    return value
      .map(String)
      .map((group) =>
        group.trim(),
      )
      .filter(Boolean)
  }

  return []
}

function NumberField({
  label,
  value,
  onChange,
  min = 0,
}: {
  label: string
  value: number
  onChange: (
    value: number,
  ) => void
  min?: number
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        value={value}
        onChange={(event) =>
          onChange(
            numberValue(
              event.target.value,
            ),
          )
        }
      />
    </label>
  )
}

function BuffButtons({
  title,
  entries,
  selectedNames,
  onToggle,
  emptyText,
}: {
  title: string
  entries: BuffListEntry[]
  selectedNames: string[]
  onToggle: (
    entry: BuffListEntry,
  ) => void
  emptyText: string
}) {
  return (
    <section className="buff-group">
      <div className="buff-group-heading">
        <strong>{title}</strong>
        <span>
          {entries.length} 項
        </span>
      </div>

      {entries.length > 0 ? (
        <div className="buff-button-grid">
          {entries.map((entry) => {
            const selected =
              selectedNames.includes(
                entry.name,
              )

            return (
              <ToggleButton
                key={`${entry.source_index}-${entry.name}`}
                pressed={selected}
                className="buff-toggle-button"
                onPressedChange={() =>
                  onToggle(entry)
                }
                title={
                  entry.type
                    ? `${entry.type} · ${entry.name}`
                    : entry.name
                }
              >
                <span className="buff-entry-copy">
                  <strong>
                    {entry.name}
                  </strong>
                  <small>
                    {entry.type ||
                      '未分類'}
                  </small>
                </span>
              </ToggleButton>
            )
          })}
        </div>
      ) : (
        <p className="muted compact-message">
          {emptyText}
        </p>
      )}
    </section>
  )
}

export default function CharacterAdvancedPanel({
  character,
  onCharacterChange,
  value,
  onChange,
  apiReady,
  jobs,
  jobsLoading,
  jobsError,
  jobCode,
  statusSettings,
  statusResult,
  onStatusChange,
}: {
  character: BasicCharacterFields
  onCharacterChange: (
    value: BasicCharacterFields,
  ) => void
  value: AdvancedCharacterState
  onChange: (
    value: AdvancedCharacterState,
  ) => void
  apiReady: boolean
  jobs: JobSummary[]
  jobsLoading: boolean
  jobsError: string
  jobCode: string
  statusSettings: StatusSettingsState
  statusResult: CharacterStatusResult | null
  onStatusChange: (
    value: StatusSettingsState,
  ) => void
}) {
  const [buffEntries, setBuffEntries] =
    useState<BuffListEntry[]>([])
  const [buffQuery, setBuffQuery] =
    useState('')
  const [buffLoading, setBuffLoading] =
    useState(false)
  const [buffError, setBuffError] =
    useState('')

  useEffect(() => {
    if (!apiReady) {
      return
    }

    const controller =
      new AbortController()

    void (async () => {
      setBuffLoading(true)
      setBuffError('')

      try {
        // The Stage14 endpoint returns the full list.
        // jobCode only marks/orders current-job entries; it does not make
        // local search job-restricted.
        const response =
          await getBuffEntries(
            '',
            jobCode,
            controller.signal,
          )

        if (
          !controller.signal.aborted
        ) {
          setBuffEntries(
            response.entries,
          )
        }
      } catch (error) {
        if (
          !controller.signal.aborted
        ) {
          setBuffEntries([])
          setBuffError(
            readableError(error),
          )
        }
      } finally {
        if (
          !controller.signal.aborted
        ) {
          setBuffLoading(false)
        }
      }
    })()

    return () =>
      controller.abort()
  }, [
    apiReady,
    jobCode,
  ])

  const visibleBuffEntries =
    useMemo(() => {
      const query =
        buffQuery
          .trim()
          .toLowerCase()

      if (!query) {
        return buffEntries
      }

      // Search the entire returned all_skill_entries list, including
      // other professions and common food/buffs.
      return buffEntries.filter(
        (entry) =>
          [
            entry.type,
            entry.name,
            ...(entry.job_ids ?? []),
          ]
            .join(' ')
            .toLowerCase()
            .includes(query),
      )
    }, [
      buffEntries,
      buffQuery,
    ])

  const currentJobBuffs =
    useMemo(
      () =>
        visibleBuffEntries.filter(
          (entry) =>
            entry.job_match,
        ),
      [visibleBuffEntries],
    )

  const otherBuffs =
    useMemo(
      () =>
        visibleBuffEntries.filter(
          (entry) =>
            !entry.job_match,
        ),
      [visibleBuffEntries],
    )

  const entryByName = useMemo(
    () =>
      Object.fromEntries(
        buffEntries.map(
          (entry) => [
            entry.name,
            entry,
          ],
        ),
      ),
    [buffEntries],
  )

  function updateCharacter(
    patch:
      Partial<BasicCharacterFields>,
  ) {
    onCharacterChange({
      ...character,
      ...patch,
    })
  }

  function clearCharacterStatusAndBuffs() {
    onCharacterChange({
      ...character,
      str: 1,
      agi: 1,
      vit: 1,
      intStat: 1,
      dex: 1,
      luk: 1,
    })

    onChange({
      ...value,
      pow: 0,
      sta: 0,
      wis: 0,
      spl: 0,
      con: 0,
      crt: 0,
      enabledSkillNames: [],
    })

    onStatusChange({
      mhpInput: 0,
      mspInput: 0,
      useLogoutHpsp: false,
      hpPercent: 100,
      spPercent: 100,
    })

    setBuffQuery('')
    setBuffError('')
  }

  function toggleBuff(
    entry: BuffListEntry,
  ) {
    if (
      value.enabledSkillNames
        .includes(entry.name)
    ) {
      onChange({
        ...value,
        enabledSkillNames:
          value
            .enabledSkillNames
            .filter(
              (name) =>
                name !==
                entry.name,
            ),
      })
      return
    }

    const groups = new Set(
      exclusiveGroups(
        entry.exclusive,
      ),
    )

    const nextNames =
      value
        .enabledSkillNames
        .filter((name) => {
          if (!groups.size) {
            return true
          }

          const existingGroups =
            exclusiveGroups(
              entryByName[
                name
              ]?.exclusive,
            )

          return !existingGroups
            .some(
              (group) =>
                groups.has(group),
            )
        })

    onChange({
      ...value,
      enabledSkillNames: [
        ...nextNames,
        entry.name,
      ],
    })
  }

  return (
    <details
      className="advanced-character"
      open
    >
      <summary>
        角色 / 素質 / Buff / HP / SP / ASPD
      </summary>

      <div className="advanced-character-body stage21-13-character-body">
        <div className="character-unified-toolbar stage21-13-character-toolbar">
          <small>
            JOB / BaseLv / JobLv 保留；清空只重設素質、Buff 與 HP/SP 輸入。
          </small>

          <button
            className="button button-secondary character-clear-button"
            type="button"
            onClick={clearCharacterStatusAndBuffs}
          >
            清空素質 / Buff / HP-SP
          </button>
        </div>

        <div className="stage21-13-character-grid stage21-13-2-character-grid">
          <div className="stage21-13-2-left-column">
            <CharacterStatusPanel
              apiReady={apiReady}
              settings={statusSettings}
              result={statusResult}
              onChange={onStatusChange}
              embedded
            />

            <div className="character-stat-column stage21-13-stat-column">
          <section className="character-core-section">
            <h4>職業 / 等級</h4>

            <div className="character-job-level-grid">
              <label className="field character-job-select">
                <span>JOB</span>
                <select
                  value={
                    character.jobId ??
                    ''
                  }
                  disabled={
                    jobsLoading
                  }
                  onChange={(event) =>
                    updateCharacter({
                      jobId:
                        numberValue(
                          event
                            .target
                            .value,
                        ),
                    })
                  }
                >
                  {character.jobId ===
                    null && (
                    <option value="">
                      請選擇職業
                    </option>
                  )}

                  {jobs.map(
                    (job) => (
                      <option
                        key={String(
                          job.job_id,
                        )}
                        value={
                          job.job_id
                        }
                      >
                        {job.name}{' '}
                        ({job.job_id})
                      </option>
                    ),
                  )}
                </select>
              </label>

              <NumberField
                label="BaseLv"
                value={
                  character.baseLv
                }
                onChange={(
                  baseLv,
                ) =>
                  updateCharacter({
                    baseLv,
                  })
                }
              />

              <NumberField
                label="JobLv"
                value={
                  character.jobLv
                }
                onChange={(
                  jobLv,
                ) =>
                  updateCharacter({
                    jobLv,
                  })
                }
              />
            </div>

            {jobsError && (
              <p className="error-text compact-message">
                {jobsError}
              </p>
            )}
          </section>

          <section>
            <h4>基本素質</h4>
            <div className="advanced-stat-grid">
              <NumberField
                label="STR"
                value={
                  character.str
                }
                onChange={(str) =>
                  updateCharacter({
                    str,
                  })
                }
              />
              <NumberField
                label="AGI"
                value={
                  character.agi
                }
                onChange={(agi) =>
                  updateCharacter({
                    agi,
                  })
                }
              />
              <NumberField
                label="VIT"
                value={
                  character.vit
                }
                onChange={(vit) =>
                  updateCharacter({
                    vit,
                  })
                }
              />
              <NumberField
                label="INT"
                value={
                  character.intStat
                }
                onChange={(
                  intStat,
                ) =>
                  updateCharacter({
                    intStat,
                  })
                }
              />
              <NumberField
                label="DEX"
                value={
                  character.dex
                }
                onChange={(dex) =>
                  updateCharacter({
                    dex,
                  })
                }
              />
              <NumberField
                label="LUK"
                value={
                  character.luk
                }
                onChange={(luk) =>
                  updateCharacter({
                    luk,
                  })
                }
              />
            </div>
          </section>

          <section>
            <h4>四轉素質</h4>
            <div className="advanced-stat-grid">
              <NumberField
                label="POW"
                value={value.pow}
                onChange={(pow) =>
                  onChange({
                    ...value,
                    pow,
                  })
                }
              />
              <NumberField
                label="STA"
                value={value.sta}
                onChange={(sta) =>
                  onChange({
                    ...value,
                    sta,
                  })
                }
              />
              <NumberField
                label="WIS"
                value={value.wis}
                onChange={(wis) =>
                  onChange({
                    ...value,
                    wis,
                  })
                }
              />
              <NumberField
                label="SPL"
                value={value.spl}
                onChange={(spl) =>
                  onChange({
                    ...value,
                    spl,
                  })
                }
              />
              <NumberField
                label="CON"
                value={value.con}
                onChange={(con) =>
                  onChange({
                    ...value,
                    con,
                  })
                }
              />
              <NumberField
                label="CRT"
                value={value.crt}
                onChange={(crt) =>
                  onChange({
                    ...value,
                    crt,
                  })
                }
              />
            </div>
          </section>
            </div>
          </div>

        <section className="buff-list-section character-buff-column stage21-13-2-buff-column">
          <div className="buff-heading">
            <div>
              <h4>增益技能 / 料理</h4>
              <small>
                本職與其他技能分區 · 搜尋不限制職業
              </small>
            </div>

            <span>
              {
                value
                  .enabledSkillNames
                  .length
              }{' '}
              已選
            </span>
          </div>

          <input
            className="buff-filter"
            type="search"
            value={buffQuery}
            onChange={(event) =>
              setBuffQuery(
                event.target.value,
              )
            }
            placeholder="搜尋全部職業技能 / 料理 / type"
          />

          {buffLoading && (
            <p className="muted compact-message">
              載入 all_skill_entries.py…
            </p>
          )}

          {buffError && (
            <p className="error-text compact-message">
              {buffError}
            </p>
          )}

          <div className="buff-entry-list buff-entry-list-grouped">
            <BuffButtons
              title="本職技能 / 料理"
              entries={
                currentJobBuffs
              }
              selectedNames={
                value
                  .enabledSkillNames
              }
              onToggle={
                toggleBuff
              }
              emptyText={
                buffQuery.trim()
                  ? '搜尋結果沒有本職項目。'
                  : '目前職業沒有專屬項目。'
              }
            />

            <div
              className="buff-job-separator"
              role="separator"
            >
              <span>
                其他職業 / 共用
              </span>
            </div>

            <BuffButtons
              title="其他技能 / 料理"
              entries={otherBuffs}
              selectedNames={
                value
                  .enabledSkillNames
              }
              onToggle={
                toggleBuff
              }
              emptyText="沒有其他符合項目。"
            />
          </div>
        </section>

      </div>
      </div>
    </details>
  )
}
