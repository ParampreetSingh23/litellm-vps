"""Generate SQL that fills a RAW (LiteLLM) proxy database with realistic demo data.

Usage:
    python3 scripts/demo_data/seed_demo_data.py > seed.sql
    python3 scripts/demo_data/seed_demo_data.py --cleanup > cleanup.sql
    docker exec -i litellm_db psql -v ON_ERROR_STOP=1 -U llmproxy -d litellm < seed.sql

Every seeded row is marked (ids prefixed with ``demo-``, keys carry ``"demo_seed": true`` in
metadata), so ``--cleanup`` removes exactly what was added and leaves real data alone. Seeding
is idempotent: it removes the previous demo rows before inserting fresh ones, so rerunning it
refreshes the dates to end today.
"""

import argparse
import hashlib
import json
import math
import random
import sys
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

DAYS: Final = 30
LOG_DAYS: Final = 7
LOGS_PER_DAY: Final = 220
PREFIX: Final = "demo-"
MARKER: Final = '{"demo_seed": true}'


@dataclass(frozen=True, slots=True)
class Model:
    name: str
    provider: str
    input_price: float
    output_price: float
    cache_read_price: float
    latency_ms: int
    api_base: str


@dataclass(frozen=True, slots=True)
class Org:
    org_id: str
    alias: str
    budget: float


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    alias: str
    org_id: str
    budget: float


@dataclass(frozen=True, slots=True)
class User:
    user_id: str
    email: str
    alias: str
    team_id: str
    role: str


@dataclass(frozen=True, slots=True)
class Key:
    alias: str
    user_id: str
    team_id: str
    models: tuple[str, ...]
    tag: str
    endpoint: str
    daily_requests: int
    prompt_tokens: int
    completion_tokens: int
    cache_ratio: float
    autorouted: bool
    compressed: bool
    budget: float
    use_case: str

    @property
    def token(self) -> str:
        return hashlib.sha256(f"{PREFIX}{self.alias}".encode()).hexdigest()

    @property
    def key_name(self) -> str:
        return f"sk-...{self.token[-4:]}"


MODELS: Final = {
    m.name: m
    for m in (
        Model("gpt-5.6", "openai", 4e-06, 2e-05, 4e-07, 2400, "https://api.openai.com/v1"),
        Model("gpt-5.4-mini", "openai", 7.5e-07, 4.5e-06, 7.5e-08, 900, "https://api.openai.com/v1"),
        Model("claude-sonnet-5", "anthropic", 2e-06, 1e-05, 2e-07, 2100, "https://api.anthropic.com"),
        Model("claude-haiku-4-5", "anthropic", 1e-06, 5e-06, 1e-07, 800, "https://api.anthropic.com"),
        Model("claude-opus-5-5", "anthropic", 4e-06, 2e-05, 2e-07, 3600, "https://api.anthropic.com"),
        Model("gemini-3.8-flash", "gemini", 7.5e-07, 3.75e-06, 7.5e-08, 700, "https://generativelanguage.googleapis.com"),
        Model("text-embedding-3-small", "openai", 2e-08, 0.0, 0.0, 120, "https://api.openai.com/v1"),
    )
}

ORGS: Final = (
    Org(f"{PREFIX}org-product", "Product & Engineering", 12000.0),
    Org(f"{PREFIX}org-ops", "Operations", 6000.0),
)

TEAMS: Final = (
    Team(f"{PREFIX}team-eng", "Engineering", f"{PREFIX}org-product", 5000.0),
    Team(f"{PREFIX}team-ds", "Data Science", f"{PREFIX}org-product", 3000.0),
    Team(f"{PREFIX}team-support", "Customer Support", f"{PREFIX}org-ops", 2500.0),
    Team(f"{PREFIX}team-marketing", "Marketing", f"{PREFIX}org-ops", 1500.0),
    Team(f"{PREFIX}team-sales", "Sales", f"{PREFIX}org-ops", 800.0),
)

