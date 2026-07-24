"""Multi-provider LLM extraction: a small, deliberately minimal call_llm()
covering the major providers (Anthropic, OpenAI, Google, Mistral) via plain
REST calls with httpx (already a pipeline dependency) - no provider SDKs,
since we only need one capability (send a prompt, get text back) and four
SDKs would be a lot of dependency weight for that.

Used where a regex/parser genuinely can't do the job - e.g. a page listing
dates as written month names ("6. September") grouped under a year heading
that's structurally separate from each row (bundestag.de/parlament/wahlen/
wahltermine is the case that prompted this), which needs real language/
structure understanding, not pattern matching. See PLAN.md section 7,
Strategy 2.

Provider + model are chosen via environment variables so this works with
whichever provider the operator has a key for:

    LLM_PROVIDER=anthropic|openai|google|mistral|openrouter   (default: anthropic)
    LLM_MODEL=<model id>                            (default: a small/cheap model per provider)
    ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY / MISTRAL_API_KEY / OPENROUTER_API_KEY

openrouter is a single API proxying many providers/models (openrouter.ai) -
OPENROUTER_MODEL selects which one (e.g. "google/gemma-4-31b-it"), since
"a small/cheap default" doesn't mean anything for a router with hundreds of
unrelated models behind one key.

Model IDs drift over time - the defaults below are current as of this
writing; override with LLM_MODEL if a provider has moved on.
"""

import base64
import os
from typing import Optional

import httpx

DEFAULT_MODELS = {
    # "or" rather than dict .get(..., default): an *_MODEL var present in
    # .env but set to "" (as OPENROUTER_MODEL was) is still "present", so
    # os.environ.get(key, default) returns "" instead of falling back -
    # silently sending model="" to the API. "or" falls back on any falsy
    # value, not just a missing key.
    "anthropic": os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001",
    "openai": os.environ.get("OPENAI_MODEL") or "gpt-5-mini",
    "google": os.environ.get("GOOGLE_MODEL") or "gemini-3-5-flash",
    "mistral": os.environ.get("MISTRAL_MODEL") or "mistral-small-latest",
    # google/gemma-4-31b-it: the larger dense Gemma 4 variant (vs. the 26B
    # A4B MoE one) - chosen over it for better fine-detail vision accuracy,
    # since a "small" model already proved unreliable at reading precise
    # color-highlight extents (see the Saisonkalender PDF investigation).
    # Override via OPENROUTER_MODEL for a different model on the same key.
    "openrouter": os.environ.get("OPENROUTER_MODEL") or "google/gemma-4-31b-it",
}

REQUEST_TIMEOUT_SECONDS = 60


class LlmError(Exception):
    """Raised on missing configuration or a failed API call. Never caught
    silently by callers - if extraction can't run, the operator should see
    why, not get back fabricated or empty data pretending to be real."""


def call_llm(prompt: str, system: Optional[str] = None) -> str:
    """Sends `prompt` (+ optional system instructions) to the configured
    provider, returns the raw text response."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")

    if provider == "anthropic":
        return _call_anthropic(prompt, system, model)
    if provider == "openai":
        return _call_openai(prompt, system, model)
    if provider == "google":
        return _call_google(prompt, system, model)
    if provider == "mistral":
        return _call_mistral(prompt, system, model)
    if provider == "openrouter":
        return _call_openrouter(prompt, system, model)
    raise LlmError(f"Unknown LLM_PROVIDER '{provider}' (expected anthropic|openai|google|mistral|openrouter)")


def call_llm_vision(image_bytes: bytes, mime_type: str, prompt: str, system: Optional[str] = None) -> str:
    """Sends an image + prompt to the configured provider's vision-capable
    model, returns the raw text response. Same LLM_PROVIDER/LLM_MODEL env
    vars as call_llm - whichever provider the operator has a key for."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")

    if provider == "anthropic":
        return _call_anthropic_vision(image_bytes, mime_type, prompt, system, model)
    if provider == "openai":
        return _call_openai_vision(image_bytes, mime_type, prompt, system, model)
    if provider == "google":
        return _call_google_vision(image_bytes, mime_type, prompt, system, model)
    if provider == "mistral":
        return _call_mistral_vision(image_bytes, mime_type, prompt, system, model)
    if provider == "openrouter":
        return _call_openrouter_vision(image_bytes, mime_type, prompt, system, model)
    raise LlmError(f"Unknown LLM_PROVIDER '{provider}' (expected anthropic|openai|google|mistral|openrouter)")


