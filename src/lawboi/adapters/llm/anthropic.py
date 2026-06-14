class AnthropicAdapter:
    def __init__(self, model: str, api_key: str):
        self.name = model
        from llama_index.llms.anthropic import Anthropic
        self._llm = Anthropic(model=model, api_key=api_key)

    def complete(self, prompt: str) -> str:
        return str(self._llm.complete(prompt))