USERS: Final = (
    User(f"{PREFIX}user-aarav", "aarav.mehta@example.com", "Aarav Mehta", f"{PREFIX}team-eng", "internal_user"),
    User(f"{PREFIX}user-sophia", "sophia.chen@example.com", "Sophia Chen", f"{PREFIX}team-eng", "internal_user"),
    User(f"{PREFIX}user-daniel", "daniel.okafor@example.com", "Daniel Okafor", f"{PREFIX}team-ds", "internal_user"),
    User(f"{PREFIX}user-priya", "priya.nair@example.com", "Priya Nair", f"{PREFIX}team-ds", "internal_user"),
    User(f"{PREFIX}user-lucas", "lucas.martin@example.com", "Lucas Martin", f"{PREFIX}team-support", "internal_user"),
    User(f"{PREFIX}user-emma", "emma.wilson@example.com", "Emma Wilson", f"{PREFIX}team-support", "internal_user"),
    User(f"{PREFIX}user-kenji", "kenji.sato@example.com", "Kenji Sato", f"{PREFIX}team-marketing", "internal_user"),
    User(f"{PREFIX}user-olivia", "olivia.brown@example.com", "Olivia Brown", f"{PREFIX}team-sales", "internal_user"),
)

KEYS: Final = (
    Key("support-chatbot-prod", f"{PREFIX}user-lucas", f"{PREFIX}team-support", ("claude-haiku-4-5", "gpt-5.4-mini"),
        "customer-support", "/chat/completions", 1900, 2600, 320, 0.62, True, False, 900.0, "support"),
    Key("support-ticket-triage", f"{PREFIX}user-emma", f"{PREFIX}team-support", ("gpt-5.4-mini",),
        "customer-support", "/chat/completions", 1100, 900, 60, 0.35, True, False, 300.0, "triage"),
    Key("code-assistant", f"{PREFIX}user-aarav", f"{PREFIX}team-eng", ("claude-sonnet-5", "gpt-5.6"),
        "engineering", "/v1/messages", 650, 14000, 1100, 0.71, False, False, 2500.0, "code"),
    Key("ci-pr-reviewer", f"{PREFIX}user-sophia", f"{PREFIX}team-eng", ("claude-sonnet-5",),
        "engineering", "/v1/messages", 240, 9000, 700, 0.55, False, False, 900.0, "review"),
    Key("rag-knowledge-base", f"{PREFIX}user-daniel", f"{PREFIX}team-ds", ("gemini-3.8-flash", "text-embedding-3-small"),
        "rag-pipeline", "/chat/completions", 1400, 5200, 380, 0.18, False, True, 1200.0, "rag"),
    Key("model-eval-harness", f"{PREFIX}user-priya", f"{PREFIX}team-ds", ("claude-opus-5-5", "gpt-5.6"),
        "evaluation", "/chat/completions", 90, 6000, 1500, 0.05, False, False, 1500.0, "eval"),
    Key("content-generator", f"{PREFIX}user-kenji", f"{PREFIX}team-marketing", ("gpt-5.6", "claude-sonnet-5"),
        "marketing", "/chat/completions", 210, 1800, 1400, 0.25, True, False, 800.0, "content"),
    Key("seo-summarizer", f"{PREFIX}user-kenji", f"{PREFIX}team-marketing", ("gemini-3.8-flash",),
        "marketing", "/chat/completions", 380, 4200, 250, 0.1, False, True, 250.0, "summary"),
    Key("sales-email-assistant", f"{PREFIX}user-olivia", f"{PREFIX}team-sales", ("gpt-5.4-mini",),
        "sales", "/chat/completions", 300, 1500, 420, 0.4, True, False, 200.0, "email"),
)

END_USERS: Final = tuple(f"{PREFIX}customer-{n:03d}" for n in (101, 117, 142, 203, 256, 318, 377, 402))
TAGS: Final = tuple(sorted({k.tag for k in KEYS} | {"production"}))
GUARDRAILS: Final = (
    ("PII Masking", 0.021, 38.0),
    ("Prompt Injection Shield", 0.008, 55.0),
    ("Secrets Detection", 0.004, 12.0),
    ("Toxicity Filter", 0.012, 41.0),
)

