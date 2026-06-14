import { fetchModels } from "@/lib/api"
import ChatInterface from "@/components/ChatInterface"

export default async function Home() {
  let models: string[] = []
  try {
    models = await fetchModels()
  } catch {
    // API not reachable at build time — fall back to empty list
  }

  return <ChatInterface availableModels={models} />
}
