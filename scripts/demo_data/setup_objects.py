"""Create the models, auto routers and saved prompts that match seed_demo_data.py, through the proxy API.

Run on the proxy host from the repo root (it reads LITELLM_MASTER_KEY from ./.env):
    python3 scripts/demo_data/setup_objects.py            # create
    python3 scripts/demo_data/setup_objects.py --remove   # delete

Objects go through the same endpoints the Admin UI uses, so credentials are encrypted with the
proxy's salt key. Model ids match the model_id values seed_demo_data.py writes into the logs.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Final

NAMESPACE: Final = uuid.UUID("7b1c2f0e-5a4d-4e8b-9c3f-2d6a8e1b4c90")

MODELS: Final = (
    ("gpt-5.6", "openai/gpt-5.6", "OPENAI_API_KEY"),
    ("gpt-5.4-mini", "openai/gpt-5.4-mini", "OPENAI_API_KEY"),
    ("claude-sonnet-5", "anthropic/claude-sonnet-5", "ANTHROPIC_API_KEY"),
    ("claude-haiku-4-5", "anthropic/claude-haiku-4-5", "ANTHROPIC_API_KEY"),
    ("claude-opus-5-5", "anthropic/claude-opus-5-5", "ANTHROPIC_API_KEY"),
    ("gemini-3.8-flash", "gemini/gemini-3.8-flash", "GEMINI_API_KEY"),
    ("text-embedding-3-small", "openai/text-embedding-3-small", "OPENAI_API_KEY"),
)

AUTO_ROUTERS: Final = (
    ("smart-router", {"SIMPLE": "gemini-3.8-flash", "MEDIUM": "gpt-5.4-mini", "COMPLEX": "claude-sonnet-5",
                      "REASONING": "claude-opus-5-5"}, "gpt-5.4-mini"),
    ("service-desk-router", {"SIMPLE": "gemini-3.8-flash", "MEDIUM": "gpt-5.4-mini", "COMPLEX": "claude-haiku-4-5"},
     "claude-haiku-4-5"),
    ("student-services-router", {"SIMPLE": "gemini-3.8-flash", "MEDIUM": "gpt-5.4-mini",
                                 "COMPLEX": "claude-haiku-4-5"}, "claude-haiku-4-5"),
)

PROMPTS: Final = (
    ("it_ticket_summary", "claude-haiku-4-5", 0.2, ("ticket_text",),
     "You are an IT service desk analyst. Summarize the ticket in two sentences, classify it (access, hardware, "
     "network, software, account) and suggest the first troubleshooting step.",
     "Ticket:\n{{ticket_text}}"),
    ("advising_note", "claude-haiku-4-5", 0.3, ("meeting_notes",),
     "You help academic advisors write appointment notes. Be factual and neutral, list agreed next steps with "
     "owners and dates, and leave out anything not discussed.",
     "Turn these meeting notes into an advising note:\n{{meeting_notes}}"),
    ("budget_variance_explainer", "gpt-5.6", 0.2, ("department", "actuals", "budget"),
     "You are a finance analyst. Forecast year-end spend from actuals to date, explain the variance to budget in "
     "plain language and give an 80% range.",
     "Department: {{department}}\nBudget: {{budget}}\nActuals to date: {{actuals}}"),
    ("research_abstract_summary", "claude-sonnet-5", 0.2, ("abstract", "audience"),
     "Summarize research for the given audience in under 150 words. Keep claims faithful to the source and note "
     "the study design and sample size.",
     "Audience: {{audience}}\nAbstract:\n{{abstract}}"),
    ("policy_qa", "gpt-5.4-mini", 0.1, ("question", "policy_text"),
     "Answer only from the provided policy text and cite the section. If the answer is not there, say so and "
     "suggest who to contact.",
     "Policy:\n{{policy_text}}\n\nQuestion: {{question}}"),
    ("model_output_review", "claude-opus-5-5", 0.0, ("outputs", "criteria"),
     "You review AI outputs for accuracy, tone and consistency across user groups. Score each criterion 0-100, "
     "flag any group gap above 5 points, and return JSON with scores, gaps and notes.",
     "Criteria: {{criteria}}\nOutputs:\n{{outputs}}"),
)


def model_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"model-{name}"))


def dotprompt(model: str, temperature: float, variables: tuple[str, ...], system: str, user: str) -> str:
    schema: Final = "".join(f"    {v}: string\n" for v in variables)
    return (
        f"---\nmodel: {model}\ntemperature: {temperature}\ninput:\n  schema:\n{schema}"
        f"output:\n  format: text\n---\n\nSystem: {system}\n\nUser: {user}\n"
    )


def master_key() -> str:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("LITELLM_MASTER_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("LITELLM_MASTER_KEY not found in ./.env; run this from the repo root on the proxy host")


def call(base: str, key: str, method: str, path: str, body: object) -> None:
    request: Final = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"ok    {method} {path} {body.get('model_name') or body.get('prompt_id') or body.get('id')}")
    except urllib.error.HTTPError as err:
        print(f"skip  {method} {path}: {err.code} {err.read().decode()[:160]}")


def create(base: str, key: str) -> None:
    for name, model, env in MODELS:
        call(base, key, "POST", "/model/new", {
            "model_name": name,
            "litellm_params": {"model": model, "api_key": f"os.environ/{env}"},
            "model_info": {"id": model_id(name)},
        })
    for name, tiers, default in AUTO_ROUTERS:
        call(base, key, "POST", "/model/new", {
            "model_name": name,
            "litellm_params": {
                "model": "auto_router/complexity_router",
                "complexity_router_config": {"tiers": tiers},
                "complexity_router_default_model": default,
            },
            "model_info": {"id": model_id(name)},
        })
    for prompt_id, model, temperature, variables, system, user in PROMPTS:
        call(base, key, "POST", "/prompts", {
            "prompt_id": prompt_id,
            "litellm_params": {
                "prompt_integration": "dotprompt",
                "prompt_id": prompt_id,
                "dotprompt_content": dotprompt(model, temperature, variables, system, user),
            },
            "prompt_info": {"prompt_type": "db", "environment": "production"},
        })


def remove(base: str, key: str) -> None:
    for name, *_ in AUTO_ROUTERS + MODELS:
        call(base, key, "POST", "/model/delete", {"id": model_id(name)})
    for prompt_id, *_ in PROMPTS:
        call(base, key, "DELETE", f"/prompts/{prompt_id}", {"id": prompt_id})


def main() -> int:
    parser: Final = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="delete the objects instead of creating them")
    parser.add_argument("--base-url", default="http://localhost:4000")
    args: Final = parser.parse_args()
    key: Final = master_key()
    (remove if args.remove else create)(args.base_url.rstrip("/"), key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