CONVERSATIONS: Final[Mapping[str, Sequence[tuple[str, str]]]] = {
    "support": (
        ("I was charged twice for my subscription this month. Can you help?",
         "I'm sorry about the double charge. I can see two payments on your account from the 3rd. I've flagged the duplicate for a refund, which usually lands in 3-5 business days."),
        ("How do I reset my password? The link in the email expired.",
         "Reset links expire after 30 minutes. I've sent a fresh link to your registered email. If it doesn't arrive in 5 minutes, check your spam folder."),
        ("Where is my order #48213? It says shipped but hasn't moved in 4 days.",
         "Order #48213 is at the regional sorting hub and is scheduled for delivery tomorrow. I've added a note to prioritize it."),
    ),
    "triage": (
        ("Classify this ticket: 'App crashes when uploading a PDF larger than 20MB on Android.'",
         '{"category": "bug", "component": "mobile-upload", "priority": "high", "team": "mobile"}'),
        ("Classify this ticket: 'Can I get an invoice with my company VAT number?'",
         '{"category": "billing", "component": "invoices", "priority": "low", "team": "finance"}'),
    ),
    "code": (
        ("Refactor this function to avoid the N+1 query when loading orders with their line items.",
         "Load the line items in one query with a join and group them in memory. Here's the updated function using `prefetch_related('items')`, which cuts it from 1+N queries to 2."),
        ("Why does this React effect run twice in development?",
         "React 18 Strict Mode mounts, unmounts and remounts components in development to surface missing cleanups. Add a cleanup function to your effect and it will behave correctly in both modes."),
    ),
    "review": (
        ("Review this pull request diff for security issues.",
         "Two findings: the new endpoint builds SQL with string formatting (use parameters), and the upload handler trusts the client-provided content type. Everything else looks good."),
    ),
    "rag": (
        ("What is our refund policy for annual plans? Use the knowledge base.",
         "Annual plans can be refunded in full within 30 days of purchase. After 30 days, refunds are prorated for the unused months (source: Billing Policy v4, section 2.3)."),
        ("Summarize the onboarding steps for a new enterprise customer.",
         "1) Kickoff call and success plan, 2) SSO and SCIM setup, 3) data import, 4) admin training, 5) 30-day health review (source: Enterprise Onboarding Playbook)."),
    ),
    "eval": (
        ("Grade this answer for factual accuracy on a 1-5 scale and explain.",
         "Score: 4/5. The answer is correct about the main causes but omits the 2023 policy change mentioned in the reference."),
    ),
    "content": (
        ("Write a LinkedIn post announcing our new analytics dashboard.",
         "Big news: our new analytics dashboard is live. See spend, usage and performance in one place, with real-time insights for every team..."),
    ),
    "summary": (
        ("Summarize this 2,000-word blog post into 3 bullet points for the meta description.",
         "- How AI gateways cut LLM costs by 30-40%\n- Caching and smart routing explained\n- A checklist to get started in a week"),
    ),
    "email": (
        ("Draft a follow-up email to a prospect who attended our webinar yesterday.",
         "Subject: Great to have you at yesterday's webinar\n\nHi Sam, thanks for joining us. As promised, here are the slides and a 14-day trial link..."),
    ),
}


@dataclass(frozen=True, slots=True)
class Json:
    value: object


def q(value: object) -> str:
    if isinstance(value, Json):
        return q(json.dumps(value.value)) + "::jsonb"
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(round(value, 8)) if isinstance(value, float) else str(value)
    if isinstance(value, list | tuple):
        return "ARRAY[" + ",".join(q(v) for v in value) + "]::text[]" if value else "'{}'::text[]"
    if isinstance(value, dict):
        return q(json.dumps(value)) + "::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def insert(table: str, rows: Iterable[Mapping[str, object]], on_conflict: str = "") -> Iterator[str]:
    for row in rows:
        columns = ", ".join(f'"{c}"' for c in row)
        values = ", ".join(q(v) for v in row.values())
        yield f'INSERT INTO "{table}" ({columns}) VALUES ({values}){on_conflict};'


