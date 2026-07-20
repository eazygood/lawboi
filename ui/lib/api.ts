const API_URL =
  typeof window === "undefined"
    ? process.env.API_URL ?? "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export interface Citation {
  act_title: string
  section: string
  subsection: string
  eli: string
  heading: string
  url: string
}

export interface AnswerResponse {
  answer: string
  model_used: string
  citations: Citation[]
  language_detected: string
  translation_warning: boolean
  disclaimer: string
  conversation_id: number
}

export interface AnswerRequest {
  query: string
  model?: string
  as_of_date?: string
  conversation_id?: number
}

export interface ProvisionResult {
  provision_id: number
  section_num: string
  text_et: string
  act_title: string
  eli: string
}

export async function fetchAnswer(req: AnswerRequest): Promise<AnswerResponse> {
  const res = await fetch(`${API_URL}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export async function fetchModels(): Promise<string[]> {
  const res = await fetch(`${API_URL}/models`)
  if (!res.ok) throw new Error(`API error ${res.status}`)
  const data = await res.json()
  return data.models as string[]
}

export async function fetchSearch(
  query: string,
  asOfDate?: string
): Promise<ProvisionResult[]> {
  const res = await fetch(`${API_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, as_of_date: asOfDate ?? null }),
  })
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}
