You are building Picxify from scratch. Read SETUP.md completely, then implement the MVP in the milestone order.

Hard requirements:
1. Keep the product promise focused: messy data -> polished, trustworthy, shareable dashboard.
2. Do not let the LLM calculate final metrics. Code calculates facts; LLM plans/narrates using facts.
3. The dashboard renderer must render only validated DashboardSpec JSON.
4. Every chart, KPI, and insight must include a sourceTrace.
5. Build template-first. Do not let the LLM invent arbitrary UI layouts.
6. Default dashboards are private. Public sharing must use unguessable slugs and explicit publish state.

Start with Milestone 1:
- Create the monorepo structure.
- Add docker-compose.yml.
- Scaffold apps/web with Next.js App Router, TypeScript, Tailwind.
- Scaffold apps/api with FastAPI, Pydantic, SQLAlchemy, Alembic.
- Add Celery worker skeleton connected to Redis.
- Add the DashboardSpec schema from schemas/dashboard_spec.schema.json.
- Add health check endpoints and a smoke test.

After each milestone, run tests, update a changelog, and create a short implementation note explaining tradeoffs.
