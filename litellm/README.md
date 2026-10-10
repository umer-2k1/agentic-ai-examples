# Light LLM (LiteLLM)

LiteLLM — "Light LLM" — is an open-source library that gives you a single, unified interface to call 100+ LLMs (OpenAI, Anthropic, Vertex AI, Bedrock, Azure, Ollama, and more) using the OpenAI format.

- Website: https://www.litellm.ai/
- Docs: https://docs.litellm.ai/
- GitHub: https://github.com/BerriAI/litellm

## Features

- **One unified API for 100+ providers** — Call any provider with the same `completion()` interface and get a consistent output format, without re-learning each provider's API.
- **OpenAI-compatible format** — Requests and responses use the OpenAI Chat Completions schema, so it works as a drop-in replacement for the OpenAI client.
- **Streaming** — Stream responses chunk by chunk with `stream=True`.
- **Consistent exception handling** — Provider errors are mapped to OpenAI exception types (e.g. `RateLimitError`, `AuthenticationError`) so existing error handling keeps working.
- **Router with retry, fallback & load balancing** — Automatically retry and fall back across multiple deployments, and load balance across providers, regions, and keys.
- **Cost optimization & Auto Routing** — Route each request to the right model, use the lowest-cost deployment, and apply response/semantic caching and prompt compression.
- **Spend tracking & budgets** — Track usage and cost per key, user, team, and model; enforce hard budgets and rate limits (RPM/TPM).
- **Virtual keys & access control** — Issue scoped keys with per-key/team/user budgets and model access control.
- **Self-hosted LLM Gateway (Proxy)** — Run an OpenAI-compatible gateway with an admin UI for monitoring and management.
- **Guardrails** — Add content filtering, PII masking, prompt-injection detection, and other safety checks.
- **Observability** — Built-in callbacks for Langfuse, MLflow, Helicone, Lunary, OpenTelemetry, and more.
- **Agent & MCP Gateway** — Reach A2A agents and MCP tool servers through the same gateway as your LLMs.
- **Easy deployment** — Self-host with Docker, Helm, or Terraform, on your own Postgres and Redis, including fully air-gapped environments.

## Getting started

Install:

```bash
uv add litellm
```

Make a call:

```python
from litellm import completion

response = completion(
    model="openai/gpt-4o",
    messages=[{"role": "user", "content": "Hello, how are you?"}],
)
print(response.choices[0].message.content)
```

## License

MIT (open source). See the repository for details.