@dataclass(frozen=True, slots=True)
class Cell:
    day: str
    key: Key
    model: Model
    end_user: str
    requests: int
    failed: int
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    spend: float
    caching_savings: float
    injected_caching_savings: float
    autorouter_savings: float
    compression_saved_tokens: int
    compression_savings: float
    response_time_ms: int


def daily_cells(rng: random.Random, today: date) -> tuple[Cell, ...]:
    def cell(offset: int, key: Key, model_index: int) -> Cell:
        day: Final = today - timedelta(days=offset)
        growth: Final = 0.62 + 0.38 * (DAYS - offset) / DAYS
        weekday: Final = 0.55 if day.weekday() >= 5 else 1.0
        share: Final = (0.7, 0.3)[model_index] if len(key.models) > 1 else 1.0
        model: Final = MODELS[key.models[model_index]]
        requests: Final = max(1, int(key.daily_requests * growth * weekday * share * rng.uniform(0.85, 1.15)))
        failed: Final = int(requests * rng.uniform(0.002, 0.018))
        is_embedding: Final = model.name.startswith("text-embedding")
        prompt: Final = int(requests * (600 if is_embedding else key.prompt_tokens) * rng.uniform(0.9, 1.1))
        completion: Final = 0 if is_embedding else int(requests * key.completion_tokens * rng.uniform(0.9, 1.1))
        cache_read: Final = int(prompt * key.cache_ratio * rng.uniform(0.9, 1.05))
        spend: Final = (prompt - cache_read) * model.input_price + cache_read * model.cache_read_price + completion * model.output_price
        caching_savings: Final = cache_read * (model.input_price - model.cache_read_price)
        compression_saved: Final = int(prompt * 0.22) if key.compressed else 0
        return Cell(
            day=day.isoformat(),
            key=key,
            model=model,
            end_user=END_USERS[(KEYS.index(key) + offset) % len(END_USERS)],
            requests=requests,
            failed=failed,
            prompt_tokens=prompt,
            completion_tokens=completion,
            cache_read_tokens=cache_read,
            spend=spend,
            caching_savings=caching_savings,
            injected_caching_savings=caching_savings * 0.45,
            autorouter_savings=spend * rng.uniform(0.6, 0.9) if key.autorouted else 0.0,
            compression_saved_tokens=compression_saved,
            compression_savings=compression_saved * model.input_price,
            response_time_ms=int(requests * model.latency_ms * rng.uniform(0.85, 1.2)),
        )

    return tuple(
        cell(offset, key, index)
        for offset in range(DAYS)
        for key in KEYS
        for index in range(len(key.models))
    )


def daily_row(c: Cell, entity_column: str | None, entity_value: str | None) -> dict[str, object]:
    base: Final[dict[str, object]] = {"id": f"{PREFIX}{uuid.uuid4()}"}
    entity: Final[dict[str, object]] = {entity_column: entity_value} if entity_column else {}
    return base | entity | {
        "date": c.day,
        "api_key": c.key.token,
        "model": c.model.name,
        "model_group": c.model.name,
        "custom_llm_provider": c.model.provider,
        "endpoint": "/embeddings" if c.model.name.startswith("text-embedding") else c.key.endpoint,
        "prompt_tokens": c.prompt_tokens,
        "completion_tokens": c.completion_tokens,
        "cache_read_input_tokens": c.cache_read_tokens,
        "cache_creation_input_tokens": int(c.cache_read_tokens * 0.04),
        "compression_saved_tokens": c.compression_saved_tokens,
        "compression_savings_spend": c.compression_savings,
        "prompt_caching_savings_spend": c.caching_savings,
        "gateway_injected_caching_savings_spend": c.injected_caching_savings,
        "autorouter_savings_spend": c.autorouter_savings,
        "spend": c.spend,
        "api_requests": c.requests,
        "successful_requests": c.requests - c.failed,
        "failed_requests": c.failed,
        "total_response_time_ms": c.response_time_ms,
        "timed_requests": c.requests,
        "updated_at": "now()",
    }


