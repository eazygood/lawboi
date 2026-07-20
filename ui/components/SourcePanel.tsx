"use client"

import { useEffect } from "react"
import { Citation } from "@/lib/api"

interface Props {
  citations: Citation[]
  open: boolean
  activeIndex: number | null
  onClose: () => void
}

export default function SourcePanel({ citations, open, activeIndex, onClose }: Props) {
  useEffect(() => {
    if (open && activeIndex !== null) {
      document.getElementById(`cite-${activeIndex}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" })
    }
  }, [open, activeIndex])

  return (
    <aside className={`citations-panel lg:border-l lg:border-slate-200 ${open ? "open" : ""}`}>
      <div className="flex justify-center pt-2 pb-1 lg:hidden">
        <div className="w-8 h-1 rounded-full bg-slate-200" />
      </div>
      <div className="h-14 shrink-0 border-b border-slate-200 flex items-center justify-between px-5">
        <h2 className="text-sm font-semibold text-slate-800">Allikad ({citations.length})</h2>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600"
          aria-label="Sulge allikate paneel"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {citations.length === 0 ? (
          <p className="text-sm text-slate-400">Selle vestuse jaoks pole viiteid.</p>
        ) : (
          citations.map((c, i) => (
            <div
              key={i}
              id={`cite-${i + 1}`}
              className={`citation-card border border-slate-200 rounded-lg p-3.5 transition-all ${
                activeIndex === i + 1 ? "active" : ""
              }`}
            >
              <div className="flex items-center mb-1.5">
                <span className="text-[10px] font-bold text-white bg-[#1e3a5f] rounded px-1.5 py-0.5">
                  {i + 1}
                </span>
              </div>
              <p className="text-sm font-medium text-slate-800">{c.act_title}</p>
              {c.heading && (
                <p className="text-sm text-slate-500 italic">{c.heading}</p>
              )}
              <p className="text-sm text-slate-600 mt-0.5">
                {c.section}
                {c.subsection && <sup className="ml-0.5">{c.subsection}</sup>}
              </p>
              <a
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-[#1e3a5f] hover:underline mt-2.5 inline-block"
              >
                Vaata Riigi Teatajas →
              </a>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
