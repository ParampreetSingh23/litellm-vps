"""Generate SQL that fills a RAW (LiteLLM) proxy database with realistic demo data.

Usage:
    python3 scripts/demo_data/seed_demo_data.py > seed.sql
    python3 scripts/demo_data/seed_demo_data.py --cleanup > cleanup.sql
    docker exec -i litellm_db psql -v ON_ERROR_STOP=1 -U llmproxy -d litellm < seed.sql

Demo ids look real but are derived deterministically from fixed names, and every demo request
is attached to one of the demo API keys, so ``--cleanup`` removes exactly what was added and leaves
real data alone. Seeding
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
from itertools import chain, product, repeat
from types import MappingProxyType
from typing import Final

DAYS: Final = 30
LOG_DAYS: Final = 7
LOGS_PER_DAY: Final = 220
LEGACY_PREFIX: Final = "demo-"
NAMESPACE: Final = uuid.UUID("7b1c2f0e-5a4d-4e8b-9c3f-2d6a8e1b4c90")


def sid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def customer_id(name: str) -> str:
    return "cus_" + hashlib.sha256(name.encode()).hexdigest()[:14]


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
        return hashlib.sha256(f"{LEGACY_PREFIX}{self.alias}".encode()).hexdigest()

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

EMAIL_DOMAIN: Final = "northfield-university.edu"

ORGS: Final = (
    Org(sid("org-academic-affairs"), "Academic Affairs", 10000.0),
    Org(sid("org-finance-admin"), "Finance & Administration", 8000.0),
    Org(sid("org-information-technology"), "Information Technology", 9000.0),
    Org(sid("org-research-libraries"), "Research & Libraries", 5000.0),
)

TEAMS: Final = (
    Team(sid("team-student-success"), "Student Success & Advising", sid("org-academic-affairs"), 2500.0),
    Team(sid("team-academic-technology"), "Academic Technology", sid("org-academic-affairs"), 2000.0),
    Team(sid("team-institutional-research"), "Institutional Research", sid("org-academic-affairs"), 1800.0),
    Team(sid("team-enrollment"), "Enrollment Management", sid("org-academic-affairs"), 1500.0),
    Team(sid("team-finance"), "Finance & Budget", sid("org-finance-admin"), 2200.0),
    Team(sid("team-hr"), "Human Resources", sid("org-finance-admin"), 800.0),
    Team(sid("team-communications"), "Communications & Marketing", sid("org-finance-admin"), 1200.0),
    Team(sid("team-service-desk"), "IT Service Desk", sid("org-information-technology"), 2000.0),
    Team(sid("team-infosec"), "Information Security", sid("org-information-technology"), 1500.0),
    Team(sid("team-software-dev"), "Software Development", sid("org-information-technology"), 3000.0),
    Team(sid("team-research-computing"), "Research Computing", sid("org-research-libraries"), 2500.0),
    Team(sid("team-libraries"), "University Libraries", sid("org-research-libraries"), 900.0),
)


def staff(handle: str, name: str, team: str) -> User:
    return User(sid(f"user-{handle}"), f"{handle.replace('-', '.')}@{EMAIL_DOMAIN}", name, sid(f"team-{team}"),
                "internal_user")


USERS: Final = (
    staff("maria-alvarez", "Maria Alvarez", "student-success"),
    staff("james-okafor", "James Okafor", "student-success"),
    staff("priya-raman", "Priya Raman", "academic-technology"),
    staff("tom-becker", "Tom Becker", "academic-technology"),
    staff("lena-hoffman", "Lena Hoffman", "institutional-research"),
    staff("daniel-kim", "Daniel Kim", "institutional-research"),
    staff("sofia-rossi", "Sofia Rossi", "enrollment"),
    staff("marcus-reed", "Marcus Reed", "enrollment"),
    staff("grace-liu", "Grace Liu", "finance"),
    staff("robert-hayes", "Robert Hayes", "finance"),
    staff("aisha-bello", "Aisha Bello", "hr"),
    staff("emily-carter", "Emily Carter", "communications"),
    staff("noah-fischer", "Noah Fischer", "communications"),
    staff("kevin-osei", "Kevin Osei", "service-desk"),
    staff("hannah-price", "Hannah Price", "service-desk"),
    staff("luis-moreno", "Luis Moreno", "service-desk"),
    staff("sarah-nguyen", "Sarah Nguyen", "infosec"),
    staff("omar-haddad", "Omar Haddad", "infosec"),
    staff("ethan-walsh", "Ethan Walsh", "software-dev"),
    staff("mei-tanaka", "Mei Tanaka", "software-dev"),
    staff("arjun-mehta", "Arjun Mehta", "software-dev"),
    staff("claire-dubois", "Claire Dubois", "research-computing"),
    staff("samuel-adeyemi", "Samuel Adeyemi", "research-computing"),
    staff("julia-novak", "Julia Novak", "libraries"),
    staff("ben-harper", "Ben Harper", "libraries"),
)


def uid(handle: str) -> str:
    return sid(f"user-{handle}")


def tid(team: str) -> str:
    return sid(f"team-{team}")


KEYS: Final = (
    Key("it-helpdesk-bot", uid("kevin-osei"), tid("service-desk"), ("claude-haiku-4-5", "gpt-5.4-mini"),
        "it-support", "/chat/completions", 2400, 2200, 300, 0.64, True, False, 900.0, "helpdesk"),
    Key("developer-code-assistant", uid("ethan-walsh"), tid("software-dev"), ("claude-sonnet-5", "gpt-5.6"),
        "engineering", "/v1/messages", 700, 14000, 1100, 0.71, False, False, 2500.0, "code"),
    Key("ci-code-review", uid("mei-tanaka"), tid("software-dev"), ("claude-sonnet-5",),
        "engineering", "/v1/messages", 200, 9000, 700, 0.55, False, False, 800.0, "review"),
    Key("research-copilot", uid("claire-dubois"), tid("research-computing"), ("claude-opus-5-5", "claude-sonnet-5"),
        "research", "/chat/completions", 300, 9000, 1300, 0.45, False, False, 2000.0, "research"),
    Key("library-search-rag", uid("julia-novak"), tid("libraries"), ("gemini-3.8-flash", "text-embedding-3-small"),
        "library", "/chat/completions", 1100, 5200, 380, 0.18, False, True, 700.0, "library"),
    Key("hr-policy-qa", uid("aisha-bello"), tid("hr"), ("gpt-5.4-mini",),
        "human-resources", "/chat/completions", 350, 3000, 250, 0.6, True, False, 300.0, "hr"),
    Key("comms-content-writer", uid("emily-carter"), tid("communications"), ("gpt-5.6", "claude-sonnet-5"),
        "communications", "/chat/completions", 220, 1800, 1400, 0.25, True, False, 800.0, "content"),
    Key("meeting-notes-summarizer", uid("tom-becker"), tid("academic-technology"), ("gemini-3.8-flash",),
        "productivity", "/chat/completions", 500, 7000, 450, 0.1, False, True, 350.0, "notes"),
    Key("translation-service", uid("noah-fischer"), tid("communications"), ("gpt-5.4-mini",),
        "communications", "/chat/completions", 400, 900, 950, 0.2, False, False, 250.0, "translation"),
    Key("course-engagement-insights", uid("priya-raman"), tid("academic-technology"),
        ("claude-sonnet-5", "gpt-5.4-mini"),
        "academic-technology", "/chat/completions", 900, 4800, 450, 0.58, True, False, 900.0, "engagement"),
    Key("advising-assistant", uid("maria-alvarez"), tid("student-success"), ("claude-haiku-4-5", "gpt-5.4-mini"),
        "student-success", "/chat/completions", 800, 2400, 420, 0.4, True, False, 500.0, "advising"),
    Key("enrollment-inquiry-bot", uid("sofia-rossi"), tid("enrollment"), ("gemini-3.8-flash",),
        "enrollment", "/chat/completions", 700, 1800, 260, 0.35, True, True, 250.0, "admissions"),
    Key("finance-planning-assistant", uid("grace-liu"), tid("finance"), ("claude-opus-5-5", "gpt-5.6"),
        "finance", "/chat/completions", 150, 12000, 1600, 0.66, False, False, 1500.0, "forecast"),
    Key("procurement-spend-analyzer", uid("robert-hayes"), tid("finance"), ("claude-sonnet-5",),
        "finance", "/v1/messages", 250, 8000, 900, 0.6, False, False, 700.0, "spend"),
    Key("ir-reporting-assistant", uid("lena-hoffman"), tid("institutional-research"),
        ("gemini-3.8-flash", "text-embedding-3-small"),
        "institutional-research", "/chat/completions", 400, 6400, 500, 0.2, False, True, 600.0, "reporting"),
    Key("model-eval-suite", uid("sarah-nguyen"), tid("infosec"), ("claude-opus-5-5", "gpt-5.6"),
        "security", "/chat/completions", 110, 6000, 1400, 0.05, False, False, 1000.0, "eval"),
    Key("security-log-triage", uid("omar-haddad"), tid("infosec"), ("claude-sonnet-5",),
        "security", "/v1/messages", 300, 10000, 600, 0.5, False, False, 800.0, "secops"),
)

END_USERS: Final = tuple(customer_id(f"customer-{n:03d}") for n in (101, 117, 142, 203, 256, 318, 377, 402))
TAGS: Final = tuple(sorted({k.tag for k in KEYS} | {"production"}))
GUARDRAILS: Final = (
    ("PII Masking", 0.021, 38.0),
    ("Prompt Injection Shield", 0.008, 55.0),
    ("Secrets Detection", 0.004, 12.0),
    ("Toxicity Filter", 0.012, 41.0),
    ("Responsible AI Filter", 0.006, 47.0),
)
GUARDRAIL_STATS: Final = MappingProxyType({name: (rate, latency) for name, rate, latency in GUARDRAILS})
POST_CALL_GUARDRAILS: Final = frozenset({"Toxicity Filter", "Responsible AI Filter"})
GUARDRAIL_REASONS: Final = MappingProxyType({
    "PII Masking": "Masked 1 STUDENT_ID and 1 EMAIL before the request reached the model",
    "Prompt Injection Shield": "Blocked: prompt matched prompt_injection_jailbreak (severity medium)",
    "Secrets Detection": "Blocked: request contained a generic_api_key pattern",
    "Toxicity Filter": "Blocked: response matched denied_insults (severity medium)",
    "Responsible AI Filter": "Blocked: response matched bias_gender (severity medium)",
})
RESTRICTED_GUARDRAILS: Final = ("PII Masking", "Prompt Injection Shield", "Responsible AI Filter")
ENGINEERING_GUARDRAILS: Final = ("Secrets Detection", "Prompt Injection Shield")
PUBLIC_CONTENT_GUARDRAILS: Final = ("Prompt Injection Shield", "Toxicity Filter", "Responsible AI Filter")
GUARDRAILS_BY_USE_CASE: Final = MappingProxyType({
    "engagement": RESTRICTED_GUARDRAILS,
    "advising": RESTRICTED_GUARDRAILS,
    "admissions": PUBLIC_CONTENT_GUARDRAILS,
    "hr": RESTRICTED_GUARDRAILS,
    "helpdesk": ("PII Masking", "Prompt Injection Shield", "Toxicity Filter"),
    "code": ENGINEERING_GUARDRAILS,
    "review": ENGINEERING_GUARDRAILS,
    "secops": ENGINEERING_GUARDRAILS,
    "content": PUBLIC_CONTENT_GUARDRAILS,
    "translation": ("Toxicity Filter",),
})
SESSION_USE_CASES: Final = frozenset({"helpdesk", "advising", "code"})

CONVERSATIONS: Final[Mapping[str, Sequence[tuple[str, str]]]] = {
    "helpdesk": (
        ("My VPN keeps disconnecting every 10 minutes when I work from home. What can I try?",
         "Update the VPN client to the latest version from the software portal, then switch the protocol to "
         "IKEv2 in settings. If it still drops, run the network diagnostic and attach the report to ticket "
         "INC0048213 so the network team can check your connection."),
        ("How do I get access to the shared drive for the Biology department?",
         "Access is granted by the department's data steward. I've opened request RITM0021764 and routed it to "
         "them. You'll get an email once it's approved, usually within one business day."),
        ("Outlook says my mailbox is full. How do I archive old email?",
         "Go to File, then Tools, then Mailbox Cleanup, and choose Archive. Items older than 12 months move to "
         "your online archive, which doesn't count against your quota."),
    ),
    "code": (
        ("Refactor this function to avoid the N+1 query when loading courses with their sections.",
         "Load the sections in one query with a join and group them in memory. Using "
         "`prefetch_related('sections')` cuts it from 1+N queries to 2."),
        ("Why does this React effect run twice in development?",
         "React Strict Mode mounts, unmounts and remounts components in development to surface missing "
         "cleanups. Add a cleanup function to the effect and it behaves correctly in both modes."),
    ),
    "review": (
        ("Review this pull request diff for security issues.",
         "Two findings: the new endpoint builds SQL with string formatting (use parameters), and the upload "
         "handler trusts the client-provided content type. Everything else looks good."),
    ),
    "research": (
        ("Summarize the methods section of this grant proposal in 150 words for the review committee.",
         "The study uses a mixed-methods design across three sites: a longitudinal survey of 1,200 participants, "
         "followed by 40 semi-structured interviews. Quantitative data are analyzed with multilevel models; "
         "interviews are coded thematically by two independent raters."),
        ("Suggest a statistical test for comparing pre and post scores across four treatment groups.",
         "Use a mixed ANOVA with time as the within-subjects factor and group as the between-subjects factor. "
         "If normality is violated, consider a linear mixed model with robust standard errors."),
    ),
    "library": (
        ("Find peer-reviewed articles from the last 5 years on microplastics in freshwater systems.",
         "I found 38 matching articles in the library databases. The three most cited are listed below with "
         "links to full text through the proxy. Want me to narrow them to field studies only?"),
    ),
    "hr": (
        ("How many days of parental leave do full-time staff get?",
         "Full-time staff get 12 weeks of paid parental leave after 6 months of service (Staff Handbook, "
         "section 7.4). Contact HR Benefits to start the request."),
    ),
    "content": (
        ("Write a short campus newsletter item announcing the new study space in the main library.",
         "The main library's third floor has reopened as a 24/7 study space with 120 new seats, bookable group "
         "rooms and extra charging stations. Reserve a room through the library website."),
    ),
    "notes": (
        ("Summarize this 60-minute curriculum committee meeting transcript into decisions and action items.",
         "Decisions: approve the revised statistics prerequisite and pilot the new capstone format in spring. "
         "Actions: registrar to update the catalog by Nov 1; department chairs to nominate pilot sections."),
    ),
    "translation": (
        ("Translate this orientation welcome message into Spanish and Vietnamese.",
         "Spanish: Bienvenidos a la orientación. Hoy conocerán el campus y a sus asesores.\n"
         "Vietnamese: Chào mừng các bạn đến với buổi định hướng. Hôm nay các bạn sẽ tham quan khuôn viên "
         "và gặp cố vấn học tập."),
    ),
    "engagement": (
        ("Course engagement summary for BIO 101: [STUDENT_ID_REDACTED] missed 3 of the last 5 assignments, "
         "quiz average dropped from 82% to 61%, last LMS login 9 days ago. Assess risk and suggest outreach.",
         '{"risk_level": "high", "drivers": ["missing assignments", "grade decline", "low LMS engagement"], '
         '"recommended_action": "Advisor outreach within 48 hours and a tutoring referral"}'),
    ),
    "advising": (
        ("Draft an advising note for a student considering dropping below full-time enrollment.",
         "Discussed reducing to 9 credits. Reviewed the impact on financial aid and on-time graduation. Student "
         "will meet Financial Aid before the add/drop deadline. Follow-up in 7 days."),
        ("Summarize this student's last three advising appointments before my meeting.",
         "Main themes: balancing a part-time job, interest in switching to Data Science, and a hold on "
         "registration that was cleared last week. Open item: confirm the change-of-major form."),
    ),
    "admissions": (
        ("What is the application deadline for fall transfer students, and do you accept AP credit?",
         "The fall transfer deadline is March 1. AP scores of 4 or 5 usually earn course credit; the Registrar "
         "makes the final evaluation after you enroll."),
    ),
    "forecast": (
        ("Using the GL actuals for Q1-Q3, forecast year-end spend for the Facilities department.",
         "Projected year-end spend is $4.82M against a $4.6M budget (+4.8%). The overrun is driven by "
         "utilities (+11% YoY). 80% interval: $4.71M to $4.95M."),
    ),
    "spend": (
        ("Flag unusual vendor payments in the September AP extract.",
         "Two anomalies: invoice AP-77412 was paid twice ($18,400 each), and a new vendor has three payments just "
         "under the $10,000 approval threshold. Recommend review by Procurement."),
    ),
    "reporting": (
        ("Summarize fall enrollment and retention for the trustees' dashboard.",
         "Fall enrollment is 18,240 (+2.1% YoY). First-year to second-year retention is 84.6%, up 1.3 points. "
         "Pell-eligible retention trails the overall rate by 4.2 points."),
    ),
    "eval": (
        ("Score these 50 sampled advising responses for accuracy, tone and consistency across student groups.",
         '{"accuracy": 0.94, "tone": 0.97, "max_group_gap": 0.03, "status": "pass", '
         '"note": "No group differs by more than 3 points on any criterion."}'),
        ("Compare this week's model outputs with last month's baseline and report any drift.",
         "Output length and refusal rate are stable. Accuracy on the reference set is 0.91 vs 0.92 baseline, "
         "within tolerance. No action needed."),
    ),
    "secops": (
        ("Triage these 200 failed-login alerts from the last hour.",
         "180 come from one IP range hitting the student portal with common passwords, a likely spray attack. "
         "Recommend blocking the range at the WAF and forcing resets for the 3 accounts that later logged in."),
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
        target = table if "." in table else f'"{table}"'
        yield f"INSERT INTO {target} ({columns}) VALUES ({values}){on_conflict};"


def upsert(table: str, row: Mapping[str, object], conflict_column: str) -> str:
    updates: Final = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in row if c != conflict_column)
    return next(insert(table, (row,), f' ON CONFLICT ("{conflict_column}") DO UPDATE SET {updates}'))


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


ACADEMIC_CALENDAR: Final = (
    (((8, 20), (9, 10)), 1.3),
    (((1, 10), (1, 25)), 1.3),
    (((10, 10), (10, 25)), 1.2),
    (((3, 1), (3, 12)), 1.2),
    (((12, 1), (12, 15)), 1.35),
    (((4, 25), (5, 10)), 1.35),
    (((11, 24), (11, 30)), 0.6),
    (((12, 20), (12, 31)), 0.5),
    (((1, 1), (1, 5)), 0.5),
    (((3, 16), (3, 22)), 0.6),
)


def season(day: date, key: Key) -> float:
    academic: Final = next((f for (lo, hi), f in ACADEMIC_CALENDAR if lo <= (day.month, day.day) <= hi), 1.0)
    fiscal_close: Final = 1.8 if key.tag == "finance" and day.day >= 26 else 1.0
    return academic * fiscal_close


def daily_cells(rng: random.Random, today: date) -> tuple[Cell, ...]:
    def cell(offset: int, key: Key, model_index: int) -> Cell:
        day: Final = today - timedelta(days=offset)
        growth: Final = 0.62 + 0.38 * (DAYS - offset) / DAYS
        weekday: Final = 0.55 if day.weekday() >= 5 else 1.0
        share: Final = (0.7, 0.3)[model_index] if len(key.models) > 1 else 1.0
        model: Final = MODELS[key.models[model_index]]
        volume: Final = key.daily_requests * growth * weekday * season(day, key) * share
        requests: Final = max(1, int(volume * rng.uniform(0.85, 1.15)))
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
    base: Final[dict[str, object]] = {"id": str(uuid.uuid4())}
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


def guardrail_run(name: str, intervened: bool, jitter: float, start: datetime) -> dict[str, object]:
    latency: Final = GUARDRAIL_STATS[name][1] * jitter / 1000
    return {
        "guardrail_name": name,
        "guardrail_mode": "post_call" if name in POST_CALL_GUARDRAILS else "pre_call",
        "guardrail_status": "guardrail_intervened" if intervened else "success",
        "guardrail_response": GUARDRAIL_REASONS[name] if intervened else None,
        "duration": round(latency, 4),
        "start_time": start.timestamp(),
        "end_time": start.timestamp() + latency,
    }


def guardrail_index_rows(logs: Sequence[Mapping[str, object]]) -> Iterator[dict[str, object]]:
    for log in logs:
        metadata = log["metadata"]
        runs = metadata["guardrail_information"] if isinstance(metadata, dict) else []
        for run in runs:
            yield {"request_id": log["request_id"], "guardrail_id": run["guardrail_name"], "start_time": log["startTime"]}


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
        request_id = str(uuid.UUID(int=rng.getrandbits(128)))
        session = sid(f"session-{n // 4:05d}") if key.use_case in SESSION_USE_CASES else None
        guardrails = [
            guardrail_run(name, rng.random() < GUARDRAIL_STATS[name][0], rng.uniform(0.7, 1.3), start)
            for name in GUARDRAILS_BY_USE_CASE.get(key.use_case, ("Prompt Injection Shield",))
        ]
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
        }
        if failed:
            metadata["error_information"] = {
                "error_code": "429",
                "error_class": "RateLimitError",
                "error_message": f"{model.provider} rate limit exceeded, retried on fallback deployment",
            }
        messages = [
            {"role": "system", "content": "You are a helpful assistant for university staff and students."},
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
            "model_id": sid(f"model-{model.name}"),
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


GATEWAY_ROUTES: Final = (
    ("llm", "/chat/completions", 0.78),
    ("llm", "/v1/messages", 0.17),
    ("llm", "/embeddings", 0.05),
    ("mcp", "/mcp", 0.03),
)


def gateway_rows(cells: Sequence[Cell]) -> Iterator[dict[str, object]]:
    days: Final = sorted({c.day for c in cells})
    for day in days:
        total = sum(c.requests for c in cells if c.day == day)
        for category, route, share in GATEWAY_ROUTES:
            yield {
                "date": day,
                "category": category,
                "route": route,
                "successful_requests": int(total * share * 0.99),
                "failed_requests": int(total * share * 0.01),
            }


GUARDRAIL_CONFIGS: Final = json.loads(
    r'''[
 {
  "guardrail_name": "PII Masking",
  "litellm_params": {
   "guardrail": "litellm_content_filter",
   "mode": "pre_call",
   "default_on": false,
   "patterns": [
    {
     "pattern_type": "prebuilt",
     "pattern_name": "email",
     "action": "MASK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "us_phone",
     "action": "MASK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "credit_card",
     "action": "MASK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "us_ssn",
     "action": "MASK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "passport_india",
     "action": "MASK"
    },
    {
     "pattern_type": "regex",
     "name": "student_id",
     "pattern": "\\b[SU]\\d{7,9}\\b",
     "action": "MASK"
    }
   ]
  },
  "guardrail_info": {
   "type": "PII",
   "description": "Masks student IDs, SSNs, emails, phone numbers and card numbers before prompts reach the model (FERPA)."
  }
 },
 {
  "guardrail_name": "Prompt Injection Shield",
  "litellm_params": {
   "guardrail": "litellm_content_filter",
   "mode": "pre_call",
   "default_on": false,
   "categories": [
    {
     "category": "prompt_injection_jailbreak",
     "enabled": true,
     "action": "BLOCK",
     "severity_threshold": "medium"
    },
    {
     "category": "prompt_injection_data_exfiltration",
     "enabled": true,
     "action": "BLOCK",
     "severity_threshold": "medium"
    },
    {
     "category": "prompt_injection_sql",
     "enabled": true,
     "action": "BLOCK",
     "severity_threshold": "medium"
    }
   ]
  },
  "guardrail_info": {
   "type": "Security",
   "description": "Blocks jailbreaks, data-exfiltration attempts and SQL injection in prompts."
  }
 },
 {
  "guardrail_name": "Secrets Detection",
  "litellm_params": {
   "guardrail": "litellm_content_filter",
   "mode": "pre_call",
   "default_on": false,
   "patterns": [
    {
     "pattern_type": "prebuilt",
     "pattern_name": "aws_access_key",
     "action": "BLOCK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "aws_secret_key",
     "action": "BLOCK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "github_token",
     "action": "BLOCK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "slack_token",
     "action": "BLOCK"
    },
    {
     "pattern_type": "prebuilt",
     "pattern_name": "generic_api_key",
     "action": "BLOCK"
    }
   ]
  },
  "guardrail_info": {
   "type": "Security",
   "description": "Stops API keys and cloud credentials from being sent to third-party models."
  }
 },
 {
  "guardrail_name": "Toxicity Filter",
  "litellm_params": {
   "guardrail": "litellm_content_filter",
   "mode": "post_call",
   "default_on": false,
   "categories": [
    {
     "category": "harm_toxic_abuse",
     "enabled": true,
     "action": "BLOCK",
     "severity_threshold": "medium"
    },
    {
     "category": "harmful_violence",
     "enabled": true,
     "action": "BLOCK",
     "severity_threshold": "medium"
    },
    {
     "category": "denied_insults",
     "enabled": true,
     "action": "BLOCK",
     "severity_threshold": "medium"
    }
   ]
  },
  "guardrail_info": {
   "type": "Content Safety",
   "description": "Blocks abusive, violent or insulting model responses."
  }
 },
 {
  "guardrail_name": "Responsible AI Filter",
  "litellm_params": {
   "guardrail": "litellm_content_filter",
   "mode": "post_call",
   "default_on": false,
   "categories": [
    {"category": "bias_racial", "enabled": true, "action": "BLOCK", "severity_threshold": "medium"},
    {"category": "bias_gender", "enabled": true, "action": "BLOCK", "severity_threshold": "medium"},
    {"category": "bias_religious", "enabled": true, "action": "BLOCK", "severity_threshold": "medium"},
    {"category": "bias_sexual_orientation", "enabled": true, "action": "BLOCK", "severity_threshold": "medium"},
    {"category": "age_discrimination", "enabled": true, "action": "BLOCK", "severity_threshold": "medium"}
   ]
  },
  "guardrail_info": {
   "type": "Ethics & Compliance",
   "description": "Blocks model responses with racial, gender, religious, sexual-orientation or age bias."
  }
 }
]'''
)


SEED_ACTOR: Final = sid("seed-admin")


def all_ids() -> tuple[str, ...]:
    return (
        tuple(o.org_id for o in ORGS)
        + tuple(sid(f"budget-{o.org_id}") for o in ORGS)
        + tuple(t.team_id for t in TEAMS)
        + tuple(u.user_id for u in USERS)
        + tuple(sid(f"user-{n}") for n in ("aarav", "sophia", "daniel", "priya", "lucas", "emma", "kenji", "olivia"))
        + END_USERS
        + tuple(sid(f"guardrail-{g['guardrail_name']}") for g in GUARDRAIL_CONFIGS)
    )


DAILY_TABLES: Final = (
    ("LiteLLM_DailyUserSpend", "user_id"),
    ("LiteLLM_DailyTeamSpend", "team_id"),
    ("LiteLLM_DailyTagSpend", "tag"),
    ("LiteLLM_DailyOrganizationSpend", "organization_id"),
    ("LiteLLM_DailyEndUserSpend", "end_user_id"),
)


def model_id(name: str) -> str:
    return sid(f"model-{name}")


def key_of(alias: str) -> Key:
    return next(k for k in KEYS if k.alias == alias)


def ts(moment: datetime) -> str:
    return moment.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")


ALL_TEAM_SLUGS: Final = tuple(t.alias for t in TEAMS)

ACCESS_GROUPS: Final = (
    ("general-use-models", "General-purpose models approved for everyday work",
     ("gemini-3.8-flash", "gpt-5.4-mini", "claude-haiku-4-5", "claude-sonnet-5", "text-embedding-3-small"),
     tuple(t.team_id for t in TEAMS)),
    ("restricted-data-models", "Models covered by a signed data protection agreement, approved for student and "
     "employee records", ("claude-haiku-4-5", "gpt-5.4-mini", "claude-sonnet-5"),
     (tid("student-success"), tid("academic-technology"), tid("enrollment"), tid("hr"))),
    ("advanced-reasoning-models", "High-cost reasoning models, enabled per team after budget approval",
     ("claude-opus-5-5", "gpt-5.6"),
     (tid("research-computing"), tid("finance"), tid("infosec"), tid("software-dev"), tid("communications"))),
)


def access_groups_of(team_id: str) -> list[str]:
    return [sid(f"access-group-{name}") for name, _, _, teams in ACCESS_GROUPS if team_id in teams]


@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    description: str
    guardrails: tuple[str, ...]
    inherit: str | None
    teams: tuple[str, ...]
    versions: int
    block_rate: float


POLICIES: Final = (
    Policy("baseline-safety", "Applies to every team: blocks prompt injection and leaked credentials",
           ("Prompt Injection Shield", "Secrets Detection"), None, ALL_TEAM_SLUGS, 2, 0.006),
    Policy("restricted-data", "Student and employee records: masks personal identifiers before any model call",
           ("PII Masking",), "baseline-safety",
           ("Student Success & Advising", "Academic Technology", "Enrollment Management", "Human Resources"), 3, 0.019),
    Policy("research-data", "Research data under IRB protocols: masks participant identifiers",
           ("PII Masking",), "baseline-safety",
           ("Research Computing", "University Libraries", "Institutional Research"), 1, 0.011),
    Policy("financial-data", "Financial systems data: masks card and bank details and blocks credentials",
           ("PII Masking", "Secrets Detection"), "baseline-safety", ("Finance & Budget",), 2, 0.014),
    Policy("responsible-ai", "Public and student-facing responses: blocks toxic or biased output",
           ("Toxicity Filter", "Responsible AI Filter"), None,
           ("Student Success & Advising", "Enrollment Management", "Communications & Marketing", "Human Resources"),
           2, 0.009),
)


def policy_id(policy: Policy, version: int) -> str:
    return sid(f"policy-{policy.name}-v{version}")


def version_published(now: datetime, version: int) -> datetime:
    return now - timedelta(days=40 - 9 * version)


def version_live_on(policy: Policy, day: date, now: datetime) -> int:
    return max((v for v in range(1, policy.versions + 1) if version_published(now, v).date() <= day), default=1)


def policy_rows(now: datetime) -> Iterator[dict[str, object]]:
    for p in POLICIES:
        for v in range(1, p.versions + 1):
            published = version_published(now, v)
            latest = v == p.versions
            yield {
                "policy_id": policy_id(p, v),
                "policy_name": p.name,
                "version_number": v,
                "version_status": "production" if latest else "published",
                "parent_version_id": policy_id(p, v - 1) if v > 1 else None,
                "is_latest": latest,
                "published_at": ts(published),
                "production_at": ts(published),
                "inherit": p.inherit,
                "description": p.description,
                "guardrails_add": list(p.guardrails if latest or len(p.guardrails) == 1 else p.guardrails[:-1]),
                "condition": {},
                "created_by": uid("sarah-nguyen"),
                "updated_by": uid("omar-haddad" if v % 2 else "sarah-nguyen"),
                "created_at": ts(published - timedelta(days=2)),
            }


def policy_attachment_rows() -> Iterator[dict[str, object]]:
    for priority, p in enumerate(POLICIES):
        yield {
            "attachment_id": sid(f"policy-attachment-{p.name}"),
            "policy_name": p.name,
            "teams": list(p.teams),
            "priority": priority,
            "created_by": uid("sarah-nguyen"),
        }


def policy_metric_rows(rng: random.Random, now: datetime) -> Iterator[dict[str, object]]:
    for p in POLICIES:
        for offset in range(DAYS):
            day = now.date() - timedelta(days=offset)
            evaluated = int(900 * len(p.teams) * (0.62 + 0.38 * (DAYS - offset) / DAYS) * rng.uniform(0.85, 1.15))
            blocked = int(evaluated * p.block_rate * rng.uniform(0.7, 1.3))
            flagged = int(evaluated * p.block_rate * 0.5)
            yield {
                "policy_id": policy_id(p, version_live_on(p, day, now)),
                "date": day.isoformat(),
                "requests_evaluated": evaluated,
                "passed_count": evaluated - blocked - flagged,
                "blocked_count": blocked,
                "flagged_count": flagged,
                "avg_score": round(rng.uniform(0.02, 0.1), 3),
                "avg_latency_ms": round(20 * len(p.guardrails) * rng.uniform(0.85, 1.2), 1),
                "updated_at": "now()",
            }


TEAM_TABLE: Final = "LiteLLM_TeamTable"
USER_TABLE: Final = "LiteLLM_UserTable"
KEY_TABLE: Final = "LiteLLM_VerificationToken"
MODEL_TABLE: Final = "LiteLLM_ProxyModelTable"


def audit_events() -> Iterator[tuple[float, str, str, str, str, object, object]]:
    admin: Final = uid("sarah-nguyen")
    for i, name in enumerate(MODELS):
        yield 29.5 - i * 0.1, uid("ethan-walsh"), "created", MODEL_TABLE, model_id(name), None, {"model_name": name}
    for i, k in enumerate(KEYS):
        yield 28 - i * 0.5, k.user_id, "created", KEY_TABLE, k.token, None, {
            "key_alias": k.alias, "team_id": k.team_id, "models": list(k.models), "max_budget": k.budget}
    for i, u in enumerate(USERS[-5:]):
        yield 21 - i * 1.5, admin, "created", USER_TABLE, u.user_id, None, {"user_email": u.email, "team_id": u.team_id}
    yield 18.2, uid("tom-becker"), "deleted", KEY_TABLE, hashlib.sha256(b"pilot-chatbot-test").hexdigest(), {
        "key_alias": "pilot-chatbot-test"}, None
    yield 15.4, admin, "updated", TEAM_TABLE, tid("enrollment"), {"policies": ["baseline-safety"]}, {
        "policies": ["baseline-safety", "restricted-data"]}
    yield 12.1, uid("grace-liu"), "updated", TEAM_TABLE, tid("finance"), {"max_budget": 2000.0}, {"max_budget": 2200.0}
    yield 10.3, uid("ethan-walsh"), "updated", KEY_TABLE, key_of("developer-code-assistant").token, {
        "key_name": "sk-...a41c"}, {"key_name": key_of("developer-code-assistant").key_name, "rotated": True}
    yield 9.2, uid("maria-alvarez"), "updated", KEY_TABLE, key_of("advising-assistant").token, {
        "models": ["claude-haiku-4-5"]}, {"models": ["claude-haiku-4-5", "gpt-5.4-mini"]}
    yield 8.0, uid("ethan-walsh"), "updated", TEAM_TABLE, tid("software-dev"), {"max_budget": 2500.0}, {
        "max_budget": 3000.0}
    yield 6.3, admin, "updated", TEAM_TABLE, tid("communications"), {"policies": ["baseline-safety"]}, {
        "policies": ["baseline-safety", "responsible-ai"]}
    yield 4.1, uid("maria-alvarez"), "updated", TEAM_TABLE, tid("student-success"), {"max_budget": 2000.0}, {
        "max_budget": 2500.0}
    yield 3.2, uid("omar-haddad"), "updated", KEY_TABLE, key_of("security-log-triage").token, {
        "key_name": "sk-...9e07"}, {"key_name": key_of("security-log-triage").key_name, "rotated": True}
    yield 1.4, uid("kevin-osei"), "updated", KEY_TABLE, key_of("it-helpdesk-bot").token, {"rpm_limit": 600}, {
        "rpm_limit": 1000}


def audit_rows(now: datetime) -> Iterator[dict[str, object]]:
    for n, (days_ago, actor, action, table, object_id, before, after) in enumerate(audit_events()):
        yield {
            "id": sid(f"audit-{n:03d}"),
            "updated_at": ts(now - timedelta(days=days_ago)),
            "changed_by": actor,
            "action": action,
            "table_name": table,
            "object_id": object_id,
            "before_value": Json(before) if before is not None else None,
            "updated_values": Json(after) if after is not None else None,
        }


HEALTH_CHECKS_PER_MODEL: Final = 28
OUTAGE_MODEL: Final = "gemini-3.8-flash"
OUTAGE_CHECKS: Final = frozenset({11, 12})


def health_rows(rng: random.Random, now: datetime) -> Iterator[dict[str, object]]:
    for m in MODELS.values():
        for i in range(HEALTH_CHECKS_PER_MODEL):
            down = m.name == OUTAGE_MODEL and i in OUTAGE_CHECKS
            checked = ts(now - timedelta(hours=6 * i + 1, minutes=rng.randint(0, 20)))
            yield {
                "health_check_id": sid(f"health-{m.name}-{i:03d}"),
                "model_name": m.name,
                "model_id": model_id(m.name),
                "status": "unhealthy" if down else "healthy",
                "healthy_count": 0 if down else 1,
                "unhealthy_count": 1 if down else 0,
                "error_message": "litellm.ServiceUnavailableError: 503 The model is overloaded. Please try again "
                                 "later." if down else None,
                "response_time_ms": round(m.latency_ms * 0.4 * rng.uniform(0.7, 1.4), 1),
                "checked_at": checked,
                "created_at": checked,
                "updated_at": checked,
            }


ERRORS: Final = (
    ("gemini-3.8-flash", "RateLimitError", "429", 4, "litellm.RateLimitError: Quota exceeded for requests per minute"),
    ("claude-opus-5-5", "Timeout", "408", 3, "litellm.Timeout: Request timed out after 600.0 seconds"),
    ("gpt-5.4-mini", "ContextWindowExceededError", "400", 2,
     "litellm.ContextWindowExceededError: This model's maximum context length was exceeded"),
    ("gemini-3.8-flash", "ServiceUnavailableError", "503", 2,
     "litellm.ServiceUnavailableError: 503 The model is overloaded. Please try again later."),
    ("claude-sonnet-5", "APIConnectionError", "500", 2, "litellm.APIConnectionError: Connection reset by peer"),
    ("gpt-5.6", "InternalServerError", "500", 1, "litellm.InternalServerError: The server had an error"),
)


def error_rows(rng: random.Random, now: datetime) -> Iterator[dict[str, object]]:
    events: Final = tuple(chain.from_iterable(repeat((name, kind, code, text), count)
                                              for name, kind, code, count, text in ERRORS))
    for n, (name, kind, code, text) in enumerate(events):
        m = MODELS[name]
        start = now - timedelta(seconds=rng.uniform(600, LOG_DAYS * 86400))
        yield {
            "request_id": sid(f"error-{n:03d}"),
            "startTime": ts(start),
            "endTime": ts(start + timedelta(milliseconds=m.latency_ms * rng.uniform(0.5, 3))),
            "api_base": m.api_base,
            "model_group": name,
            "litellm_model_name": f"{m.provider}/{name}",
            "model_id": model_id(name),
            "exception_type": kind,
            "exception_string": text,
            "status_code": code,
        }


SHADOW_EVALS: Final = (
    ("it-helpdesk-bot", "service-desk-router", {"SIMPLE": "gemini-3.8-flash", "MEDIUM": "gpt-5.4-mini",
                                                "COMPLEX": "claude-haiku-4-5"}, 20, (0.19, 0.18, 0.6, 0.03)),
    ("advising-assistant", "student-services-router", {"SIMPLE": "gemini-3.8-flash", "MEDIUM": "gpt-5.4-mini",
                                                       "COMPLEX": "claude-haiku-4-5"}, 12, (0.21, 0.19, 0.57, 0.03)),
)
SHADOW_ATTEMPTS: Final = 150


def request_cost(model: Model, key: Key) -> float:
    return key.prompt_tokens * model.input_price + key.completion_tokens * model.output_price


def shadow_rows(rng: random.Random, now: datetime) -> Iterator[tuple[str, dict[str, object]]]:
    for n, (alias, router, tiers, days_ago, weights) in enumerate(SHADOW_EVALS):
        key = key_of(alias)
        job = sid(f"shadow-job-{n}")
        created = now - timedelta(days=days_ago)
        yield "LiteLLM_ShadowEvalJob", {
            "id": job, "group_id": job, "target_type": "key", "target_id": key.token, "router_name": router,
            "router_names": [router], "models": [], "direction": "forward", "judge_model": "claude-opus-5-5",
            "shadow_percentage": 0.1, "max_turns": SHADOW_ATTEMPTS, "max_budget": 25.0,
            "created_at": ts(created), "created_by": key.user_id, "ends_at": ts(created + timedelta(days=7)),
        }
        real = MODELS[key.models[0]]
        for a in range(SHADOW_ATTEMPTS):
            tier = rng.choices(("SIMPLE", "MEDIUM", "COMPLEX"), weights=(0.5, 0.35, 0.15))[0]
            outcome = rng.choices(("real", "shadow", "tie", "error"), weights=weights)[0]
            shadow = MODELS[tiers[tier]]
            yield "LiteLLM_ShadowEvalAttempt", {
                "id": sid(f"shadow-attempt-{n}-{a:03d}"),
                "job_id": job,
                "request_id": str(uuid.UUID(int=rng.getrandbits(128))),
                "outcome": outcome,
                "router_name": router,
                "tier": tier,
                "real_model": real.name,
                "shadow_model": shadow.name,
                "confidence": round(rng.uniform(0.6, 0.97), 2),
                "judge_cost": round(request_cost(MODELS["claude-opus-5-5"], key) * 0.3, 6),
                "shadow_cost": 0.0 if outcome == "error" else round(request_cost(shadow, key), 6),
                "real_cost": round(request_cost(real, key), 6),
                "error": "judge returned malformed JSON" if outcome == "error" else None,
                "created_at": ts(created + timedelta(minutes=a * 60)),
            }
        yield "LiteLLM_ShadowEvalFunnel", {
            "job_id": job, "not_sampled": SHADOW_ATTEMPTS * 9, "unjudgeable": 6, "shed": 0, "withheld": 2}


def governance_ids() -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType({
        "access_group": tuple(sid(f"access-group-{name}") for name, *_ in ACCESS_GROUPS),
        "policy": tuple(chain.from_iterable((policy_id(p, v) for v in range(1, p.versions + 1)) for p in POLICIES)),
        "attachment": tuple(sid(f"policy-attachment-{p.name}") for p in POLICIES),
        "audit": tuple(sid(f"audit-{n:03d}") for n in range(len(tuple(audit_events())))),
        "health": tuple(sid(f"health-{m}-{i:03d}") for m, i in product(MODELS, range(HEALTH_CHECKS_PER_MODEL))),
        "error": tuple(sid(f"error-{n:03d}") for n in range(sum(e[3] for e in ERRORS))),
        "shadow_job": tuple(sid(f"shadow-job-{n}") for n in range(len(SHADOW_EVALS))),
    })


def governance_cleanup_sql() -> Iterator[str]:
    ids: Final = governance_ids()

    def within(values: tuple[str, ...]) -> str:
        return ", ".join(q(v) for v in values)

    yield f'DELETE FROM "LiteLLM_AccessGroupTable" WHERE access_group_id IN ({within(ids["access_group"])});'
    yield f'DELETE FROM "LiteLLM_DailyPolicyMetrics" WHERE policy_id IN ({within(ids["policy"])});'
    yield f'DELETE FROM "LiteLLM_PolicyAttachmentTable" WHERE attachment_id IN ({within(ids["attachment"])});'
    yield f'DELETE FROM "LiteLLM_PolicyTable" WHERE policy_id IN ({within(ids["policy"])});'
    yield f'DELETE FROM "LiteLLM_AuditLog" WHERE id IN ({within(ids["audit"])});'
    yield f'DELETE FROM "LiteLLM_HealthCheckTable" WHERE health_check_id IN ({within(ids["health"])});'
    yield f'DELETE FROM "LiteLLM_ErrorLogs" WHERE request_id IN ({within(ids["error"])});'
    yield f'DELETE FROM "LiteLLM_ShadowEvalAttempt" WHERE job_id IN ({within(ids["shadow_job"])});'
    yield f'DELETE FROM "LiteLLM_ShadowEvalFunnel" WHERE job_id IN ({within(ids["shadow_job"])});'
    yield f'DELETE FROM "LiteLLM_ShadowEvalJob" WHERE id IN ({within(ids["shadow_job"])});'


def governance_seed_sql(rng: random.Random, now: datetime) -> Iterator[str]:
    yield from (raw_now(s) for s in insert("LiteLLM_AccessGroupTable", (
        {"access_group_id": sid(f"access-group-{name}"), "access_group_name": name, "description": description,
         "access_model_names": list(models), "assigned_team_ids": list(teams), "created_by": uid("sarah-nguyen"),
         "updated_at": "now()"}
        for name, description, models, teams in ACCESS_GROUPS), ' ON CONFLICT ("access_group_name") DO NOTHING'))
    yield from (raw_now(s) for s in insert("LiteLLM_PolicyTable", policy_rows(now), " ON CONFLICT DO NOTHING"))
    yield from (raw_now(s) for s in insert("LiteLLM_PolicyAttachmentTable", policy_attachment_rows()))
    yield from (raw_now(s) for s in insert("LiteLLM_DailyPolicyMetrics", policy_metric_rows(rng, now)))
    yield from insert("LiteLLM_AuditLog", audit_rows(now))
    yield from insert("LiteLLM_HealthCheckTable", health_rows(rng, now))
    yield from insert("LiteLLM_ErrorLogs", error_rows(rng, now))
    yield from chain.from_iterable(insert(table, (row,)) for table, row in shadow_rows(rng, now))


def other_guardrail_metrics_sql(today: date) -> Iterator[str]:
    """Give guardrails the seeder doesn't own 30 days of metrics, recorded in raw_seed so cleanup can undo them."""
    ours: Final = ", ".join(q(g["guardrail_name"]) for g in GUARDRAIL_CONFIGS)
    start: Final = (today - timedelta(days=DAYS - 1)).isoformat()
    yield (
        "WITH days AS (SELECT d::date AS day, row_number() OVER (ORDER BY d) AS n "
        f"FROM generate_series({q(start)}::date, {q(today.isoformat())}::date, interval '1 day') d), "
        f'targets AS (SELECT guardrail_name AS gid FROM "LiteLLM_GuardrailsTable" WHERE guardrail_name NOT IN ({ours})), '
        "sized AS (SELECT t.gid, to_char(d.day, 'YYYY-MM-DD') AS date, "
        "((1500 + 30 * d.n + ('x' || substr(md5(t.gid || d.day), 1, 4))::bit(16)::int % 700) "
        "* CASE WHEN extract(isodow FROM d.day) >= 6 THEN 0.55 ELSE 1 END)::bigint AS evaluated, "
        "0.003 + ('x' || substr(md5(d.day || t.gid), 1, 4))::bit(16)::int % 1500 / 100000.0 AS rate, "
        "15 + ('x' || substr(md5(t.gid), 1, 4))::bit(16)::int % 50 AS latency "
        "FROM targets t CROSS JOIN days d), "
        "counted AS (SELECT *, (evaluated * rate)::bigint AS blocked, (evaluated * rate * 0.5)::bigint AS flagged "
        "FROM sized), "
        'ins AS (INSERT INTO "LiteLLM_DailyGuardrailMetrics" (guardrail_id, date, requests_evaluated, passed_count, '
        "blocked_count, flagged_count, avg_score, avg_latency_ms, updated_at) "
        "SELECT gid, date, evaluated, evaluated - blocked - flagged, blocked, flagged, round(rate::numeric * 4, 3), "
        "latency, (NOW() AT TIME ZONE 'UTC') FROM counted "
        "ON CONFLICT (guardrail_id, date) DO NOTHING RETURNING guardrail_id, date) "
        "INSERT INTO raw_seed.guardrail_metrics SELECT guardrail_id, date FROM ins;"
    )


