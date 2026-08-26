"""Provider adapters for the preregistered three-model agentic audit."""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import certifi

from .agentic_v2 import EVIDENCE_IDS, OUTPUT_SCHEMA, PromptPacket


class ProviderError(RuntimeError):
    """A credential, transport, provider, or response error safe for manifests."""


@dataclass(frozen=True)
class ProviderResult:
    request_body: dict[str, Any]
    raw_response: dict[str, Any]
    response_text: str
    returned_model: str
    model_digest: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    estimated_cost_usd: float


def load_model_specs(experiment_config: Mapping[str, Any], selection: str) -> list[dict[str, Any]]:
    models = experiment_config.get("models", [])
    if not isinstance(models, list) or not models:
        raise ValueError("Experiment config must define a non-empty models list")
    wanted = [item.strip() for item in selection.split(",") if item.strip()]
    if not wanted or selection.strip().lower() == "all":
        selected = [dict(item) for item in models]
    else:
        by_id = {str(item["model_spec_id"]): item for item in models}
        unknown = sorted(set(wanted).difference(by_id))
        if unknown:
            raise ValueError(f"Unknown --model-panel model ids: {unknown}")
        selected = [dict(by_id[item]) for item in wanted]
    required = {"model_spec_id", "provider", "adapter", "model", "endpoint"}
    for spec in selected:
        missing = sorted(required.difference(spec))
        if missing:
            raise ValueError(f"Model spec {spec.get('model_spec_id')} missing fields: {missing}")
    return selected


def _secret_values(spec: Mapping[str, Any]) -> list[str]:
    env_name = str(spec.get("api_key_env", ""))
    value = os.environ.get(env_name, "") if env_name else ""
    return [value] if value else []


