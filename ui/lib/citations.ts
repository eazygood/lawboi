import { Citation } from "./api"

const BRACKET_CITATION = /\[([^[\]]*§[^[\]]*)\]/g
const SECTION_NUMBER = /§\s*(\d+[a-z]?)/i

function sectionNumber(section: string): string | null {
  const match = SECTION_NUMBER.exec(section)
  return match ? match[1].toLowerCase() : null
}

export function annotateInlineCitations(answer: string, citations: Citation[]): string {
  const sectionToIndices = new Map<string, number[]>()
  citations.forEach((c, i) => {
    const num = sectionNumber(c.section)
    if (!num) return
    const indices = sectionToIndices.get(num) ?? []
    indices.push(i + 1)
    sectionToIndices.set(num, indices)
  })

  return answer.replace(BRACKET_CITATION, (_fullMatch, inner: string) => {
    const num = sectionNumber(inner)
    if (!num) return ""
    const indices = sectionToIndices.get(num)
    if (!indices || indices.length === 0) return ""
    if (indices.length === 1) return `[${indices[0]}](#cite-${indices[0]})`

    const loweredInner = inner.toLowerCase()
    const match = indices.find((idx) => loweredInner.includes(citations[idx - 1].act_title.toLowerCase()))
    const index = match ?? indices[0]
    return `[${index}](#cite-${index})`
  })
}
