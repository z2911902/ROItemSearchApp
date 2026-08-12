// === STAGE 21.5 EFFECT SEARCH AND DESKTOP SPACING ===

export interface EffectDisplayFilters {
  hidePhysical: boolean
  hideMagical: boolean
  hideRecognition: boolean
}

export const DEFAULT_EFFECT_DISPLAY_FILTERS: EffectDisplayFilters = {
  hidePhysical: false,
  hideMagical: false,
  hideRecognition: true,
}

// Exact current Desktop ItemSearchApp.filter_effects() UI keywords.
export const DESKTOP_PHYSICAL_HIDE_KEYWORDS = [
  '物理',
  '爆擊',
  'CRI',
  '武器ATK',
  'P.ATK',
] as const

export const DESKTOP_MAGICAL_HIDE_KEYWORDS = [
  '魔法',
  '武器MATK',
  'S.MATK',
] as const

export const DESKTOP_UNRECOGNIZED_PREFIXES = [
  '🟡',
  '⚠️',
  '❌',
  '📌',
  '✅',
  '⛔',
  '可使用',
] as const

function stripCompareLabelPrefix(
  text: string,
): string {
  return String(text ?? '')
    .trim()
    .replace(/^效果\s*[|｜]\s*/, '')
    .trim()
}

function candidatesForPrefixCheck(
  text: string,
): string[] {
  const normalized =
    stripCompareLabelPrefix(text)
  const candidates = [normalized]

  // Web source rendering can prepend a source segment. Desktop filters
  // parser lines before presentation, so inspect each rendered segment too.
  normalized
    .split(/\s*[|｜]\s*/)
    .map((row) => row.trim())
    .filter(Boolean)
    .forEach((row) => candidates.push(row))

  for (const prefix of DESKTOP_UNRECOGNIZED_PREFIXES) {
    const index = normalized.indexOf(prefix)
    if (index > 0) {
      candidates.push(
        normalized.slice(index).trim(),
      )
    }
  }

  return [...new Set(candidates)]
}

export function isRecognitionOrParserLine(
  text: string,
): boolean {
  return candidatesForPrefixCheck(text).some(
    (candidate) =>
      DESKTOP_UNRECOGNIZED_PREFIXES.some(
        (prefix) =>
          candidate.startsWith(prefix),
      ),
  )
}

export function isEffectTextHidden(
  text: string,
  filters: EffectDisplayFilters,
): boolean {
  const normalized =
    stripCompareLabelPrefix(text)

  if (
    filters.hidePhysical &&
    DESKTOP_PHYSICAL_HIDE_KEYWORDS.some(
      (keyword) =>
        normalized.includes(keyword),
    )
  ) {
    return true
  }

  if (
    filters.hideMagical &&
    DESKTOP_MAGICAL_HIDE_KEYWORDS.some(
      (keyword) =>
        normalized.includes(keyword),
    )
  ) {
    return true
  }

  if (
    filters.hideRecognition &&
    isRecognitionOrParserLine(normalized)
  ) {
    return true
  }

  return false
}

function isDesktopTotalLine(
  line: string,
): boolean {
  const normalized = String(line ?? '')

  return (
    normalized.includes('〔總和〕') ||
    normalized.includes('〔總計〕') ||
    normalized.includes('🧮↳')
  )
}

function compactDesktopEffectSpacing(
  lines: string[],
): string[] {
  const output: string[] = []

  for (const rawLine of lines) {
    const line = String(rawLine ?? '')
    const blank = line.trim().length === 0

    if (blank) {
      // Desktop intentionally has one blank line after each total.
      // Collapse repeated parser/source blanks down to one instead of
      // deleting every separator or allowing giant visual gaps.
      if (
        output.length > 0 &&
        output[output.length - 1].trim().length !== 0
      ) {
        output.push('')
      }
      continue
    }

    if (
      output.length > 0 &&
      isDesktopTotalLine(output[output.length - 1])
    ) {
      output.push('')
    }

    output.push(line)
  }

  while (
    output.length > 0 &&
    output[output.length - 1].trim().length === 0
  ) {
    output.pop()
  }

  return output
}

export function filterEffectLines(
  lines: string[],
  filters: EffectDisplayFilters,
): string[] {
  const filtered = lines.filter(
    (line) =>
      !isEffectTextHidden(line, filters),
  )

  return compactDesktopEffectSpacing(filtered)
}

/**
 * Mirrors Desktop update_total_effect_display():
 * keyword = input.trim()
 * lines = [line for line in raw if keyword in line]
 *
 * Search is deliberately case-sensitive and only returns matching rows.
 * No blank separators are injected while a keyword is active.
 */
export function searchEffectLines(
  lines: string[],
  searchText: string,
): string[] {
  const keyword = String(searchText ?? '').trim()

  if (!keyword) {
    return lines
  }

  return lines.filter(
    (line) => line.includes(keyword),
  )
}