def _require_key(env_var: str) -> str:
    key = os.environ.get(env_var)
    if not key:
        raise LlmError(f"{env_var} is not set - export it before using LLM extraction")
    return key


def _call_anthropic(prompt: str, system: Optional[str], model: str) -> str:
    api_key = _require_key("ANTHROPIC_API_KEY")
    # temperature=0: this is used for structured extraction (find dates in
    # text), not creative generation - the default sampling temperature
    # otherwise makes results inconsistent between runs on the same input.
    body = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"Anthropic API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_anthropic_vision(image_bytes: bytes, mime_type: str, prompt: str, system: Optional[str], model: str) -> str:
    api_key = _require_key("ANTHROPIC_API_KEY")
    body = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }
    if system:
        body["system"] = system
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"Anthropic API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai(prompt: str, system: Optional[str], model: str) -> str:
    api_key = _require_key("OPENAI_API_KEY")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"OpenAI API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_openai_vision(image_bytes: bytes, mime_type: str, prompt: str, system: Optional[str], model: str) -> str:
    api_key = _require_key("OPENAI_API_KEY")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    })
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"OpenAI API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_google(prompt: str, system: Optional[str], model: str) -> str:
    api_key = _require_key("GOOGLE_API_KEY")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"content-type": "application/json"},
        params={"key": api_key},
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"Google API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_google_vision(image_bytes: bytes, mime_type: str, prompt: str, system: Optional[str], model: str) -> str:
    api_key = _require_key("GOOGLE_API_KEY")
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
                {"text": prompt},
            ],
        }],
        "generationConfig": {"temperature": 0},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"content-type": "application/json"},
        params={"key": api_key},
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"Google API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_mistral(prompt: str, system: Optional[str], model: str) -> str:
    # Mistral's Chat Completions API is OpenAI-compatible - same request/
    # response shape, just a different endpoint and key.
    api_key = _require_key("MISTRAL_API_KEY")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = httpx.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"Mistral API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_mistral_vision(image_bytes: bytes, mime_type: str, prompt: str, system: Optional[str], model: str) -> str:
    # Same OpenAI-compatible image_url shape as _call_openai_vision, just a
    # different endpoint/key. Requires a Pixtral-family model - override
    # LLM_MODEL if the configured default isn't vision-capable.
    api_key = _require_key("MISTRAL_API_KEY")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    })
    resp = httpx.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"Mistral API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_openrouter(prompt: str, system: Optional[str], model: str) -> str:
    # OpenRouter (openrouter.ai) proxies many providers behind one
    # OpenAI-compatible Chat Completions endpoint - same request/response
    # shape as _call_openai/_call_mistral, just routed by `model` (e.g.
    # "google/gemma-4-31b-it") instead of a fixed provider.
    api_key = _require_key("OPENROUTER_API_KEY")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"OpenRouter API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_openrouter_vision(image_bytes: bytes, mime_type: str, prompt: str, system: Optional[str], model: str) -> str:
    # Same OpenAI-compatible image_url data-URL shape as _call_openai_vision/
    # _call_mistral_vision - requires a vision-capable model on OpenRouter's
    # side (check the model's "input_modalities" via openrouter.ai/api/v1/models
    # before assuming a given model id supports images).
    api_key = _require_key("OPENROUTER_API_KEY")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    })
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise LlmError(f"OpenRouter API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]
