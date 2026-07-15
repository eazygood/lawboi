"use client"

const FRIENDLY_NAMES: Record<string, string> = {
  "gemini-2.0-flash": "Kiire (Gemini)",
  "gemini-1.5-pro": "Täpne (Gemini)",
  "gpt-4o": "Täpne (OpenAI)",
  "gpt-4o-mini": "Kiire (OpenAI)",
  "claude-sonnet-4-5": "Täpne (Claude)",
}

function friendlyName(model: string): string {
  return FRIENDLY_NAMES[model] ?? model
}

interface Props {
  models: string[]
  selected: string
  onChange: (model: string) => void
}

export default function ModelSelector({ models, selected, onChange }: Props) {
  if (models.length === 0) return null
  return (
    <p className="text-[11px] text-slate-400">
      Mudel:{" "}
      <select
        id="model-select"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent underline hover:text-slate-600 focus:outline-none appearance-none cursor-pointer"
      >
        {models.map((m) => (
          <option key={m} value={m}>{friendlyName(m)}</option>
        ))}
      </select>
    </p>
  )
}
