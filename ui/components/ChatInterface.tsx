"use client"

import { useState, useRef } from "react"
import { fetchAnswer, AnswerResponse, Citation } from "@/lib/api"
import SourcePanel from "./SourcePanel"
import ModelSelector from "./ModelSelector"
import EmptyState from "./EmptyState"
import AnswerContent from "./AnswerContent"

interface Message {
  role: "user" | "assistant"
  content: string
  response?: AnswerResponse
}

interface Props {
  availableModels: string[]
}

interface CitationPanelState {
  citations: Citation[]
  activeIndex: number | null
}

export default function ChatInterface({ availableModels }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState(availableModels[0] ?? "gemini-2.0-flash")
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [citationPanel, setCitationPanel] = useState<CitationPanelState | null>(null)
  const requestIdRef = useRef(0)

  function handleNewChat() {
    requestIdRef.current += 1
    setMessages([])
    setInput("")
    setLoading(false)
    setConversationId(null)
    setCitationPanel(null)
    setError(null)
  }

  function openCitations(citations: Citation[], activeIndex: number | null) {
    setCitationPanel({ citations, activeIndex })
  }

  function handleComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      e.currentTarget.form?.requestSubmit()
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return
    const requestId = requestIdRef.current
    const query = input.trim()
    setInput("")
    setError(null)
    setMessages((prev) => [...prev, { role: "user", content: query }])
    setLoading(true)
    try {
      const response = await fetchAnswer({
        query,
        model: selectedModel,
        conversation_id: conversationId ?? undefined,
      })
      if (requestIdRef.current === requestId) {
        setConversationId(response.conversation_id)
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: response.answer, response },
        ])
      }
    } catch (err) {
      if (requestIdRef.current === requestId) {
        setError(err instanceof Error ? err.message : "Unknown error")
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false)
      }
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 max-w-3xl mx-auto w-full">
        <header className="h-14 shrink-0 border-b border-slate-200 flex items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-md bg-[#1e3a5f] flex items-center justify-center text-white font-bold text-xs shrink-0">
              ¶
            </div>
            <h1 className="text-sm font-semibold text-slate-800 truncate">ParagrahvAI</h1>
          </div>
          <button
            onClick={handleNewChat}
            disabled={messages.length === 0}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-600 border border-slate-200 hover:bg-slate-50 disabled:opacity-40 rounded-lg px-3 py-1.5 shrink-0"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Uus vestlus
          </button>
        </header>

        {messages.length === 0 ? (
          <EmptyState onSelectPrompt={setInput} />
        ) : (
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
            <div className="max-w-2xl mx-auto space-y-6">
              {messages.map((msg, i) =>
                msg.role === "user" ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[85%] sm:max-w-lg bg-[#1e3a5f] text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm">
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex justify-start">
                    <div className="max-w-xl w-full">
                      <div className="flex items-center gap-2 mb-1.5">
                        <div className="w-5 h-5 rounded bg-[#1e3a5f] flex items-center justify-center text-white text-[10px] font-bold">
                          ¶
                        </div>
                        <span className="text-xs font-medium text-slate-500">ParagrahvAI</span>
                      </div>
                      <div className="bg-slate-50 border border-slate-200 rounded-2xl rounded-tl-sm px-5 py-4">
                        <AnswerContent
                          answer={msg.content}
                          citations={msg.response?.citations ?? []}
                          onCitationClick={(index) => openCitations(msg.response?.citations ?? [], index)}
                        />
                      </div>
                      {msg.response && (
                        <div className="flex items-center gap-3 mt-2 px-1">
                          {msg.response.citations.length > 0 && (
                            <button
                              onClick={() => openCitations(msg.response!.citations, null)}
                              className="text-xs font-medium text-[#1e3a5f] hover:underline"
                            >
                              {msg.response.citations.length} allikat
                            </button>
                          )}
                          {msg.response.translation_warning && (
                            <span className="text-[11px] text-slate-400">Sisaldab mitteametlikku tõlget</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )
              )}
              {loading && (
                <div className="flex justify-start">
                  <div className="max-w-xl w-full">
                    <div className="flex items-center gap-2 mb-1.5">
                      <div className="w-5 h-5 rounded bg-[#1e3a5f] flex items-center justify-center text-white text-[10px] font-bold">
                        ¶
                      </div>
                      <span className="text-xs font-medium text-slate-500">ParagrahvAI</span>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded-2xl rounded-tl-sm px-5 py-4 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" />
                    </div>
                  </div>
                </div>
              )}
              {error && <p className="text-red-500 text-sm text-center">{error}</p>}
            </div>
          </div>
        )}

        <div
          className="border-t border-slate-200 px-4 sm:px-6 py-3"
          style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
        >
          <div className="max-w-2xl mx-auto">
            <form
              onSubmit={handleSubmit}
              className="flex items-end gap-2 border border-slate-300 rounded-2xl px-3 py-2 focus-within:ring-2 focus-within:ring-[#1e3a5f]/20 focus-within:border-[#1e3a5f]/40 bg-white"
            >
              <textarea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="Küsi Eesti seaduste kohta..."
                disabled={loading}
                className="flex-1 resize-none text-sm py-1.5 focus:outline-none placeholder:text-slate-400"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="w-8 h-8 rounded-lg bg-[#1e3a5f] hover:bg-[#16304f] text-white flex items-center justify-center transition-colors shrink-0 disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </form>
            <div className="flex items-center justify-between mt-1.5 px-1">
              <ModelSelector models={availableModels} selected={selectedModel} onChange={setSelectedModel} />
              <p className="text-[11px] text-slate-400 hidden sm:inline">Ei asenda õigusnõustaja konsultatsiooni</p>
            </div>
          </div>
        </div>
      </main>

      <SourcePanel
        citations={citationPanel?.citations ?? []}
        open={citationPanel !== null}
        activeIndex={citationPanel?.activeIndex ?? null}
        onClose={() => setCitationPanel(null)}
      />
    </div>
  )
}
