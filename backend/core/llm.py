from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import os
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set.\n"
        "1. Get a free key at https://console.groq.com\n"
        "2. Add it to your .env file: GROQ_API_KEY=gsk_...\n"
    )

groq_client = Groq(api_key=GROQ_API_KEY)

FAST_MODEL  = "llama-3.1-8b-instant"
SMART_MODEL = "llama-3.3-70b-versatile"


def chat(
    messages:   list[dict],
    system:     str  = "",
    model:      str  = "fast",
    max_tokens: int  = 1024,
    json_mode:  bool = False
) -> str:
    resolved_model = FAST_MODEL if model == "fast" else SMART_MODEL

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    kwargs = {
        "model":      resolved_model,
        "messages":   full_messages,
        "max_tokens": max_tokens,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = groq_client.chat.completions.create(**kwargs)
    return response.choices[0].message.content

MODEL_COSTS = {
    "llama-3.1-8b-instant":    {"input": 0.05,  "output": 0.08},   # Groq
    "llama-3.3-70b-versatile": {"input": 0.59,  "output": 0.79},   # Groq
    "gemma2-9b-it":            {"input": 0.20,  "output": 0.20},   # Groq
    # Add more as needed
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a model call."""
    costs = MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
    return round(
        (input_tokens  * costs["input"]  / 1_000_000) +
        (output_tokens * costs["output"] / 1_000_000),
        8
    )


def chat_with_usage(
    messages:   list[dict],
    system:     str  = "",
    model:      str  = "fast",
    max_tokens: int  = 1024,
    json_mode:  bool = False,
) -> tuple[str, dict]:
    """
    Like chat() but also returns token usage.

    Returns:
        (response_text, {"input_tokens": N, "output_tokens": N, "cost_usd": N})
    """
    resolved_model = FAST_MODEL if model == "fast" else SMART_MODEL

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    kwargs = {
        "model":      resolved_model,
        "messages":   full_messages,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = groq_client.chat.completions.create(**kwargs)

    input_tokens  = response.usage.prompt_tokens     if response.usage else 0
    output_tokens = response.usage.completion_tokens if response.usage else 0
    cost          = estimate_cost(resolved_model, input_tokens, output_tokens)

    return response.choices[0].message.content, {
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost,
        "model":         resolved_model,
    }


def embed(texts: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer
    model      = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(texts, convert_to_list=True)
    return embeddings