// === STAGE 21.4 DESKTOP ITEM DESCRIPTION HTML ===

function escapeHtmlChar(char: string): string {
  if (char === '&') return '&amp;'
  if (char === '<') return '&lt;'
  if (char === '>') return '&gt;'
  if (char === '"') return '&quot;'
  if (char === "'") return '&#39;'
  return char
}

function renderDescriptionLine(
  source: unknown,
): string {
  const line = String(source ?? '')
  let html = ''
  let openSpans = 0

  for (let index = 0; index < line.length;) {
    if (
      line[index] === '^' &&
      index + 6 < line.length
    ) {
      const colorCode =
        line.slice(index + 1, index + 7)

      if (/^[0-9a-fA-F]{6}$/.test(colorCode)) {
        html +=
          `<span style="color:#${colorCode}">`
        openSpans += 1
        index += 7
        continue
      }
    }

    html += escapeHtmlChar(line[index])
    index += 1
  }

  while (openSpans > 0) {
    html += '</span>'
    openSpans -= 1
  }

  return html
}

/**
 * Mirrors Desktop convert_description_to_html():
 * - ^RRGGBB opens a color span;
 * - spans are closed at the end of each source line;
 * - lines are joined with <br>.
 *
 * Unlike Desktop's QTextEdit path, raw text is HTML-escaped first so only
 * the generated span/br markup can enter the browser DOM.
 */
export function descriptionToSafeHtml(
  description: unknown[],
): string {
  return description
    .map(renderDescriptionLine)
    .join('<br>')
}
