#!/usr/bin/env bash
# Usage, from the repo root on the proxy host:  bash scripts/demo_data/fill_db.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

python3 scripts/demo_data/seed_demo_data.py > /tmp/seed.sql
docker exec -i litellm_db psql -q -v ON_ERROR_STOP=1 -U llmproxy -d litellm < /tmp/seed.sql
rm -f /tmp/seed.sql

python3 scripts/demo_data/setup_objects.py

docker exec -i litellm_db psql -q -v ON_ERROR_STOP=1 -U llmproxy -d litellm <<'SQL'
WITH ranked AS (
  SELECT model_id,
         date_trunc('minute', NOW() AT TIME ZONE 'UTC' - interval '46 days')
           + (row_number() OVER (ORDER BY model_name)) * interval '7 minutes' AS created,
         date_trunc('minute', NOW() AT TIME ZONE 'UTC' - interval '38 days')
           + (row_number() OVER (ORDER BY model_name)) * interval '23 minutes' AS updated
  FROM "LiteLLM_ProxyModelTable"
  WHERE created_by = 'Demo Setup' OR model_info->>'created_by' = 'Demo Setup'
)
UPDATE "LiteLLM_ProxyModelTable" m
SET created_by = 'harsh.malhotra@rabbitt.ai',
    updated_by = 'harsh.malhotra@rabbitt.ai',
    created_at = r.created,
    updated_at = r.updated,
    model_info = COALESCE(m.model_info, '{}'::jsonb) || jsonb_build_object(
      'created_by', 'harsh.malhotra@rabbitt.ai',
      'updated_by', 'harsh.malhotra@rabbitt.ai',
      'created_at', to_char(r.created, 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
      'updated_at', to_char(r.updated, 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'))
FROM ranked r
WHERE m.model_id = r.model_id;
SQL

# TODO: drop once the running image is rebuilt from d31374a or later, which ships this fix
docker compose exec -T -u root litellm python3 - <<'PY'
import pathlib, litellm.proxy.guardrails.usage_endpoints as m
p = pathlib.Path(m.__file__)
s = p.read_text()
old = '_field_str(litellm_params, "guardrail", "Unknown")'
new = '(lambda g: "LiteLLM" if g == "litellm_content_filter" else g)(_field_str(litellm_params, "guardrail", "Unknown"))'
if "_guardrail_provider" not in s and new not in s and s.count(old) == 2:
    p.write_text(s.replace(old, new))
PY

docker compose restart litellm
echo "done, refresh the Admin UI in ~20 seconds"
