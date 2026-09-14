---
name: weekly-ads-monitor
description: Maintain and extend the read-only weekly advertising monitoring system that publishes project-specific Yandex Direct, Metrika, Roistat, and plan data to unified Google Sheets tabs.
---

# Weekly Ads Monitor

Work inside this repository to maintain the agency's weekly advertising
monitoring spreadsheet.

Before changing a project, read its file in `config/` and inspect the relevant
publisher in `src/weekly_ads_monitor/`. Treat every project's source mapping,
conversion definition, attribution, status classification, and plan mapping as
project-specific. Do not invent missing settings.

Preserve these invariants:

- external advertising and analytics systems are read-only;
- secrets live only in `.env.local` and `.secrets/`, never in tracked files;
- calculations, aggregation, thresholds, attribution filters, and diagnostics
  run in deterministic code;
- send only a compact set of calculated facts to an LLM, at most once per
  project and week, and skip the call when no useful comment is needed;
- retain historical weekly rows and split display periods at calendar-month
  boundaries while comparing complete Monday–Sunday weeks;
- use actual calendar days for monthly plan pacing;
- do not add Search/RSA blocks to project tabs;
- display unavailable data as unavailable instead of manufacturing zeros;
- preserve the established Google Sheets formatting and project-specific KPI
  direction rules.

When adding a project, first establish its data sources, account/counter/project
IDs, conversion definition, attribution model, timezone, plan source, KPI
directions, and required credentials. Add only the integrations that project
actually uses.

Before publishing, run the unit tests and validate the target sheet after the
write. Confirm key control periods, current plan/fact values, absence of secret
material, and absence of Search/RSA sections.

Use `TASK_PROMPT.md` when a full statement of the product requirements is
needed.
