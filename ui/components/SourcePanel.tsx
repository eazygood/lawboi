"use client"

import { Citation } from "@/lib/api"

interface Props {
  citations: Citation[]
  onClose: () => void
}

export default function SourcePanel({ citations, onClose }: Props) {
  return (
    <aside className="fixed right-0 top-0 h-full w-80 bg-white shadow-xl border-l overflow-y-auto z-10">
      <div className="flex justify-between items-center p-4 border-b">
        <h2 className="font-semibold text-gray-700">Sources</h2>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          aria-label="Close source panel"
        >
          ×
        </button>
      </div>
      {citations.length === 0 ? (
        <p className="p-4 text-sm text-gray-400">No citations for this answer.</p>
      ) : (
        <ul className="divide-y">
          {citations.map((c, i) => (
            <li key={i} className="p-4">
              <p className="font-medium text-sm text-gray-800">{c.act_title}</p>
              <p className="text-sm text-gray-600">{c.section} {c.subsection}</p>
              <p className="text-xs text-gray-400 mt-1">{c.eli}</p>
              <a
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-blue-500 hover:underline mt-1 block"
              >
                View on riigiteataja.ee →
              </a>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
