import os
import sys
import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SignalForge")

STATE_FILE = os.path.join("data", "state.json")

DEFAULT_SUBREDDITS = [
    "forhire",
    "freelance_forhire",
    "startups",
    "entrepreneur",
    "smallbusiness",
    "SaaS",
    "ArtificialInteligence",
    "LocalLLaMA",
    "automation",
    "nocode"
]

DEFAULT_SEARCH_TERMS = [
    "AI automation",
    "build AI agent",
    "chatbot developer",
    "automate workflow",
    "LLM integration",
    "Zapier alternative",
    "custom GPT",
    "AI scraping",
    "lead generation bot",
    "AI developer needed",
    "AI automation agency",
    "LLM consultant",
    "automate my business"
]

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load state file: {e}")
    return {"seen_ids": []}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    try:
        if "seen_ids" in state and len(state["seen_ids"]) > 2000:
            state["seen_ids"] = state["seen_ids"][-2000:]
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Could not save state file: {e}")

def fetch_reddit_posts(subreddits, search_terms, max_age_hours):
    posts = []
    seen_urls = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    
    user_agent = os.getenv("REDDIT_USER_AGENT", "SignalForgeBot/2.0")
    headers = {"User-Agent": user_agent}
    
    for sub in subreddits:
        for term in search_terms:
            query = urllib.parse.quote(term)
            url = f"https://www.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=1&sort=new&limit=25"
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    children = data.get("data", {}).get("children", [])
                    for child in children:
                        pdata = child.get("data", {})
                        pid = pdata.get("id")
                        title = pdata.get("title", "")
                        selftext = pdata.get("selftext", "")
                        created_utc = pdata.get("created_utc", 0)
                        permalink = pdata.get("permalink", "")
                        url_link = pdata.get("url", "")
                        
                        post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                        if post_time < cutoff:
                            continue
                            
                        full_url = f"https://reddit.com{permalink}" if permalink else url_link
                        if full_url in seen_urls:
                            continue
                        seen_urls.add(full_url)
                        
                        posts.append({
                            "id": f"reddit_{pid}",
                            "title": title,
                            "content": selftext[:1500],
                            "url": full_url,
                            "source": f"r/{sub}"
                        })
            except Exception as e:
                logger.debug(f"Error fetching r/{sub} for '{term}': {e}")
            time.sleep(0.3)
            
    return posts

def analyze_with_gemini(posts, api_key, model):
    if not posts:
        return []
        
    scored_posts = []
    min_score = int(os.getenv("MIN_LEAD_SCORE", "7"))
    
    if not api_key:
        logger.warning("No GEMINI_API_KEY provided. Using high-speed keyword heuristic scoring.")
        for p in posts:
            text = (p["title"] + " " + p["content"]).lower()
            score = 8 if any(k in text for k in ["ai", "automation", "bot", "agent", "llm"]) else 5
            if score >= min_score:
                p["score"] = score
                p["rationale"] = "Matched heuristic automation criteria."
                scored_posts.append(p)
        return scored_posts

    def evaluate_single_post(p):
        prompt = (
            "You are an expert B2B sales lead qualification AI. "
            "Analyze the following post and determine if the author is actively looking to hire or buy AI automation, "
            "AI agents, custom LLM solutions, or workflow automation services.\n"
            f"Title: {p['title']}\n"
            f"Content: {p['content']}\n\n"
            "Return ONLY a valid JSON object with keys: 'score' (integer 1-10) and 'rationale' (string explanation)."
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = json.dumps(payload).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    text_resp = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
                    text_resp = text_resp.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(text_resp)
                    score = int(parsed.get("score", 0))
                    rationale = parsed.get("rationale", "")
                    if score >= min_score:
                        p["score"] = score
                        p["rationale"] = rationale
                        return p
        except Exception as e:
            logger.debug(f"Gemini scoring error for post {p['id']}: {e}")
        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(evaluate_single_post, p): p for p in posts}
        for future in as_completed(futures):
            res = future.result()
            if res:
                scored_posts.append(res)
                
    return scored_posts

def send_discord_notification(lead, webhook_url):
    if not webhook_url:
        logger.info(f"[DRY RUN DISCORD] Lead found: {lead['title']} ({lead['url']}) - Score: {lead['score']}/10")
        return
        
    payload = {
        "embeds": [{
            "title": f"🚀 High-Intent AI Lead ({lead['score']}/10): {lead['title'][:200]}",
            "url": lead["url"],
            "description": lead.get("rationale", "No rationale provided."),
            "color": 5814783,
            "fields": [
                {"name": "Source", "value": lead["source"], "inline": True}
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info(f"Sent lead to Discord: {lead['title'][:50]}")
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")

def main():
    logger.info("Starting SignalForge high-speed lead scan...")
    
    sub_env = os.getenv("SUBREDDITS")
    if sub_env:
        subreddits = [s.strip() for s in sub_env.split(",") if s.strip()]
    else:
        subreddits = DEFAULT_SUBREDDITS
        
    term_env = os.getenv("SEARCH_TERMS")
    if term_env:
        search_terms = [t.strip() for t in term_env.split(",") if t.strip()]
    else:
        search_terms = DEFAULT_SEARCH_TERMS
        
    max_age_hours = int(os.getenv("MAX_POST_AGE_HOURS", "72"))
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))
    
    posts = fetch_reddit_posts(subreddits, search_terms, max_age_hours)
    logger.info(f"Fetched {len(posts)} total raw posts across {len(subreddits)} subreddits.")
    
    new_posts = [p for p in posts if p["id"] not in seen_ids]
    logger.info(f"{len(new_posts)} posts remain after deduplication.")
    
    scored_leads = analyze_with_gemini(new_posts, gemini_api_key, gemini_model)
    logger.info(f"Found {len(scored_leads)} qualified leads meeting threshold.")
    
    for lead in scored_leads:
        send_discord_notification(lead, discord_webhook)
        seen_ids.add(lead["id"])
        
    state["seen_ids"] = list(seen_ids)
    save_state(state)
    logger.info("SignalForge scan completed successfully.")

if __name__ == "__main__":
    main()