def redact_text(text: str, secrets: Sequence[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    # Providers sometimes echo a masked key (for example, a prefix followed by
    # asterisks and a suffix). Treat that representation as sensitive too.
    redacted = re.sub(r"\bsk-[A-Za-z0-9_.*-]+", "[REDACTED_API_KEY]", redacted)
    return redacted


def _verified_ssl_context() -> ssl.SSLContext:
    """Use an explicit maintained CA bundle without weakening TLS verification."""

    return ssl.create_default_context(cafile=certifi.where())


def _physical_memory_bytes() -> int:
    """Return total physical memory for a reproducible local-model preflight."""

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return int(result.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            return 0
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def resolve_endpoint(spec: Mapping[str, Any]) -> str:
    """Resolve an optional HTTPS-compatible gateway without persisting its credential."""

    endpoint = str(spec["endpoint"]).rstrip("/")
    env_name = str(spec.get("endpoint_env", ""))
    override = os.environ.get(env_name, "").strip() if env_name else ""
    if not override:
        return endpoint
    parsed = urllib.parse.urlsplit(override)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError(
            f"{env_name} must be an HTTPS base URL without credentials, query, or fragment"
        )
    base = override.rstrip("/")
    if base.endswith("/responses"):
        return base
    if base.endswith("/v1"):
        return f"{base}/responses"
    return f"{base}/v1/responses"


def _request_json(
    url: str,
    *,
    body: dict[str, Any] | None = None,
    api_key: str = "",
    timeout: float = 120.0,
    method: str = "POST",
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_verified_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise ProviderError(f"HTTP {exc.code} from {url}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ProviderError(f"Unable to reach {url}: {exc.reason}") from None
    except TimeoutError:
        raise ProviderError(f"Timed out while waiting for {url} after {timeout:g} seconds") from None
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Provider returned invalid JSON from {url}: {exc}") from None


def preflight(spec: Mapping[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    adapter = str(spec["adapter"])
    if adapter in {"openai_responses", "deepseek_chat"}:
        env_name = str(spec.get("api_key_env", ""))
        if not env_name or not os.environ.get(env_name):
            raise ProviderError(f"{env_name or 'API key environment variable'} is not set")
        return {
            "status": "ready",
            "model_digest": "remote_provider",
            "resolved_endpoint": resolve_endpoint(spec),
            "custom_endpoint": bool(
                spec.get("endpoint_env") and os.environ.get(str(spec["endpoint_env"]))
            ),
        }
    if adapter == "ollama_chat":
        endpoint = str(spec["endpoint"]).rstrip("/")
        tags = _request_json(f"{endpoint}/api/tags", method="GET", timeout=timeout)
        requested = str(spec["model"])
        models = tags.get("models", [])
        match = next(
            (
                item
                for item in models
                if str(item.get("name")) == requested or str(item.get("model")) == requested
            ),
            None,
        )
        if match is None:
            raise ProviderError(
                f"Ollama model {requested} is not installed. Run: ollama pull {requested}"
            )
        show = _request_json(
            f"{endpoint}/api/show",
            body={"model": requested},
            timeout=timeout,
        )
        native_contexts = [
            int(value)
            for key, value in (show.get("model_info", {}) or {}).items()
            if str(key).endswith(".context_length") and str(value).isdigit()
        ]
        native_context = max(native_contexts, default=0)
        configured_context = int(spec.get("context_length", 0) or 0)
        if native_context and configured_context > native_context:
            raise ProviderError(
                f"Configured context {configured_context} exceeds {requested} native context "
                f"{native_context}"
            )
        return {
            "status": "ready",
            "model_digest": str(match.get("digest", "")),
            "size_bytes": int(match.get("size", 0) or 0),
            "details": match.get("details", {}),
            "configured_context_length": configured_context,
            "native_context_length": native_context,
            "physical_memory_bytes": _physical_memory_bytes(),
        }
    raise ProviderError(f"Unknown provider adapter: {adapter}")


def build_request_body(
    spec: Mapping[str, Any],
    packet: PromptPacket,
    *,
    output_schema: Mapping[str, Any] = OUTPUT_SCHEMA,
    schema_name: str = "evidence_ladder_audit_v2",
) -> dict[str, Any]:
    adapter = str(spec["adapter"])
    model = str(spec["model"])
    max_tokens = int(spec.get("max_output_tokens", 1200))
    temperature = float(spec.get("temperature", 0))
    if adapter == "openai_responses":
        return {
            "model": model,
            "instructions": packet.system_prompt,
            "input": packet.user_prompt,
            "reasoning": {"effort": str(spec.get("reasoning_effort", "medium"))},
            "store": False,
            "max_output_tokens": max_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": dict(output_schema),
                }
            },
        }
    if adapter == "deepseek_chat":
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": packet.system_prompt},
                {"role": "user", "content": packet.user_prompt},
            ],
            "thinking": {"type": "enabled"},
            "reasoning_effort": str(spec.get("reasoning_effort", "high")),
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
    if adapter == "ollama_chat":
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": packet.system_prompt},
                {"role": "user", "content": packet.user_prompt},
            ],
            "format": dict(output_schema),
            "stream": False,
            "think": True,
            "options": {
                "temperature": temperature,
                "num_ctx": int(spec.get("context_length", 32768)),
                "num_predict": max_tokens,
                "seed": int(spec.get("seed", 0)),
            },
            "keep_alive": str(spec.get("keep_alive", "10m")),
        }
    raise ProviderError(f"Unknown provider adapter: {adapter}")


def _response_text(adapter: str, payload: Mapping[str, Any]) -> str:
    if adapter == "openai_responses":
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        pieces: list[str] = []
        for item in payload.get("output", []) or []:
            if not isinstance(item, Mapping) or item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                if isinstance(content, Mapping) and content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str):
                        pieces.append(text)
        return "\n".join(pieces).strip()
    if adapter == "deepseek_chat":
        choices = payload.get("choices", []) or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()
    if adapter == "ollama_chat":
        return str(payload.get("message", {}).get("content", "")).strip()
    return ""


def _usage(adapter: str, payload: Mapping[str, Any]) -> tuple[int, int, int]:
    if adapter == "ollama_chat":
        return (
            int(payload.get("prompt_eval_count", 0) or 0),
            int(payload.get("eval_count", 0) or 0),
            0,
        )
    usage = payload.get("usage", {}) or {}
    if adapter == "openai_responses":
        details = usage.get("output_tokens_details", {}) or {}
        return (
            int(usage.get("input_tokens", 0) or 0),
            int(usage.get("output_tokens", 0) or 0),
            int(details.get("reasoning_tokens", 0) or 0),
        )
    details = usage.get("completion_tokens_details", {}) or {}
    return (
        int(usage.get("prompt_tokens", 0) or 0),
        int(usage.get("completion_tokens", 0) or 0),
        int(details.get("reasoning_tokens", 0) or 0),
    )


def _estimated_cost(spec: Mapping[str, Any], input_tokens: int, output_tokens: int) -> float:
    pricing = spec.get("pricing_usd_per_million", {}) or {}
    input_rate = float(pricing.get("input_cache_miss", 0) or 0)
    output_rate = float(pricing.get("output", 0) or 0)
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def invoke(
    spec: Mapping[str, Any],
    packet: PromptPacket,
    *,
    timeout: float = 180.0,
    output_schema: Mapping[str, Any] = OUTPUT_SCHEMA,
    schema_name: str = "evidence_ladder_audit_v2",
) -> ProviderResult:
    adapter = str(spec["adapter"])
    body = build_request_body(
        spec, packet, output_schema=output_schema, schema_name=schema_name
    )
    api_key = ""
    if adapter in {"openai_responses", "deepseek_chat"}:
        env_name = str(spec.get("api_key_env", ""))
        api_key = os.environ.get(env_name, "")
        if not api_key:
            raise ProviderError(f"{env_name} is not set")
    endpoint = resolve_endpoint(spec)
    url = endpoint
    if adapter == "ollama_chat":
        url = f"{endpoint}/api/chat"
    try:
        payload = _request_json(url, body=body, api_key=api_key, timeout=timeout)
    except ProviderError as exc:
        raise ProviderError(redact_text(str(exc), _secret_values(spec))) from None
    response_text = _response_text(adapter, payload)
    if not response_text:
        raise ProviderError(f"{spec['model_spec_id']} returned no assistant content")
    input_tokens, output_tokens, reasoning_tokens = _usage(adapter, payload)
    returned_model = str(payload.get("model", spec["model"]))
    digest = ""
    if adapter == "ollama_chat":
        digest = str(preflight(spec, timeout=min(timeout, 20.0)).get("model_digest", ""))
    return ProviderResult(
        request_body=body,
        raw_response=dict(payload),
        response_text=response_text,
        returned_model=returned_model,
        model_digest=digest,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        estimated_cost_usd=_estimated_cost(spec, input_tokens, output_tokens),
    )


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("No JSON object found in model response") from None
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON response: {exc}") from None
    if not isinstance(payload, dict):
        raise ValueError("Model response JSON must be an object")
    return payload


def validate_response_against_schema(
    payload: Mapping[str, Any],
    *,
    output_schema: Mapping[str, Any],
    evidence_ids: Sequence[str],
) -> dict[str, Any]:
    """Validate the shared audit response shape against a case-specific schema."""

    required = set(output_schema["required"])
    missing = sorted(required.difference(payload))
    extras = sorted(set(payload).difference(required))
    if missing or extras:
        raise ValueError(f"Response schema fields missing={missing} extra={extras}")
    allowed = output_schema["properties"]
    normalized = dict(payload)
    for field, specification in allowed.items():
        if specification.get("type") != "string" or "enum" not in specification:
            continue
        value = str(payload[field])
        if value not in specification["enum"]:
            raise ValueError(f"Invalid {field}: {value}")
        normalized[field] = value
    for field in ("supporting_evidence_ids", "missing_evidence_slots"):
        value = payload[field]
        if not isinstance(value, list):
            raise ValueError(f"{field} must be an array")
        ids = [str(item) for item in value]
        if len(set(ids)) != len(ids) or set(ids).difference(evidence_ids):
            raise ValueError(f"Invalid or duplicate evidence IDs in {field}: {ids}")
        normalized[field] = ids
    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError):
        raise ValueError("confidence must be numeric") from None
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    normalized["confidence"] = confidence
    claim = str(payload["short_claim"]).strip()
    if not claim or len(claim) > 600:
        raise ValueError("short_claim must contain 1 to 600 characters")
    normalized["short_claim"] = claim
    return normalized


def validate_structured_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    return validate_response_against_schema(
        payload, output_schema=OUTPUT_SCHEMA, evidence_ids=EVIDENCE_IDS
    )


def repair_packet(
    original_text: str,
    *,
    output_schema: Mapping[str, Any] = OUTPUT_SCHEMA,
) -> PromptPacket:
    """Create a format-only repair request without evidence or answer content."""

    system = (
        "You are a JSON format repair utility. Preserve the submitted answer's meaning. "
        "Do not add evidence, factual claims, or new judgments. Return only valid JSON matching the schema."
    )
    user = json.dumps(
        {"malformed_answer": original_text[:12000], "required_schema": output_schema},
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    digest_source = f"{system}\n---USER---\n{user}"
    from .agentic_v2 import sha256_text

    digest = sha256_text(digest_source)
    return PromptPacket(system, user, digest, sha256_text(original_text), f"REPAIR-{digest[:16]}")