def raw_now(sql: str) -> str:
    return sql.replace("'now()'", "(NOW() AT TIME ZONE 'UTC')")


def team_of(team_id: str) -> Team:
    return next(t for t in TEAMS if t.team_id == team_id)


def user_of(user_id: str) -> User:
    return next(u for u in USERS if u.user_id == user_id)


def spend_logs(rng: random.Random, now: datetime) -> Iterator[dict[str, object]]:
    weights: Final = [k.daily_requests for k in KEYS]
    for n in range(LOG_DAYS * LOGS_PER_DAY):
        key = rng.choices(KEYS, weights=weights)[0]
        model = MODELS[key.models[0] if len(key.models) == 1 or rng.random() < 0.7 else key.models[1]]
        start = now - timedelta(seconds=rng.uniform(60, LOG_DAYS * 86400))
        is_embedding = model.name.startswith("text-embedding")
        failed = rng.random() < 0.012
        duration = int(model.latency_ms * rng.uniform(0.6, 1.8))
        prompt = int((600 if is_embedding else key.prompt_tokens) * rng.uniform(0.6, 1.4))
        completion = 0 if is_embedding or failed else int(key.completion_tokens * rng.uniform(0.5, 1.5))
        cache_read = int(prompt * key.cache_ratio) if rng.random() < 0.85 else 0
        spend = 0.0 if failed else (prompt - cache_read) * model.input_price + cache_read * model.cache_read_price + completion * model.output_price
        question, answer = rng.choice(CONVERSATIONS[key.use_case])
        team = team_of(key.team_id)
        user = user_of(key.user_id)
        request_id = f"{PREFIX}{uuid.UUID(int=rng.getrandbits(128))}"
        session = f"{PREFIX}session-{n // 4:05d}" if key.use_case in ("support", "code") else None
        guardrails = [
            {
                "guardrail_name": name,
                "guardrail_mode": "pre_call",
                "guardrail_status": "guardrail_intervened" if rng.random() < rate else "success",
                "duration": round(latency / 1000 * rng.uniform(0.7, 1.3), 4),
                "start_time": start.timestamp(),
                "end_time": start.timestamp() + latency / 1000,
            }
            for name, rate, latency in GUARDRAILS[:2]
        ] if key.use_case in ("support", "rag", "email") else []
        metadata: dict[str, object] = {
            "status": "failure" if failed else "success",
            "user_api_key_alias": key.alias,
            "user_api_key_team_id": team.team_id,
            "user_api_key_team_alias": team.alias,
            "user_api_key_user_id": user.user_id,
            "user_api_key_user_email": user.email,
            "user_api_key_org_id": team.org_id,
            "litellm_overhead_time_ms": round(rng.uniform(3, 14), 2),
            "additional_usage_values": {"cache_read_input_tokens": cache_read, "cache_creation_input_tokens": 0},
            "guardrail_information": guardrails,
            "demo_seed": True,
        }
        if failed:
            metadata["error_information"] = {
                "error_code": "429",
                "error_class": "RateLimitError",
                "error_message": f"{model.provider} rate limit exceeded, retried on fallback deployment",
            }
        messages = [
            {"role": "system", "content": "You are a helpful assistant for RAW by Rabbitt customers."},
            {"role": "user", "content": question},
        ]
        response = {} if failed else {
            "id": f"chatcmpl-{request_id[-24:]}",
            "object": "chat.completion",
            "model": model.name,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": answer}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
        }
        yield {
            "request_id": request_id,
            "call_type": "aembedding" if is_embedding else "acompletion",
            "api_key": key.token,
            "spend": spend,
            "total_tokens": prompt + completion,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "startTime": start.replace(tzinfo=None).isoformat(sep=" "),
            "endTime": (start + timedelta(milliseconds=duration)).replace(tzinfo=None).isoformat(sep=" "),
            "completionStartTime": (start + timedelta(milliseconds=duration * 0.35)).replace(tzinfo=None).isoformat(sep=" "),
            "request_duration_ms": duration,
            "model": model.name,
            "model_id": f"{PREFIX}{model.name}",
            "model_group": model.name,
            "custom_llm_provider": model.provider,
            "api_base": model.api_base,
            "user": user.user_id,
            "metadata": metadata,
            "cache_hit": "False",
            "cache_key": "",
            "request_tags": Json([key.tag, "production"]),
            "team_id": team.team_id,
            "organization_id": team.org_id,
            "end_user": END_USERS[n % len(END_USERS)],
            "requester_ip_address": f"10.0.{rng.randint(1, 20)}.{rng.randint(2, 250)}",
            "messages": Json(messages),
            "response": response,
            "session_id": session,
            "status": "failure" if failed else "success",
            "litellm_call_id": str(uuid.UUID(int=rng.getrandbits(128))),
            "proxy_server_request": {"model": model.name, "messages": messages},
        }


