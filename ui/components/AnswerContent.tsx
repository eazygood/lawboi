"use client"

import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { Citation } from "@/lib/api"
import { annotateInlineCitations } from "@/lib/citations"

interface Props {
  answer: string
  citations: Citation[]
  unverifiedSections?: string[]
  onCitationClick: (index: number) => void
}

export default function AnswerContent({ answer, citations, unverifiedSections = [], onCitationClick }: Props) {
  const annotated = annotateInlineCitations(answer, citations, unverifiedSections)

  const components: Components = {
    a({ href, children }) {
      const cite = /^#cite-(\d+)$/.exec(href ?? "")
      if (cite) {
        const index = Number(cite[1])
        return (
          <button type="button" className="cite-marker" onClick={() => onCitationClick(index)}>
            {children}
          </button>
        )
      }
      if (/^#unverified-/.test(href ?? "")) {
        return (
          <span className="cite-marker-unverified" title="Not found among retrieved/validated sources">
            {children}
          </span>
        )
      }
      return <a href={href}>{children}</a>
    },
  }

  return (
    <div className="answer-content">
      <ReactMarkdown components={components}>{annotated}</ReactMarkdown>
    </div>
  )
}
