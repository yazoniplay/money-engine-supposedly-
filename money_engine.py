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
from threading import BoundedSemaphore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SignalForge")

STATE_FILE = os.path.join("data", "state.json")

DEFAULT_SUBREDDITS = [
    "forhire", "freelance_forhire", "startups", "entrepreneur",
    "smallbusiness", "SaaS", "ArtificialInteligence", "LocalLLaMA",
    "automation", "nocode", "businessautomation", "solopreneur",
    "AIagents", "ChatGPTCoding", "python", "growthhacking",
    "machinelearning", "mlops", "productivity", "techbiz", "hiring", "jobbit"
]

DEFAULT_SEARCH_TERMS = [
    "AI automation", "build AI agent", "chatbot developer",
    "automate workflow", "LLM integration", "Zapier alternative",
    "custom GPT", "AI scraping", "lead generation bot",
    "AI developer needed", "AI automation agency", "LLM consultant",
    "automate my business", "hire AI expert", "workflow automation",
    "automate lead gen", "AI pipeline", "hire AI", "AI expert"
]

def get_env_int(key, default):
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning(f"Environment variable {key} has invalid value '{val}', using default {default}")
        return default

REDDIT_CONCURRENCY = get_env_int("REDDIT_CONCURRENCY", 6)
GEMINI_CONCURRENCY = get_env_int("GEMINI_CONCURRENCY", 4)

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
        if "seen_ids" in state and len(state["seen_ids"]) > 5000:
            state["seen_ids"] = state["seen_ids"][-5000:]
        tmp_file = STATE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, STATE_FILE)
    except Exception as e:
        logger.error(f"Could not save state file atomically: {e}")

def fetch_reddit_posts(subreddits, search_terms, max_age_hours):
    posts = []
    seen_urls = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    user_agent = os.getenv("REDDIT_USER_AGENT", "SignalForgeBot/3.0")
    headers = {"User-Agent": user_agent}
    
    reddit_sem = BoundedSemaphore(REDDIT_CONCURRENCY)

    def fetch_sub_term(sub, term):
        local_posts = []
        query = urllib.parse.quote(term, safe="")
        url = f"https://www.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=1&sort=new&limit=50"
        req = urllib.request.Request(url, headers=headers)
        reddit_sem.acquire()
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
                children = data.get("data", {}).get("children", [])
                for child in children:
                    pdata = child.get("data", {})
                    pid = pdata.get("id")
                    if not pid:
                        continue
                    title = pdata.get("title", "")
                    selftext = pdata.get("selftext", "")
                    created_utc = pdata.get("created_utc", 0)
                    permalink = pdata.get("permalink", "")
                    url_link = pdata.get("url", "")
                    
                    post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                    if post_time < cutoff:
                        continue
                        
                    full_url = f"https://reddit.com{permalink}" if permalink else url_link
                    
                    local_posts.append({
                        "id": f"reddit_{pid}",
                        "title": title,
                        "content": selftext[:2000],
                        "url": full_url,
                        "source": f"r/{sub}"
                    })
        except Exception as e:
            logger.debug(f"Error fetching r/{sub} for '{term}': {e}")
        finally:
            reddit_sem.release()
        return local_posts

    tasks = [(sub, term) for sub in subreddits for term in search_terms]
    with ThreadPoolExecutor(max_workers=REDDIT_CONCURRENCY) as executor:
        futures = {executor.submit(fetch_sub_term, sub, term): (sub, term) for sub, term in tasks}
        for future in as_completed(futures):
            try:
                res = future.result()
                for p in res:
                    if p["url"] not in seen_urls:
                        seen_urls.add(p["url"])
                        posts.append(p)
            except Exception as e:
                logger.debug(f"Task execution error: {e}")
            time.sleep(0.02)
            
    return posts

def analyze_with_gemini(posts, api_key, model):
    if not posts:
        return []
        
    scored_posts = []
    min_score = get_env_int("MIN_LEAD_SCORE", 8)
    
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

    gemini_sem = BoundedSemaphore(GEMINI_CONCURRENCY)

    def evaluate_single_post(p):
        prompt = (
            "You are a B2B Lead Qualification Expert. Analyze if the author is actively seeking to HIRE or BUY AI automation, "
            "AI agents, custom LLM solutions, or workflow automation. Look for intent signals like 'looking for', 'recommendations', "
            "'need a developer', 'how to automate'.\n"
            f"Title: {p['title']}\nContent: {p['content']}\n\n"
            "Return ONLY a valid JSON object with keys: 'score' (integer 1-10) and 'rationale' (string explanation)."
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = json.dumps(payload).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        gemini_sem.acquire()
        try:
            for attempt in range(2):
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
                            return None
                except Exception as e:
                    if attempt == 1:
                        logger.debug(f"Gemini scoring error for post {p['id']}: {e}")
                    time.sleep(0.5)
        finally:
            gemini_sem.release()
        return None

    with ThreadPoolExecutor(max_workers=GEMINI_CONCURRENCY) as executor:
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
            if resp.status not in (200, 204):
                logger.warning(f"Discord notification failed with status {resp.status}")
    except Exception as e:
        logger.error(f"Failed to send Discord webhook: {e}")

def main():
    logger.info("Starting SignalForge high-speed expanded lead scan...")
    
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    max_age_hours = get_env_int("MAX_POST_AGE_HOURS", 72)
    
    sub_env = os.getenv("SUBREDDITS", "").strip()
    if sub_env:
        subreddits = [s.strip() for s in sub_env.split(",") if s.strip()]
    else:
        subreddits = DEFAULT_SUBREDDITS
        
    search_env = os.getenv("SEARCH_TERMS", "").strip()
    if search_env:
        search_terms = [t.strip() for t in search_env.split(",") if t.strip()]
    else:
        search_terms = DEFAULT_SEARCH_TERMS
        
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))
    
    logger.info(f"Scanning {len(subreddits)} subreddits with {len(search_terms)} search terms (Max age: {max_age_hours}h)...")
    posts = fetch_reddit_posts(subreddits, search_terms, max_age_hours)
    logger.info(f"Fetched {len(posts)} total raw posts across subreddits.")
    
    new_posts = [p for p in posts if p["id"] not in seen_ids]
    logger.info(f"{len(new_posts)} posts are new since last state sync.")
    
    if not new_posts:
        logger.info("No new posts to analyze.")
        return
        
    logger.info(f"Analyzing {len(new_posts)} posts with Gemini / heuristics...")
    scored_leads = analyze_with_gemini(new_posts, gemini_api_key, gemini_model)
    logger.info(f"Found {len(scored_leads)} high-intent leads meeting score threshold.")
    
    for lead in scored_leads:
        send_discord_notification(lead, discord_webhook)
        time.sleep(0.2)
        
    for p in new_posts:
        seen_ids.add(p["id"])
        
    state["seen_ids"] = list(seen_ids)
    save_state(state)
    logger.info("SignalForge lead scan completed successfully.")

if __name__ == "__main__":
    main()
