// === STAGE 21 LIVE MULTI CONDITION EQUIPMENT SEARCH ===
import {
  type KeyboardEvent,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { searchEquipmentItems } from '../api'
import type { ItemSummary } from '../types'

const EQUIPMENT_SEARCH_DEBOUNCE_MS = 180

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function itemTitle(item: ItemSummary): string {
  return item.base_name || item.name || `物品 ${item.item_id}`
}

export default function EquipmentSearchField({
  apiReady,
  item,
  placeholder = '裝備名稱 / Item ID / 描述，多條件用空白分隔',
  onSelect,
}: {
  apiReady: boolean
  item: ItemSummary | null
  placeholder?: string
  onSelect: (item: ItemSummary | null) => void
}) {
  const [query, setQuery] = useState(item ? itemTitle(item) : '')
  const [candidates, setCandidates] = useState<ItemSummary[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [focused, setFocused] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const selectedTitle = item ? itemTitle(item) : ''

  useEffect(() => {
    setQuery(selectedTitle)
    setCandidates([])
    setActiveIndex(-1)
  }, [item?.item_id, selectedTitle])

  const normalized = query.trim()

  useEffect(() => {
    if (
      !apiReady ||
      !normalized ||
      (item && normalized === selectedTitle)
    ) {
      setCandidates([])
      setSearching(false)
      setError('')
      setActiveIndex(-1)
      return
    }

    const controller = new AbortController()

    const timer = window.setTimeout(() => {
      void (async () => {
        setSearching(true)
        setError('')

        try {
          const response = await searchEquipmentItems(
            normalized,
            controller.signal,
            40,
          )

          if (controller.signal.aborted) return

          setCandidates(response.items)
          setActiveIndex(
            response.items.length > 0 ? 0 : -1,
          )
        } catch (searchError) {
          if (!controller.signal.aborted) {
            setCandidates([])
            setActiveIndex(-1)
            setError(readableError(searchError))
          }
        } finally {
          if (!controller.signal.aborted) {
            setSearching(false)
          }
        }
      })()
    }, EQUIPMENT_SEARCH_DEBOUNCE_MS)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [
    apiReady,
    item?.item_id,
    normalized,
    selectedTitle,
  ])

  const showDropdown = useMemo(
    () =>
      focused &&
      Boolean(normalized) &&
      normalized !== selectedTitle &&
      (
        searching ||
        candidates.length > 0 ||
        Boolean(error)
      ),
    [
      candidates.length,
      error,
      focused,
      normalized,
      searching,
      selectedTitle,
    ],
  )

  function choose(next: ItemSummary) {
    onSelect(next)
    setQuery(itemTitle(next))
    setCandidates([])
    setActiveIndex(-1)
    setError('')
  }

  function handleKeyDown(
    event: KeyboardEvent<HTMLInputElement>,
  ) {
    if (event.key === 'Escape') {
      setCandidates([])
      setActiveIndex(-1)
      return
    }

    if (!showDropdown || candidates.length === 0) {
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((current) =>
        current < 0
          ? 0
          : Math.min(
              candidates.length - 1,
              current + 1,
            ),
      )
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((current) =>
        current <= 0 ? 0 : current - 1,
      )
      return
    }

    if (
      event.key === 'Enter' &&
      activeIndex >= 0
    ) {
      event.preventDefault()
      choose(candidates[activeIndex])
    }
  }

  return (
    <div className="equipment-live-search">
      <div className="inline-control">
        <input
          type="search"
          value={query}
          autoComplete="off"
          placeholder={placeholder}
          aria-label="裝備多條件搜尋"
          aria-autocomplete="list"
          aria-expanded={showDropdown}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            window.setTimeout(
              () => setFocused(false),
              120,
            )
          }}
          onKeyDown={handleKeyDown}
          onChange={(event) => {
            setQuery(event.target.value)
            setError('')
          }}
        />

        <button
          className="button button-secondary compact-button"
          type="button"
          disabled={!item && !query}
          onClick={() => {
            onSelect(null)
            setQuery('')
            setCandidates([])
            setActiveIndex(-1)
            setError('')
          }}
        >
          清
        </button>
      </div>

      <small className="equipment-search-hint">
        多條件以空白分隔；每個條件都必須命中 Item ID、名稱或描述。
      </small>

      {showDropdown && (
        <div className="equipment-search-popup">
          {searching && (
            <div className="equipment-search-state">
              搜尋中…
            </div>
          )}

          {!searching &&
            candidates.map((candidate, index) => (
              <button
                key={candidate.item_id}
                type="button"
                className={`equipment-search-candidate ${
                  index === activeIndex
                    ? 'equipment-search-candidate-active'
                    : ''
                }`}
                onMouseDown={(event) =>
                  event.preventDefault()
                }
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(candidate)}
              >
                <span className="equipment-search-candidate-main">
                  <strong>{itemTitle(candidate)}</strong>
                  <small>
                    ID {candidate.item_id}
                    {candidate.weapon_type !== null &&
                    candidate.weapon_type !== undefined
                      ? ` · weapon ${candidate.weapon_type}`
                      : ''}
                  </small>
                </span>

                {candidate.description_preview && (
                  <span className="equipment-search-description">
                    {candidate.description_preview}
                  </span>
                )}
              </button>
            ))}

          {!searching &&
            !error &&
            candidates.length === 0 && (
              <div className="equipment-search-state">
                沒有符合全部條件的裝備。
              </div>
            )}

          {error && (
            <div className="equipment-search-state error-text">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
