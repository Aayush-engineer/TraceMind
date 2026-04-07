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


def embed(texts: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer
    model      = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(texts, convert_to_list=True)
    return embeddings