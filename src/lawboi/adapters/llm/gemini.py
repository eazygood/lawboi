class GeminiAdapter:
    def __init__(self, model: str, api_key: str):
        self.name = model
        from llama_index.llms.gemini import Gemini
        self._llm = Gemini(model=model, api_key=api_key)

    async def complete(self, prompt: str) -> str:
        return str(await self._llm.acomplete(prompt))

    async def complete_structured(self, prompt: str, output_cls):
        from llama_index.core.prompts import PromptTemplate
        template = PromptTemplate(prompt.replace("{", "{{").replace("}", "}}"))
        return await self._llm.astructured_predict(output_cls, template)
