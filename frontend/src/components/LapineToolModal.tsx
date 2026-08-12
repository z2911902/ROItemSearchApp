import { useEffect, useState } from 'react'
import { getLapineToolItem, rollLapine } from '../api'
import type {
  ItemSummary,
  LapineRollResponse,
  LapineToolItem,
} from '../types'
import ToggleButton from './ToggleButton'

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export default function LapineToolModal({
  item,
  partName,
  refine,
  onApplyLua,
  onClose,
}: {
  item: ItemSummary
  partName: string
  refine: number
  onApplyLua: (luaEffect: string) => void
  onClose: () => void
}) {
  const [showAll, setShowAll] = useState(false)
  const [data, setData] = useState<LapineToolItem | null>(null)
  const [error, setError] = useState('')
  const [rollingKey, setRollingKey] = useState('')
  const [lastRoll, setLastRoll] = useState<LapineRollResponse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      setError('')
      try {
        setData(
          await getLapineToolItem(item.item_id, showAll, controller.signal),
        )
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setData(null)
          setError(readableError(loadError))
        }
      }
    })()
    return () => controller.abort()
  }, [item.item_id, showAll])

  async function run(boxKey: string) {
    setRollingKey(boxKey)
    setError('')
    try {
      const response = await rollLapine(item.item_id, boxKey)
      setLastRoll(response)
      if (response.lua_effect.trim()) {
        onApplyLua(response.lua_effect)
      }
    } catch (rollError) {
      setError(readableError(rollError))
    } finally {
      setRollingKey('')
    }
  }

  return (
    <div className="tool-modal-backdrop" role="presentation">
      <section className="tool-modal tool-modal-wide" role="dialog" aria-modal="true">
        <header className="tool-modal-header">
          <div>
            <div className="eyebrow">LAPINE UPGRADE · WEB</div>
            <h2>Lapine 附加能力工具</h2>
            <p>
              {partName} · {item.base_name || item.name} · +{refine}
            </p>
          </div>
          <button className="button button-secondary" type="button" onClick={onClose}>
            關閉
          </button>
        </header>

        <ToggleButton
          pressed={showAll}
          className="tool-toggle-button"
          onPressedChange={setShowAll}
        >
          顯示 LapineUpgradeBox 中所有選項（包含尚未建立機率表）
        </ToggleButton>

        {error && <p className="error-text tool-message">{error}</p>}
        {!data && !error && <p className="tool-message">載入 Lapine 資料…</p>}

        {data?.boxes.map((box) => {
          const refineOk =
            refine >= box.need_refine_min && refine <= box.need_refine_max
          return (
            <article className="lapine-box" key={box.key}>
              <header>
                <div>
                  <strong>{box.source_name}</strong>
                  <span>{box.key}</span>
                </div>
                <button
                  className="button button-primary"
                  type="button"
                  disabled={
                    !box.profile ||
                    !refineOk ||
                    rollingKey === box.key
                  }
                  onClick={() => void run(box.key)}
                >
                  {rollingKey === box.key ? '抽選中…' : '隨機附魔並取代詞條'}
                </button>
              </header>

              <div className="lapine-requirements">
                <span>
                  精煉需求 +{box.need_refine_min} ～ +{box.need_refine_max}
                </span>
                <span>最低 Option 數 {box.need_option_num_min}</span>
                {box.need_source_string && <span>{box.need_source_string}</span>}
              </div>

              {!refineOk && (
                <p className="warning-text">目前精煉值不符合此 Lapine 資料。</p>
              )}

              {box.profile ? (
                <>
                  <div className="lapine-profile-title">
                    {box.profile.title || '機率表'}
                    {box.profile.updated_at && (
                      <small>更新：{box.profile.updated_at}</small>
                    )}
                  </div>
                  <div className="lapine-row-list">
                    {box.profile.rows.map((row, index) => (
                      <div key={`${row.group}-${row.option_code}-${index}`}>
                        <span>群組 {row.group}</span>
                        <strong>{row.display_preview}</strong>
                        <span>{row.probability}%</span>
                        <code>{row.lua_preview || row.option_code}</code>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="muted">此 Lapine 選項尚未建立機率表，因此無法抽選。</p>
              )}
            </article>
          )
        })}

        {lastRoll && (
          <div className="lapine-roll-result">
            <strong>
              {lastRoll.success ? '本次 Lapine 結果' : '本次沒有產生附加能力'}
            </strong>
            {lastRoll.results.map((result, index) => (
              <p key={`${result.group}-${index}`}>
                群組 {result.group}：{result.display_text}
              </p>
            ))}
            {lastRoll.lua_effect && (
              <details>
                <summary>已取代此部位 note 的 Lua</summary>
                <pre>{lastRoll.lua_effect}</pre>
              </details>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