def guardrail_metric_rows(rng: random.Random, today: date) -> Iterator[dict[str, object]]:
    for name, rate, latency in GUARDRAILS:
        for offset in range(DAYS):
            evaluated = int(2600 * (0.62 + 0.38 * (DAYS - offset) / DAYS) * rng.uniform(0.85, 1.15))
            blocked = int(evaluated * rate * rng.uniform(0.7, 1.3))
            flagged = int(evaluated * rate * 0.6)
            yield {
                "guardrail_id": name,
                "date": (today - timedelta(days=offset)).isoformat(),
                "requests_evaluated": evaluated,
                "passed_count": evaluated - blocked - flagged,
                "blocked_count": blocked,
                "flagged_count": flagged,
                "avg_score": round(rng.uniform(0.02, 0.12), 3),
                "avg_latency_ms": round(latency * rng.uniform(0.85, 1.2), 1),
                "updated_at": "now()",
            }


DAILY_TABLES: Final = (
    ("LiteLLM_DailyUserSpend", "user_id"),
    ("LiteLLM_DailyTeamSpend", "team_id"),
    ("LiteLLM_DailyTagSpend", "tag"),
    ("LiteLLM_DailyOrganizationSpend", "organization_id"),
    ("LiteLLM_DailyEndUserSpend", "end_user_id"),
)


def cleanup_sql() -> Iterator[str]:
    tokens: Final = ", ".join(q(k.token) for k in KEYS)
    yield "CREATE TEMP TABLE demo_days ON COMMIT DROP AS SELECT DISTINCT \"date\" FROM \"LiteLLM_DailyUserSpend\" " \
          f"WHERE api_key IN ({tokens});"
    for table, _ in DAILY_TABLES:
        yield f'DELETE FROM "{table}" WHERE api_key IN ({tokens});'
    yield f'DELETE FROM "LiteLLM_SpendLogs" WHERE request_id LIKE {q(PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_DailyGuardrailMetrics" WHERE guardrail_id IN ({", ".join(q(g[0]) for g in GUARDRAILS)});'
    yield f'DELETE FROM "LiteLLM_DailyGatewayRequests" WHERE route LIKE {q("%#demo")};'
    yield f'DELETE FROM "LiteLLM_VerificationToken" WHERE token IN ({tokens});'
    yield f'DELETE FROM "LiteLLM_TeamMembership" WHERE user_id LIKE {q(PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_UserTable" WHERE user_id LIKE {q(PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_TeamTable" WHERE team_id LIKE {q(PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_OrganizationTable" WHERE organization_id LIKE {q(PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_EndUserTable" WHERE user_id LIKE {q(PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_TagTable" WHERE created_by = {q(PREFIX + "seed")};'
    yield f'DELETE FROM "LiteLLM_BudgetTable" WHERE budget_id LIKE {q(PREFIX + "%")};'
    yield 'DELETE FROM "LiteLLM_DailyGlobalSpend" WHERE "date" IN (SELECT "date" FROM demo_days);'
    yield from reroll_global_sql("SELECT \"date\" FROM demo_days")


