// === STAGE 21.11 PER-SLOT BROWSER SAVES ===
import { getEnchantToolItem, getLapineToolItem } from '../api'
import { useEffect, useMemo, useState } from 'react'
import {
  cloneEquipmentSlotState,
  readBrowserSlotBuilds,
  slotHasData,
  subscribeBrowserSlotBuilds,
  writeBrowserSlotBuilds,
  type BrowserStoredSlotBuild,
} from '../browserSlotStorage'
import type { CalculatePayload, ItemSummary } from '../types'
import {
  DEFAULT_GRADE_OPTIONS,
  supports,
  type EquipmentSlotDefinition,
  type EquipmentSlotState,
} from '../equipmentSlots'
import CardEnchantField from './CardEnchantField'
import EquipmentSearchField from './EquipmentSearchField'
import NoteFieldEditor from './NoteFieldEditor'
import ConfirmDialog from './ConfirmDialog'

function numberValue(value: string, fallback = 0): number {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

interface EquipmentSlotEditorProps {
  definition: EquipmentSlotDefinition
  value: EquipmentSlotState<ItemSummary>
  apiReady: boolean
  previewContext: CalculatePayload | null
  onChange: (value: EquipmentSlotState<ItemSummary>) => void
  onOpenEnchant?: () => void
  onOpenLapine?: () => void
}

export default function EquipmentSlotEditor({
  definition,
  value,
  apiReady,
  previewContext,
  onChange,
  onOpenEnchant,
  onOpenLapine,
}: EquipmentSlotEditorProps) {
  const supportsEquipment = supports(definition, 'supportsEquipment')
  const supportsRefine = supports(definition, 'supportsRefine')
  const supportsGrade = supports(definition, 'supportsGrade')
  const supportsCards = supports(definition, 'supportsCards')
  const supportsNote = supports(definition, 'supportsNote')
  const supportsTools = supports(definition, 'supportsTools')
  const gradeOptions = definition.gradeOptions ?? DEFAULT_GRADE_OPTIONS
  const [enchantAvailability, setEnchantAvailability] =
    useState<'idle' | 'loading' | 'available' | 'unavailable'>('idle')
  const [lapineAvailability, setLapineAvailability] =
    useState<'idle' | 'loading' | 'available' | 'unavailable'>('idle')
  const [slotBuilds, setSlotBuilds] =
    useState<BrowserStoredSlotBuild[]>([])
  const [slotBuildName, setSlotBuildName] =
    useState('')
  const [slotBuildMessage, setSlotBuildMessage] =
    useState('')
  const [pendingLoad, setPendingLoad] =
    useState<BrowserStoredSlotBuild | null>(null)
  const [pendingSaveOverwrite, setPendingSaveOverwrite] =
    useState<BrowserStoredSlotBuild | null>(null)

  useEffect(() => {
    const refresh = () => {
      setSlotBuilds(
        readBrowserSlotBuilds().filter(
          (row) => row.slot_id === definition.slotId,
        ),
      )
    }

    refresh()
    return subscribeBrowserSlotBuilds(refresh)
  }, [definition.slotId])

  useEffect(() => {
    if (
      !supportsTools ||
      !apiReady ||
      !value.item
    ) {
      setEnchantAvailability('idle')
      return
    }

    const controller = new AbortController()
    setEnchantAvailability('loading')

    void (async () => {
      try {
        const data = await getEnchantToolItem(
          value.item!.item_id,
          controller.signal,
        )

        if (controller.signal.aborted) return

        const hasRows = data.slots.some(
          (slot) => slot.entries.length > 0,
        )

        setEnchantAvailability(
          hasRows ? 'available' : 'unavailable',
        )
      } catch {
        if (!controller.signal.aborted) {
          // The Stage13 route returns an error/no item when EnchantList
          // has no usable data for this equipment.  Treat that as unavailable
          // instead of letting the user open an empty modal.
          setEnchantAvailability('unavailable')
        }
      }
    })()

    return () => controller.abort()
  }, [
    apiReady,
    supportsTools,
    value.item?.item_id,
  ])

  useEffect(() => {
    if (
      !supportsTools ||
      !apiReady ||
      !value.item
    ) {
      setLapineAvailability('idle')
      return
    }

    const controller = new AbortController()
    setLapineAvailability('loading')

    void (async () => {
      try {
        // showAll=false matches the normal Desktop Lapine list:
        // only compatible entries with a configured probability table
        // count as usable Lapine data.
        const data = await getLapineToolItem(
          value.item!.item_id,
          false,
          controller.signal,
        )

        if (controller.signal.aborted) return

        setLapineAvailability(
          data.boxes.length > 0
            ? 'available'
            : 'unavailable',
        )
      } catch {
        if (!controller.signal.aborted) {
          setLapineAvailability('unavailable')
        }
      }
    })()

    return () => controller.abort()
  }, [
    apiReady,
    supportsTools,
    value.item?.item_id,
  ])

  const enchantAvailable =
    enchantAvailability === 'available'
  const enchantButtonText =
    enchantAvailability === 'loading'
      ? '附魔工具｜檢查中'
      : enchantAvailable
        ? '附魔工具'
        : '附魔工具｜無資料'

  const lapineAvailable =
    lapineAvailability === 'available'
  const lapineButtonText =
    lapineAvailability === 'loading'
      ? 'Lapine｜檢查中'
      : lapineAvailable
        ? 'Lapine'
        : 'Lapine｜無資料'

  const extraCount = useMemo(
    () =>
      value.cards.filter((card) => card.trim()).length +
      (value.note.trim() ? 1 : 0),
    [value.cards, value.note],
  )

  const currentSlotHasData = slotHasData(value)

  function defaultSlotBuildName(): string {
    const itemName =
      value.item?.base_name ||
      value.item?.name

    if (itemName) return itemName
    if (value.note.trim()) return `${definition.label} 詞條`

    return `${definition.label} 存檔`
  }

  function commitSlotSave(
    existing: BrowserStoredSlotBuild | null,
  ) {
    const name =
      slotBuildName.trim() ||
      defaultSlotBuildName()

    const all = readBrowserSlotBuilds()

    const record: BrowserStoredSlotBuild = {
      id:
        existing?.id ??
        (
          typeof crypto !== 'undefined' &&
          'randomUUID' in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random()}`
        ),
      slot_id: definition.slotId,
      slot_key: definition.key,
      slot_label: definition.label,
      name,
      saved_at: new Date().toISOString(),
      value: cloneEquipmentSlotState(value),
    }

    const next = writeBrowserSlotBuilds([
      record,
      ...all.filter(
        (row) =>
          row.id !== record.id &&
          !(
            row.slot_id === definition.slotId &&
            row.name === record.name
          ),
      ),
    ])

    setSlotBuilds(
      next.filter(
        (row) => row.slot_id === definition.slotId,
      ),
    )
    setSlotBuildName(name)
    setSlotBuildMessage(
      existing
        ? `已取代部位存檔：${name}`
        : `已儲存部位：${name}`,
    )
    setPendingSaveOverwrite(null)
  }

  function saveCurrentSlot() {
    if (!currentSlotHasData) {
      setSlotBuildMessage('目前部位沒有可儲存的內容。')
      return
    }

    const name =
      slotBuildName.trim() ||
      defaultSlotBuildName()

    const existing =
      slotBuilds.find((row) => row.name === name) ?? null

    if (existing) {
      setSlotBuildName(name)
      setPendingSaveOverwrite(existing)
      return
    }

    commitSlotSave(null)
  }

  function applyStoredSlot(row: BrowserStoredSlotBuild) {
    onChange(
      cloneEquipmentSlotState(row.value),
    )
    setSlotBuildMessage(
      `已載入部位存檔：${row.name}`,
    )
    setPendingLoad(null)
  }

  function requestLoadSlot(row: BrowserStoredSlotBuild) {
    if (currentSlotHasData) {
      setPendingLoad(row)
      return
    }

    applyStoredSlot(row)
  }

  function deleteStoredSlot(id: string) {
    const all = readBrowserSlotBuilds()
    const next = writeBrowserSlotBuilds(
      all.filter((row) => row.id !== id),
    )

    setSlotBuilds(
      next.filter(
        (row) => row.slot_id === definition.slotId,
      ),
    )
    setSlotBuildMessage('已刪除部位存檔。')
  }

  function setCard(index: number, cardName: string) {
    const cards = [...value.cards] as [string, string, string, string]
    cards[index] = cardName
    onChange({ ...value, cards })
  }

  return (
    <article className={`equipment-slot-card ${
      value.item || extraCount ? 'equipment-slot-card-active' : ''
    }`}>
      <header className="equipment-slot-header">
        <div>
          <strong>{definition.label}</strong>
          <span>slot {definition.slotId}</span>
        </div>
        <div className="badge-row">
          {extraCount > 0 && <span className="badge">{extraCount} 附加</span>}
          {value.item && <span className="badge">已裝備</span>}
        </div>
      </header>

      <details className="slot-save-manager">
        <summary>
          <span>部位存檔</span>
          <span className="badge">{slotBuilds.length}</span>
        </summary>

        <div className="slot-save-manager-body">
          <div className="slot-save-create">
            <label className="field">
              <span>存檔名稱</span>
              <input
                value={slotBuildName}
                onChange={(event) => {
                  setSlotBuildName(event.target.value)
                  setSlotBuildMessage('')
                }}
                placeholder={
                  currentSlotHasData
                    ? defaultSlotBuildName()
                    : `${definition.label} 存檔名稱`
                }
              />
            </label>

            <button
              className="button button-secondary"
              type="button"
              disabled={!currentSlotHasData}
              onClick={saveCurrentSlot}
            >
              儲存目前部位
            </button>
          </div>

          {slotBuildMessage && (
            <p className="slot-save-message">
              {slotBuildMessage}
            </p>
          )}

          {slotBuilds.length > 0 ? (
            <div className="slot-save-list">
              {slotBuilds.map((row) => (
                <div
                  className="slot-save-row"
                  key={row.id}
                >
                  <div className="slot-save-copy">
                    <strong>{row.name}</strong>
                    <small>
                      {new Date(row.saved_at).toLocaleString()}
                    </small>
                  </div>

                  <div className="slot-save-actions">
                    <button
                      className="button button-secondary"
                      type="button"
                      onClick={() => requestLoadSlot(row)}
                    >
                      載入
                    </button>
                    <button
                      className="button button-secondary"
                      type="button"
                      onClick={() => deleteStoredSlot(row.id)}
                    >
                      刪除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted compact-message">
              尚未儲存此部位。
            </p>
          )}
        </div>
      </details>

      {supportsEquipment && (
        <>
          <EquipmentSearchField
            apiReady={apiReady}
            item={value.item}
            placeholder={
              definition.slotId === 100
                ? '石碑名稱 / Item ID / 描述，多條件空白分隔'
                : definition.slotId === 101
                  ? '寵物名稱 / Item ID / 描述，多條件空白分隔'
                  : '裝備名稱 / Item ID / 描述，多條件空白分隔'
            }
            onSelect={(item) =>
              onChange({
                ...value,
                item,
              })
            }
          />

          <div className="slot-current">
            {value.item ? (
              <div className="slot-current-with-tools">
                <div className="slot-current-main">
                  <div className="slot-current-copy">
                    <strong>
                      {value.item.base_name ||
                        value.item.name ||
                        `物品 ${value.item.item_id}`}
                    </strong>
                    <span>ID {value.item.item_id}</span>
                  </div>
                </div>

                {supportsTools && (
                  <div className="slot-tool-buttons">
                    <button
                      className={`button button-secondary ${
                        !enchantAvailable
                          ? 'tool-button-unavailable'
                          : ''
                      }`}
                      type="button"
                      onClick={onOpenEnchant}
                      disabled={
                        !apiReady ||
                        !onOpenEnchant ||
                        !enchantAvailable
                      }
                      title={
                        enchantAvailable
                          ? '開啟此裝備的附魔工具'
                          : '此裝備在 EnchantList 沒有可用附魔資料'
                      }
                    >
                      {enchantButtonText}
                    </button>
                    <button
                      className={`button button-secondary ${
                        !lapineAvailable
                          ? 'tool-button-unavailable'
                          : ''
                      }`}
                      type="button"
                      onClick={onOpenLapine}
                      disabled={
                        !apiReady ||
                        !onOpenLapine ||
                        !lapineAvailable
                      }
                      title={
                        lapineAvailable
                          ? '開啟此裝備的 Lapine 附加功能附魔'
                          : '此裝備沒有可用的 Lapine 機率表資料'
                      }
                    >
                      {lapineButtonText}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <span className="muted">未選擇裝備</span>
            )}
          </div>
        </>
      )}

      {(supportsRefine || supportsGrade) && (
        <div className={`slot-values ${supportsRefine && supportsGrade ? 'two-column-fields' : ''}`}>
          {supportsRefine && (
            <label className="field">
              <span>{definition.refineLabel ?? '精煉'}</span>
              <input
                type="number"
                min={0}
                max={20}
                value={value.refine}
                onChange={(event) => onChange({ ...value, refine: numberValue(event.target.value) })}
              />
            </label>
          )}

          {supportsGrade && (
            <label className="field">
              <span>{definition.gradeLabel ?? 'Grade'}</span>
              <select
                value={value.grade}
                onChange={(event) => onChange({ ...value, grade: numberValue(event.target.value) })}
              >
                {gradeOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {(supportsCards || supportsNote) && (
        <details className="slot-extra">
          <summary>
            {supportsCards ? '卡片 / 附魔 / 詞條' : '詞條'}
            {extraCount > 0 && <span>{extraCount}</span>}
          </summary>
          <div className="slot-extra-body">
            {supportsCards && (
              <div className="socket-grid">
                {value.cards.map((card, index) => (
                  <CardEnchantField
                    key={index}
                    index={index}
                    value={card}
                    apiReady={apiReady}
                    onChange={(cardName) => setCard(index, cardName)}
                  />
                ))}
              </div>
            )}

            {supportsNote && (
              <NoteFieldEditor
                raw={value.note}
                apiReady={apiReady}
                slotId={definition.slotId}
                grade={value.grade}
                refine={value.refine}
                context={previewContext}
                title={definition.label}
                onChange={(note) =>
                  onChange({
                    ...value,
                    note,
                  })
                }
              />
            )}
          </div>
        </details>
      )}

      <ConfirmDialog
        open={pendingLoad !== null}
        title={`取代${definition.label}目前內容？`}
        message={
          pendingLoad
            ? `「${definition.label}」目前已有資料。載入「${pendingLoad.name}」會完整取代目前的裝備、精煉 / Grade、卡片 / 附魔與詞條。是否取代？`
            : ''
        }
        confirmLabel="取代並載入"
        onCancel={() => setPendingLoad(null)}
        onConfirm={() => {
          if (pendingLoad) {
            applyStoredSlot(pendingLoad)
          }
        }}
      />

      <ConfirmDialog
        open={pendingSaveOverwrite !== null}
        title="同名部位存檔已存在"
        message={
          pendingSaveOverwrite
            ? `「${definition.label}」已有同名存檔「${pendingSaveOverwrite.name}」。是否用目前部位內容取代舊存檔？`
            : ''
        }
        confirmLabel="取代存檔"
        onCancel={() => setPendingSaveOverwrite(null)}
        onConfirm={() => {
          if (pendingSaveOverwrite) {
            commitSlotSave(pendingSaveOverwrite)
          }
        }}
      />
    </article>
  )
}
