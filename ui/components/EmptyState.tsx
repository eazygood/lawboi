"use client"

interface Props {
  onSelectPrompt: (prompt: string) => void
}

const EXAMPLE_PROMPTS = [
  "Kui pikk on katseaeg tähtajatu töölepingu puhul?",
  "Millal tuleb esitada käibemaksudeklaratsioon?",
  "Mis vastutus on osaühingu juhatuse liikmel?",
  "Kuidas arvestatakse puhkusetasu osalise koormusega?",
]

export default function EmptyState({ onSelectPrompt }: Props) {
  return (
    <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center px-6">
      <div className="max-w-xl w-full text-center">
        <h2 className="text-2xl font-semibold text-slate-800 mb-2">Küsi Eesti seaduste kohta</h2>
        <p className="text-slate-500 text-sm mb-8 leading-relaxed">
          Vastused põhinevad Riigi Teataja ametlikel tekstidel ja iga vastus viitab konkreetsele
          seadusesättele, mida saab kohe kontrollida.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => onSelectPrompt(prompt)}
              className="group p-3.5 rounded-lg border border-slate-200 hover:border-[#1e3a5f]/40 hover:bg-slate-50 transition-colors text-left"
            >
              <p className="text-sm font-medium text-slate-700 group-hover:text-[#1e3a5f]">{prompt}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
