# SignalForge — AI Automation Lead Engine

Discover public B2B requests for AI automation, qualify with Gemini, deduplicate, and send source-linked opportunities to Telegram.

## Setup
1. Add GitHub Actions secrets: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. Optional Reddit OAuth secrets: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.
2. Enable Actions, then run SignalForge Lead Scan manually.
3. Scheduled scans run every 30 minutes (GitHub may delay scheduled jobs).

Optional repository variables: MIN_LEAD_SCORE (default 8), MAX_POST_AGE_HOURS (default 72), SUBREDDITS, SEARCH_TERMS, REDDIT_USER_AGENT.

## Local run
Python 3.11+: pip install -r requirements.txt, configure environment variables from .env.example, then run python money_engine.py.

## Important
Only use permitted public data. Respect platform terms, rate limits, privacy and marketing laws. Don't bypass access controls or spam requesters. AI scores are triage estimates, not proof of buying intent or guaranteed budgets. Do not claim exclusivity unless it is real. Never commit API keys.