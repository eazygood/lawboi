"use client"

import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { Citation } from "@/lib/api"
import { annotateInlineCitations } from "@/lib/citations"

interface Props {
  answer: string
  citations: Citation[]
  onCitationClick: (index: number) => void
}

export default function AnswerContent({ answer, citations, onCitationClick }: Props) {
  const annotated = annotateInlineCitations(answer, citations)

  const components: Components = {
    a({ href, children }) {
      const match = /^#cite-(\d+)$/.exec(href ?? "")
      if (!match) return <a href={href}>{children}</a>
      const index = Number(match[1])
      return (
        <button type="button" className="cite-marker" onClick={() => onCitationClick(index)}>
          {children}
        </button>
      )
    },
  }

  return (
    <div className="answer-content">
      <ReactMarkdown components={components}>{annotated}</ReactMarkdown>
    </div>
  )
}
