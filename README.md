# Weekly Ads Monitor

Read-only MVP for weekly advertising monitoring in one Google Spreadsheet.

Implemented projects:

- `reduktor40.ru`: Yandex Direct + Roistat + Google Sheets plan;
- `asko-hall.ru`: Yandex Direct + Yandex Metrika + Roistat calls + Google Sheets plan;
- `loglab.ru`: Yandex Direct + Yandex Metrika + Google Sheets plan.

The system loads advertising and conversion data, calculates weekly and monthly
metrics in ordinary Python code, and publishes unified project tabs to Google
Sheets. It never changes data in Yandex Direct, Metrika, or Roistat.

## Secrets

Create `.env.local` in the repository root. This file is ignored by Git:

```text
YANDEX_DIRECT_OAUTH_TOKEN=...
YANDEX_METRIKA_OAUTH_TOKEN=...
ROISTAT_API_KEY=...
```

Put Google service-account credentials in
`.secrets/google-service-account.json`. The entire `.secrets` directory is
ignored by Git. Share the target spreadsheet with the service-account email.

## Run

Use Python 3.11 or newer:

```powershell
python -m pip install -e .
$env:PYTHONPATH = "src"

python -m weekly_ads_monitor.publish_google_sheet `
  --spreadsheet-id "SPREADSHEET_ID" `
  --tab "reduktor40.ru"

python -m weekly_ads_monitor.publish_asko_hall
python -m weekly_ads_monitor.publish_loglab
```

Project-specific settings are stored in `config/*.json`. Never put tokens or
service-account credentials in those files.

## Reporting conventions

- completed week: Monday through Sunday;
- reporting timezone: Moscow (`UTC+3`);
- costs include VAT;
- monthly pacing uses elapsed calendar days and the actual number of days in the month;
- weeks crossing a month boundary are split visually between calendar months;
- full weeks are used for weekly comparison and commentary;
- plan `sessions` are treated as Yandex Direct clicks where configured;
- calculated metrics and diagnostics are produced in code;
- LLM use is reserved for a short human-readable comment and is skipped when unnecessary;
- Search/RSA sections are not shown on project tabs.

See [TASK_PROMPT.md](TASK_PROMPT.md) for the transferable task prompt and
[SKILL.md](SKILL.md) for the Codex skill instructions.