def reroll_global_sql(days_query: str) -> Iterator[str]:
    """Rebuild LiteLLM_DailyGlobalSpend for the given days exactly like the proxy's rollup cron."""
    keys: Final = ("date", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint")
    metrics: Final = (
        "prompt_tokens", "completion_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
        "compression_saved_tokens", "compression_savings_spend", "prompt_caching_savings_spend",
        "gateway_injected_caching_savings_spend", "autorouter_savings_spend", "spend", "api_requests",
        "successful_requests", "failed_requests", "total_response_time_ms", "timed_requests",
    )
    normalized: Final = ", ".join(f"COALESCE(\"{c}\", '')" for c in keys)
    yield (
        f'INSERT INTO "LiteLLM_DailyGlobalSpend" ("id", {", ".join(f"""\"{c}\"""" for c in keys)}, '
        f'{", ".join(f"""\"{c}\"""" for c in metrics)}, "updated_at") '
        f"SELECT gen_random_uuid()::text, {normalized}, {', '.join(f'SUM(\"{c}\")' for c in metrics)}, "
        "(NOW() AT TIME ZONE 'UTC') FROM \"LiteLLM_DailyUserSpend\" "
        f"WHERE \"date\" IN ({days_query}) AND \"date\" < (NOW() AT TIME ZONE 'UTC')::date::text "
        f"GROUP BY {normalized} "
        f"ON CONFLICT ({', '.join(f'\"{c}\"' for c in keys)}) DO UPDATE SET "
        f"{', '.join(f'\"{c}\" = EXCLUDED.\"{c}\"' for c in metrics)}, \"updated_at\" = (NOW() AT TIME ZONE 'UTC');"
    )


def seed_sql(rng: random.Random, now: datetime) -> Iterator[str]:
    cells: Final = daily_cells(rng, now.date())
    key_spend: Final = {k.alias: sum(c.spend for c in cells if c.key is k) for k in KEYS}
    team_spend: Final = {t.team_id: sum(c.spend for c in cells if c.key.team_id == t.team_id) for t in TEAMS}
    org_spend: Final = {o.org_id: sum(team_spend[t.team_id] for t in TEAMS if t.org_id == o.org_id) for o in ORGS}
    user_spend: Final = {u.user_id: sum(c.spend for c in cells if c.key.user_id == u.user_id) for u in USERS}
    end_user_spend: Final = {e: sum(c.spend for c in cells if c.end_user == e) for e in END_USERS}
    tag_spend: Final = {t: sum(c.spend for c in cells if c.key.tag == t) for t in TAGS}
    created: Final = (now - timedelta(days=DAYS + 14)).replace(tzinfo=None).isoformat(sep=" ")

    yield from insert("LiteLLM_BudgetTable", (
        {"budget_id": f"{PREFIX}budget-{o.org_id}", "max_budget": o.budget, "budget_duration": "30d",
         "created_by": f"{PREFIX}seed", "updated_by": f"{PREFIX}seed"} for o in ORGS))
    yield from insert("LiteLLM_OrganizationTable", (
        {"organization_id": o.org_id, "organization_alias": o.alias, "budget_id": f"{PREFIX}budget-{o.org_id}",
         "metadata": {"demo_seed": True}, "models": [], "spend": org_spend[o.org_id],
         "created_by": f"{PREFIX}seed", "updated_by": f"{PREFIX}seed", "created_at": created} for o in ORGS))
    yield from insert("LiteLLM_TeamTable", (
        {"team_id": t.team_id, "team_alias": t.alias, "organization_id": t.org_id,
         "admins": [u.user_id for u in USERS if u.team_id == t.team_id][:1],
         "members": [u.user_id for u in USERS if u.team_id == t.team_id],
         "members_with_roles": Json([{"role": "admin" if i == 0 else "user", "user_id": u.user_id, "user_email": u.email}
                                for i, u in enumerate(u for u in USERS if u.team_id == t.team_id)]),
         "metadata": {"demo_seed": True}, "max_budget": t.budget, "spend": team_spend[t.team_id],
         "models": sorted({m for k in KEYS if k.team_id == t.team_id for m in k.models}),  # comprehension-ok: flatten key models
         "budget_duration": "30d", "tpm_limit": 2000000, "rpm_limit": 5000, "created_at": created} for t in TEAMS))
    yield from insert("LiteLLM_UserTable", (
        {"user_id": u.user_id, "user_alias": u.alias, "user_email": u.email, "user_role": u.role, "team_id": u.team_id,
         "teams": [u.team_id], "organization_id": team_of(u.team_id).org_id, "models": [], "spend": user_spend[u.user_id],
         "max_budget": 1000.0, "metadata": {"demo_seed": True}, "created_at": created} for u in USERS))
    yield from insert("LiteLLM_TeamMembership", (
        {"user_id": u.user_id, "team_id": u.team_id, "spend": user_spend[u.user_id], "total_spend": user_spend[u.user_id]}
        for u in USERS))
    yield from insert("LiteLLM_VerificationToken", (
        {"token": k.token, "key_name": k.key_name, "key_alias": k.alias, "spend": key_spend[k.alias],
         "total_spend": key_spend[k.alias], "models": list(k.models), "user_id": k.user_id, "team_id": k.team_id,
         "organization_id": team_of(k.team_id).org_id, "max_budget": k.budget, "budget_duration": "30d",
         "tpm_limit": 500000, "rpm_limit": 1000, "metadata": {"demo_seed": True, "tags": [k.tag]},
         "created_at": created, "created_by": "default_user_id", "last_active": now.replace(tzinfo=None).isoformat(sep=" "),
         "blocked": False} for k in KEYS))
    yield from insert("LiteLLM_EndUserTable", (
        {"user_id": e, "alias": f"Customer {e[-3:]}", "spend": end_user_spend[e]} for e in END_USERS),
        ' ON CONFLICT ("user_id") DO NOTHING')
    yield from insert("LiteLLM_TagTable", (
        {"tag_name": t, "description": f"{t.replace('-', ' ').title()} traffic", "models": [], "spend": tag_spend.get(t, 0.0),
         "created_by": f"{PREFIX}seed"} for t in TAGS), ' ON CONFLICT ("tag_name") DO NOTHING')

    for table, column in DAILY_TABLES:
        entity = {
            "user_id": lambda c: c.key.user_id,
            "team_id": lambda c: c.key.team_id,
            "tag": lambda c: c.key.tag,
            "organization_id": lambda c: team_of(c.key.team_id).org_id,
            "end_user_id": lambda c: c.end_user,
        }[column]
        yield from (raw_now(s) for s in insert(table, (daily_row(c, column, entity(c)) for c in cells)))

    yield from (raw_now(s) for s in insert("LiteLLM_DailyGuardrailMetrics", guardrail_metric_rows(rng, now.date())))

    llm_by_day: Final = {c.day: 0 for c in cells}
    for c in cells:
        llm_by_day[c.day] += c.requests
    yield from (raw_now(s) for s in insert("LiteLLM_DailyGatewayRequests", (
        {"date": day, "category": category, "route": f"{route}#demo", "successful_requests": int(total * share * 0.99),
         "failed_requests": int(total * share * 0.01), "updated_at": "now()"}
        for day, total in llm_by_day.items()
        for category, route, share in (("llm", "/chat/completions", 0.78), ("llm", "/v1/messages", 0.17),
                                       ("llm", "/embeddings", 0.05), ("mcp", "/mcp", 0.03)))))  # comprehension-ok: day x route grid

    yield from insert("LiteLLM_SpendLogs", spend_logs(rng, now))
    yield from reroll_global_sql(f"SELECT DISTINCT \"date\" FROM \"LiteLLM_DailyUserSpend\" WHERE api_key IN "
                                 f"({', '.join(q(k.token) for k in KEYS)})")


def main() -> int:
    parser: Final = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cleanup", action="store_true", help="print SQL that removes all demo rows instead")
    parser.add_argument("--seed", type=int, default=7, help="random seed for reproducible data")
    args: Final = parser.parse_args()
    out: Final = sys.stdout
    out.write("BEGIN;\n")
    for statement in cleanup_sql():
        out.write(statement + "\n")
    if not args.cleanup:
        for statement in seed_sql(random.Random(args.seed), datetime.now(UTC)):
            out.write(statement + "\n")
    out.write("COMMIT;\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
