// === STAGE 20 CARD ENCHANT AUTOCOMPLETE ===
import {
  type KeyboardEvent,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { searchItems } from '../api'
import type { ItemSummary } from '../types'

const SEARCH_DEBOUNCE_MS = 180

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function itemCalculationName(item: ItemSummary): string {
  return item.name || item.base_name
}

function itemTitle(item: ItemSummary): string {
  return item.base_name || item.name || `物品 ${item.item_id}`
}

interface CardEnchantFieldProps {
  index: number
  value: string
  apiReady: boolean
  onChange: (value: string) => void
}

export default function CardEnchantField({
  index,
  value,
  apiReady,
  onChange,
}: CardEnchantFieldProps) {
  const [candidates, setCandidates] = useState<ItemSummary[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [focused, setFocused] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const query = value.trim()

  useEffect(() => {
    if (!apiReady || !query) {
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
          const response = await searchItems(
            query,
            controller.signal,
          )

          if (controller.signal.aborted) return

          setCandidates(
            response.items
              .filter((item) => item.is_equipment)
              .slice(0, 12),
          )
          setActiveIndex(-1)
        } catch (searchError) {
          if (!controller.signal.aborted) {
            setCandidates([])
            setError(readableError(searchError))
          }
        } finally {
          if (!controller.signal.aborted) {
            setSearching(false)
          }
        }
      })()
    }, SEARCH_DEBOUNCE_MS)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [apiReady, query])

  const showDropdown = useMemo(
    () =>
      focused &&
      Boolean(query) &&
      (searching || candidates.length > 0 || Boolean(error)),
    [candidates.length, error, focused, query, searching],
  )

  function choose(item: ItemSummary) {
    onChange(itemCalculationName(item))
    setCandidates([])
    setActiveIndex(-1)
    setError('')
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
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
          : Math.min(candidates.length - 1, current + 1),
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

    if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault()
      choose(candidates[activeIndex])
    }
  }

  return (
    <div className="socket-field">
      <label>
        <span>卡片 / 附魔 {index + 1}</span>
        <div className="inline-control">
          <input
            type="search"
            value={value}
            autoComplete="off"
            onFocus={() => setFocused(true)}
            onBlur={() => {
              window.setTimeout(() => setFocused(false), 120)
            }}
            onKeyDown={handleKeyDown}
            onChange={(event) => {
              onChange(event.target.value)
              setError('')
            }}
            placeholder="直接輸入，候選會自動出現"
            aria-label={`卡片或附魔 ${index + 1}`}
            aria-autocomplete="list"
            aria-expanded={showDropdown}
          />
          <button
            className="button button-secondary compact-button"
            type="button"
            disabled={!value}
            onClick={() => {
              onChange('')
              setCandidates([])
              setActiveIndex(-1)
              setError('')
            }}
          >
            清
          </button>
        </div>
      </label>

      {showDropdown && (
        <div className="socket-candidates socket-candidates-popup">
          {searching && (
            <div className="socket-candidate-state">
              搜尋中…
            </div>
          )}

          {!searching &&
            candidates.map((item, candidateIndex) => (
              <button
                key={item.item_id}
                type="button"
                className={`slot-candidate ${
                  activeIndex === candidateIndex
                    ? 'slot-candidate-active'
                    : ''
                }`}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(candidateIndex)}
                onClick={() => choose(item)}
              >
                <strong>{itemTitle(item)}</strong>
                <span>ID {item.item_id}</span>
              </button>
            ))}

          {error && (
            <div className="socket-candidate-state error-text">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
