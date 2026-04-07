# TraceMind Python SDK

Instrument your LLM app in 3 lines.

## Install
pip install TraceMind

## Quickstart
from TraceMind import TraceMind

ef = TraceMind(api_key="ef_live_...", project="my-app")

@ef.trace("my_llm_call")
def ask_ai(question: str) -> str:
    return your_llm.run(question)