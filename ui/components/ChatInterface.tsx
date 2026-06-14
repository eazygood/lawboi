"use client"

import { useState } from "react"
import { fetchAnswer, AnswerResponse } from "@/lib/api"
import SourcePanel from "./SourcePanel"
import ModelSelector from "./ModelSelector"

interface Message {
  role: "user" | "assistant"
  content: string
  response?: AnswerResponse
}

interface Props {
  availableModels: string[]
}

export default function ChatInterface({ availableModels }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState(availableModels[0] ?? "gemini-2.0-flash")
  const [panelResponse, setPanelResponse] = useState<AnswerResponse | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return
    const query = input.trim()
    setInput("")
    setError(null)
    setMessages((prev) => [...prev, { role: "user", content: query }])
    setLoading(true)
    try {
      const response = await fetchAnswer({ query, model: selectedModel })
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.answer, response },
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto px-4">
      <header className="py-4 border-b flex justify-between items-center">
        <h1 className="text-xl font-semibold text-gray-800">Eesti Õigusabi</h1>
        <ModelSelector
          models={availableModels}
          selected={selectedModel}
          onChange={setSelectedModel}
        />
      </header>

      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              {msg.content}
              {msg.response && msg.response.citations.length > 0 && (
                <button
                  onClick={() => setPanelResponse(msg.response!)}
                  className="block mt-2 text-xs underline opacity-70 hover:opacity-100"
                >
                  {msg.response.citations.length} source{msg.response.citations.length > 1 ? "s" : ""} →
                </button>
              )}
              {msg.response?.translation_warning && (
                <p className="mt-1 text-xs opacity-60 italic">
                  Note: source text is an unofficial translation.
                </p>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-4 py-2 text-sm text-gray-400">
              Thinking…
            </div>
          </div>
        )}
        {error && (
          <p className="text-red-500 text-sm text-center">{error}</p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="py-4 border-t flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about Estonian law..."
          className="flex-1 border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50 hover:bg-blue-600"
        >
          Send
        </button>
      </form>

      {panelResponse && (
        <SourcePanel
          citations={panelResponse.citations}
          onClose={() => setPanelResponse(null)}
        />
      )}
    </div>
  )
}
