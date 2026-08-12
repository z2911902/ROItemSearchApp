import { useEffect, useMemo, useState } from 'react'
import { getEnchantToolItem, rollEnchant } from '../api'
import type {
  EnchantEntry,
  EnchantRollResponse,
  EnchantToolItem,
  ItemSummary,
} from '../types'

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function typeLabel(type: EnchantEntry['type']): string {
  return {
    enchant: '機率附魔',
    perfect: '指定附魔',
    upgrade: '指定升階',
    perfect_upgrade: '指定升階',
    random_upgrade: '機率升階',
  }[type]
}

export default function EnchantToolModal({
  item,
  partName,
  currentCards,
  onApply,
  onClose,
}: {
  item: ItemSummary
  partName: string
  currentCards: [string, string, string, string]
  onApply: (slotId: number, enchantName: string) => void
  onClose: () => void
}) {
  const [data, setData] = useState<EnchantToolItem | null>(null)
  const [error, setError] = useState('')
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null)
  const [rolling, setRolling] = useState(false)
  const [rollResult, setRollResult] = useState<EnchantRollResponse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const response = await getEnchantToolItem(item.item_id, controller.signal)
        setData(response)
        setSelectedSlot(response.slots[0]?.slot_id ?? null)
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setError(readableError(loadError))
        }
      }
    })()
    return () => controller.abort()
  }, [item.item_id])

  const slot = useMemo(
    () => data?.slots.find((candidate) => candidate.slot_id === selectedSlot) ?? null,
    [data, selectedSlot],
  )

  async function runRandom() {
    if (selectedSlot === null) {
      return
    }
    setRolling(true)
    setError('')
    try {
      const response = await rollEnchant(
        item.item_id,
        selectedSlot,
        currentCards[selectedSlot] ?? '',
      )
      setRollResult(response)
      if (response.success && response.result?.output_name) {
        onApply(selectedSlot, response.result.output_name)
      }
    } catch (rollError) {
      setError(readableError(rollError))
    } finally {
      setRolling(false)
    }
  }

  return (
    <div className="tool-modal-backdrop" role="presentation">
      <section className="tool-modal" role="dialog" aria-modal="true">
        <header className="tool-modal-header">
          <div>
            <div className="eyebrow">DESKTOP ENCHANT TOOL · WEB</div>
            <h2>附魔工具</h2>
            <p>
              {partName} · {item.base_name || item.name} · ID {item.item_id}
            </p>
          </div>
          <button className="button button-secondary" type="button" onClick={onClose}>
            關閉
          </button>
        </header>

        {error && <p className="error-text tool-message">{error}</p>}
        {!data && !error && <p className="tool-message">載入 EnchantList…</p>}

        {data && (
          <>
            <div className="tool-tabs">
              {data.slots.map((candidate) => (
                <button
                  type="button"
                  key={candidate.slot_id}
                  className={candidate.slot_id === selectedSlot ? 'active' : ''}
                  onClick={() => {
                    setSelectedSlot(candidate.slot_id)
                    setRollResult(null)
                  }}
                >
                  第 {candidate.slot_id + 1} 洞
                  {currentCards[candidate.slot_id] && (
                    <span>{currentCards[candidate.slot_id]}</span>
                  )}
                </button>
              ))}
            </div>

            <div className="tool-actions">
              <button
                className="button button-primary"
                type="button"
                onClick={() => void runRandom()}
                disabled={rolling || selectedSlot === null}
              >
                {rolling ? '抽選中…' : '隨機 / 機率升階'}
              </button>
              {rollResult && (
                <span className={rollResult.success ? 'success-text' : 'muted'}>
                  {rollResult.success
                    ? `結果：${rollResult.result?.output_name}`
                    : '本次未抽中'}
                </span>
              )}
            </div>

            {slot && (
              <div className="tool-entry-list">
                {slot.entries.map((entry, index) => (
                  <article key={`${entry.type}-${index}-${entry.output_name}`}>
                    <div className="tool-entry-main">
                      <div>
                        <span className="tool-type">{typeLabel(entry.type)}</span>
                        <strong>{entry.name}</strong>
                        {entry.rate_percent < 100 && (
                          <small>{entry.rate_percent.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}%</small>
                        )}
                      </div>
                      <button
                        className="button button-secondary"
                        type="button"
                        onClick={() => onApply(slot.slot_id, entry.output_name)}
                      >
                        套用到第 {slot.slot_id + 1} 洞
                      </button>
                    </div>
                    {(entry.zeny > 0 || entry.materials.length > 0) && (
                      <div className="material-row">
                        {entry.zeny > 0 && <span>{entry.zeny.toLocaleString()} Zeny</span>}
                        {entry.materials.map((material, materialIndex) => (
                          <span key={`${material.raw_name}-${materialIndex}`}>
                            {material.name} × {material.count}
                          </span>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}

            {data.reset?.enable && (
              <div className="tool-footer-note">
                可重置附魔
                {data.reset.materials.length > 0 && (
                  <>
                    ：
                    {data.reset.materials
                      .map((material) => `${material.name} × ${material.count}`)
                      .join('、')}
                  </>
                )}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