def cleanup_sql() -> Iterator[str]:
    tokens: Final = ", ".join(q(k.token) for k in KEYS)
    ids: Final = ", ".join(q(i) for i in all_ids())
    yield "CREATE TEMP TABLE demo_days ON COMMIT DROP AS SELECT DISTINCT \"date\" FROM \"LiteLLM_DailyUserSpend\" " \
          f"WHERE api_key IN ({tokens});"
    for table, _ in DAILY_TABLES:
        yield f'DELETE FROM "{table}" WHERE api_key IN ({tokens});'
    yield ('DELETE FROM "LiteLLM_SpendLogGuardrailIndex" WHERE request_id IN '
           f'(SELECT request_id FROM "LiteLLM_SpendLogs" WHERE api_key IN ({tokens}));')
    yield f'DELETE FROM "LiteLLM_SpendLogs" WHERE api_key IN ({tokens}) OR request_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_DailyGuardrailMetrics" WHERE guardrail_id IN ({", ".join(q(g[0]) for g in GUARDRAILS)});'
    yield f'DELETE FROM "LiteLLM_DailyGatewayRequests" WHERE route LIKE {q("%#demo")};'
    yield "CREATE SCHEMA IF NOT EXISTS raw_seed;"
    yield ("CREATE TABLE IF NOT EXISTS raw_seed.gateway_requests (date text, category text, route text, "
           "successful_requests bigint, failed_requests bigint);")
    yield ('UPDATE "LiteLLM_DailyGatewayRequests" g SET '
           "successful_requests = g.successful_requests - m.successful_requests, "
           "failed_requests = g.failed_requests - m.failed_requests "
           "FROM raw_seed.gateway_requests m WHERE g.date = m.date AND g.category = m.category AND g.route = m.route;")
    yield ('DELETE FROM "LiteLLM_DailyGatewayRequests" g USING raw_seed.gateway_requests m '
           "WHERE g.date = m.date AND g.category = m.category AND g.route = m.route "
           "AND g.successful_requests <= 0 AND g.failed_requests <= 0;")
    yield "TRUNCATE raw_seed.gateway_requests;"
    yield "CREATE TABLE IF NOT EXISTS raw_seed.guardrail_metrics (guardrail_id text, date text);"
    yield ('DELETE FROM "LiteLLM_DailyGuardrailMetrics" g USING raw_seed.guardrail_metrics m '
           "WHERE g.guardrail_id = m.guardrail_id AND g.date = m.date;")
    yield "TRUNCATE raw_seed.guardrail_metrics;"
    yield f'DELETE FROM "LiteLLM_VerificationToken" WHERE token IN ({tokens});'
    yield f'DELETE FROM "LiteLLM_GuardrailsTable" WHERE guardrail_id IN ({ids});'
    yield f'DELETE FROM "LiteLLM_TeamMembership" WHERE user_id IN ({ids}) OR user_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_UserTable" WHERE user_id IN ({ids}) OR user_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_TeamTable" WHERE team_id IN ({ids}) OR team_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_OrganizationTable" WHERE organization_id IN ({ids}) OR organization_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_EndUserTable" WHERE user_id IN ({ids}) OR user_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield f'DELETE FROM "LiteLLM_TagTable" WHERE created_by IN ({q(SEED_ACTOR)}, {q(LEGACY_PREFIX + "seed")});'
    yield f'DELETE FROM "LiteLLM_BudgetTable" WHERE budget_id IN ({ids}) OR budget_id LIKE {q(LEGACY_PREFIX + "%")};'
    yield from governance_cleanup_sql()
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
        {"budget_id": sid(f"budget-{o.org_id}"), "max_budget": o.budget, "budget_duration": "30d",
         "created_by": SEED_ACTOR, "updated_by": SEED_ACTOR} for o in ORGS))
    yield from insert("LiteLLM_OrganizationTable", (
        {"organization_id": o.org_id, "organization_alias": o.alias, "budget_id": sid(f"budget-{o.org_id}"),
         "models": [], "spend": org_spend[o.org_id],
         "created_by": SEED_ACTOR, "updated_by": SEED_ACTOR, "created_at": created} for o in ORGS))
    yield from insert("LiteLLM_TeamTable", (
        {"team_id": t.team_id, "team_alias": t.alias, "organization_id": t.org_id,
         "admins": [u.user_id for u in USERS if u.team_id == t.team_id][:1],
         "members": [u.user_id for u in USERS if u.team_id == t.team_id],
         "members_with_roles": Json([{"role": "admin" if i == 0 else "user", "user_id": u.user_id, "user_email": u.email}
                                for i, u in enumerate(u for u in USERS if u.team_id == t.team_id)]),
         "max_budget": t.budget, "spend": team_spend[t.team_id],
         "models": sorted({m for k in KEYS if k.team_id == t.team_id for m in k.models}),  # comprehension-ok: flatten key models
         "access_group_ids": access_groups_of(t.team_id),
         "budget_duration": "30d", "tpm_limit": 2000000, "rpm_limit": 5000, "created_at": created} for t in TEAMS))
    yield from insert("LiteLLM_UserTable", (
        {"user_id": u.user_id, "user_alias": u.alias, "user_email": u.email, "user_role": u.role, "team_id": u.team_id,
         "teams": [u.team_id], "organization_id": team_of(u.team_id).org_id, "models": [], "spend": user_spend[u.user_id],
         "max_budget": 1000.0, "created_at": created} for u in USERS))
    yield from insert("LiteLLM_TeamMembership", (
        {"user_id": u.user_id, "team_id": u.team_id, "spend": user_spend[u.user_id], "total_spend": user_spend[u.user_id]}
        for u in USERS))
    yield from insert("LiteLLM_VerificationToken", (
        {"token": k.token, "key_name": k.key_name, "key_alias": k.alias, "spend": key_spend[k.alias],
         "total_spend": key_spend[k.alias], "models": list(k.models), "user_id": k.user_id, "team_id": k.team_id,
         "organization_id": team_of(k.team_id).org_id, "max_budget": k.budget, "budget_duration": "30d",
         "tpm_limit": 500000, "rpm_limit": 1000, "metadata": {"tags": [k.tag]},
         "created_at": created, "created_by": "default_user_id", "last_active": now.replace(tzinfo=None).isoformat(sep=" "),
         "blocked": False} for k in KEYS))
    yield from insert("LiteLLM_EndUserTable", (
        {"user_id": e, "alias": f"Customer {e[-3:]}", "spend": end_user_spend[e]} for e in END_USERS),
        ' ON CONFLICT ("user_id") DO NOTHING')
    yield from insert("LiteLLM_TagTable", (
        {"tag_name": t, "description": f"{t.replace('-', ' ').title()} traffic", "models": [], "spend": tag_spend.get(t, 0.0),
         "created_by": SEED_ACTOR} for t in TAGS), ' ON CONFLICT ("tag_name") DO NOTHING')

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

    yield from (raw_now(s) for s in insert(
        "LiteLLM_GuardrailsTable",
        (
            {
                "guardrail_id": sid(f"guardrail-{g['guardrail_name']}"),
                "guardrail_name": g["guardrail_name"],
                "litellm_params": g["litellm_params"],
                "guardrail_info": g["guardrail_info"],
                "status": "active",
                "created_at": ts(now - timedelta(days=182 - 4 * i, hours=3 * i + 2)),
                "updated_at": ts(now - timedelta(days=158 - 3 * i, hours=5 * i + 1)),
            }
            for i, g in enumerate(GUARDRAIL_CONFIGS)
        ),
        ' ON CONFLICT ("guardrail_name") DO NOTHING',
    ))
    gateway: Final = tuple(gateway_rows(cells))
    yield from insert("raw_seed.gateway_requests", gateway)
    yield from (raw_now(s) for s in insert(
        "LiteLLM_DailyGatewayRequests",
        (row | {"updated_at": "now()"} for row in gateway),
        ' ON CONFLICT ("date", "category", "route") DO UPDATE SET '
        '"successful_requests" = "LiteLLM_DailyGatewayRequests"."successful_requests" + EXCLUDED."successful_requests", '
        '"failed_requests" = "LiteLLM_DailyGatewayRequests"."failed_requests" + EXCLUDED."failed_requests", '
        "\"updated_at\" = (NOW() AT TIME ZONE 'UTC')",
    ))
    logs: Final = tuple(spend_logs(rng, now))
    yield from (upsert("LiteLLM_SpendLogs", row, "request_id") for row in logs)
    yield from insert("LiteLLM_SpendLogGuardrailIndex", guardrail_index_rows(logs), " ON CONFLICT DO NOTHING")
    yield from other_guardrail_metrics_sql(now.date())
    yield from governance_seed_sql(rng, now)
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
    if args.cleanup:
        out.write("DROP SCHEMA raw_seed CASCADE;\n")
    else:
        for statement in seed_sql(random.Random(args.seed), datetime.now(UTC)):
            out.write(statement + "\n")
    out.write("COMMIT;\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
