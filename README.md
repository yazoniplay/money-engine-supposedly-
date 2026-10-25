# SignalForge — AI Automation Lead Engine

Discover public B2B requests for AI automation, qualify them with Gemini, deduplicate results, and send source-linked opportunities to a private Discord channel.

## Setup
1. In Discord, open **Server Settings → Integrations → Webhooks → New Webhook** (or channel settings → Integrations), choose the destination channel, and copy the webhook URL.
2. Add these GitHub Actions secrets in **Settings → Secrets and variables → Actions**: `GEMINI_API_KEY` and `DISCORD_WEBHOOK_URL`. Optional Reddit OAuth secrets: `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.
3. Enable Actions, then run **SignalForge Lead Scan** manually.
4. Scheduled scans run every 30 minutes (GitHub may delay scheduled jobs).

Optional repository variables: `MIN_LEAD_SCORE` (default 8), `MAX_POST_AGE_HOURS` (default 72), `SUBREDDITS`, `SEARCH_TERMS`, `REDDIT_USER_AGENT`.

## Local run
Python 3.11+: `pip install -r requirements.txt`, configure environment variables from `.env.example`, then run `python money_engine.py`.

## Important
Only use permitted public data. Respect platform terms, rate limits, privacy and marketing laws. Don't bypass access controls or spam requesters. AI scores are triage estimates, not proof of buying intent or guaranteed budgets. Do not claim exclusivity unless it is real. Keep the Discord webhook private and never commit API keys.