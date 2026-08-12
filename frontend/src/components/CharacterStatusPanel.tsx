// === STAGE 21.13 CHARACTER STATUS SIDEBAR ===
import type {
  CharacterStatusResult,
  StatusSettingsState,
} from '../types'
import ToggleButton from './ToggleButton'

function intValue(value: string, fallback = 0): number {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function formatNumber(value: number): string {
  return Math.round(value).toLocaleString()
}

function sourceLabel(source: string): string {
  if (source === 'manual_logout') return '登出畫面輸入'
  if (source === 'manual_base') return '手動基礎值'
  return '職業 HP/SP 表'
}

export default function CharacterStatusPanel({
  apiReady,
  settings,
  result,
  onChange,
  embedded = false,
}: {
  apiReady: boolean
  settings: StatusSettingsState
  result: CharacterStatusResult | null
  onChange: (settings: StatusSettingsState) => void
  embedded?: boolean
}) {
  const hp = result?.hpsp
  const aspd = result?.aspd

  return (
    <section
      className={`character-status-panel ${
        embedded
          ? 'character-status-panel-embedded stage21-13-status-column'
          : ''
      }`}
    >
      <header className="character-status-header">
        <div>
          {!embedded && (
            <div className="eyebrow">
              STAGE 20 · SHARED STATUS CORE
            </div>
          )}
          {embedded ? (
            <h4>HP / SP / ASPD</h4>
          ) : (
            <h3>HP / SP / ASPD</h3>
          )}
          {!embedded && (
            <p>
              角色、裝備、Buff、精煉或攻速詞條改變後會一起自動更新。
            </p>
          )}
        </div>
        <span className="badge">
          {apiReady ? '自動計算' : 'API 未連線'}
        </span>
      </header>

      <div className="status-metric-grid">
        <article className="status-metric-card">
          <span>HP</span>
          <strong>
            {hp
              ? `${formatNumber(hp.mhp_now)} / ${formatNumber(hp.mhp)}`
              : '—'}
          </strong>
          <small>
            {hp
              ? `${hp.hp_current_percent}% · ${sourceLabel(hp.source_hp)}`
              : '等待 Core'}
          </small>
        </article>

        <article className="status-metric-card">
          <span>SP</span>
          <strong>
            {hp
              ? `${formatNumber(hp.msp_now)} / ${formatNumber(hp.msp)}`
              : '—'}
          </strong>
          <small>
            {hp
              ? `${hp.sp_current_percent}% · ${sourceLabel(hp.source_sp)}`
              : '等待 Core'}
          </small>
        </article>

        <article className="status-metric-card status-metric-aspd">
          <span>ASPD</span>
          <strong>
            {aspd?.supported && aspd.value !== null
              ? aspd.value.toFixed(3)
              : '—'}
          </strong>
          <small>
            {aspd?.supported && aspd.attacks_per_second !== null
              ? `每秒 ${aspd.attacks_per_second.toFixed(2)} 下 · ${
                  aspd.mode === 'dual'
                    ? '雙刀'
                    : aspd.has_shield
                      ? '持盾'
                      : '單手'
                }`
              : aspd?.message || '等待 Core'}
          </small>
        </article>
      </div>

      <div className="status-slider-grid">
        <label className="status-slider-field">
          <span>
            HP {settings.hpPercent}%
            {hp && ` · ${formatNumber(hp.mhp_now)}`}
          </span>
          <input
            type="range"
            min={0}
            max={100}
            value={settings.hpPercent}
            onChange={(event) =>
              onChange({
                ...settings,
                hpPercent: intValue(event.target.value, 100),
              })
            }
          />
        </label>

        <label className="status-slider-field">
          <span>
            SP {settings.spPercent}%
            {hp && ` · ${formatNumber(hp.msp_now)}`}
          </span>
          <input
            type="range"
            min={0}
            max={100}
            value={settings.spPercent}
            onChange={(event) =>
              onChange({
                ...settings,
                spPercent: intValue(event.target.value, 100),
              })
            }
          />
        </label>
      </div>

      <details className="status-advanced-input">
        <summary>HP/SP 手動基礎值 / 登出畫面輸入</summary>
        <div className="status-advanced-body">
          <div className="status-manual-grid">
            <label className="field">
              <span>MHP 輸入（0 = 使用職業表）</span>
              <input
                type="number"
                min={0}
                value={settings.mhpInput}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    mhpInput: intValue(event.target.value),
                  })
                }
              />
            </label>

            <label className="field">
              <span>MSP 輸入（0 = 使用職業表）</span>
              <input
                type="number"
                min={0}
                value={settings.mspInput}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    mspInput: intValue(event.target.value),
                  })
                }
              />
            </label>
          </div>

          <ToggleButton
            pressed={settings.useLogoutHpsp}
            className="status-toggle-button"
            onPressedChange={(useLogoutHpsp) =>
              onChange({
                ...settings,
                useLogoutHpsp,
              })
            }
          >
            <span>
              輸入的是登出畫面 HP/SP
              <small>
                Core 會先依基礎 VIT / INT 無條件進位反推，再套裝備加成。
              </small>
            </span>
          </ToggleButton>

          {result && (
            <div className="status-debug-grid">
              <span>基礎職業 HP {formatNumber(result.hpsp.job_base_hp)}</span>
              <span>基礎職業 SP {formatNumber(result.hpsp.job_base_sp)}</span>
              <span>總 VIT {result.stats.total_vit}</span>
              <span>總 INT {result.stats.total_int}</span>
              <span>總 AGI {result.stats.total_agi}</span>
              <span>總 DEX {result.stats.total_dex}</span>
              <span>
                裝備 MHP {result.hpsp.hp_flat >= 0 ? '+' : ''}
                {result.hpsp.hp_flat}
                {' / '}
                {result.hpsp.hp_percent_bonus >= 0 ? '+' : ''}
                {result.hpsp.hp_percent_bonus}%
              </span>
              <span>
                裝備 MSP {result.hpsp.sp_flat >= 0 ? '+' : ''}
                {result.hpsp.sp_flat}
                {' / '}
                {result.hpsp.sp_percent_bonus >= 0 ? '+' : ''}
                {result.hpsp.sp_percent_bonus}%
              </span>
            </div>
          )}
        </div>
      </details>
    </section>
  )
}
