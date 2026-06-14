"use client"

interface Props {
  models: string[]
  selected: string
  onChange: (model: string) => void
}

export default function ModelSelector({ models, selected, onChange }: Props) {
  if (models.length === 0) return null
  return (
    <div className="flex items-center gap-2 text-sm text-gray-500">
      <label htmlFor="model-select" className="font-medium">Model:</label>
      <select
        id="model-select"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        className="border rounded px-2 py-1 text-sm bg-white"
      >
        {models.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
    </div>
  )
}
