"""
=========================================================================================
NEXUS LEAD GENERATION ENGINE - OMEGA ARCHITECTURE (V4.0.0)
=========================================================================================
Capabilities:
- Asynchronous Network I/O (asyncio, aiohttp)
- Local State Management & Deduplication (SQLite3)
- Live Infrastructure Ping & Load Time Validation
- Heuristic JSON Repair & Fallback Parsers
- Dynamic Market Scoring Algorithms
- Omnichannel Dispatch Routing (Discord Rich Embeds)
=========================================================================================
"""

import os
import re
import json
import time
import uuid
import random
import logging
import sqlite3
import asyncio
import traceback
from urllib.parse import urlparse
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple, Callable

# Attempt to load advanced HTTP and AI libraries
try:
    import aiohttp
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("CRITICAL: Missing dependencies. Run: pip install aiohttp google-genai")

# ============================================================================
# 1. ENTERPRISE CONFIGURATION & TARGET VECTORS
# ============================================================================

class Config:
    """Singleton Configuration Manager ensuring strict environment validation."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
        self.DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "nexus_state.db"))
        self.MAX_RETRIES = 3
        self.TIMEOUT_SECONDS = 15
        
        self.VERTICALS = [
            "Commercial HVAC & Mechanical Contractors",
            "Private Dental, Orthodontic, and Oral Surgery Practices",
            "Boutique Corporate Law & Estate Planning Offices",
            "Luxury Architecture and Custom Home Builders",
            "High-End MedSpas and Aesthetic Clinics",
            "Independent Luxury Auto Detailing Studios",
            "Private Wealth Management Firms"
        ]
        
        self.REGIONS = [
            "Stockholm, Sweden", "Gothenburg, Sweden",
            "Austin, TX, USA", "Denver, CO, USA",
            "London, United Kingdom", "Manchester, United Kingdom",
            "Copenhagen, Denmark", "Zurich, Switzerland",
            "Dubai, UAE", "Singapore"
        ]

    def validate(self):
        if not self.GEMINI_API_KEY:
            raise ValueError("FATAL: GEMINI_API_KEY is not set in the environment.")
        if not self.DISCORD_WEBHOOK_URL:
            logging.getLogger("Nexus").warning("DISCORD_WEBHOOK_URL not set. Running in dry-run mode.")

config = Config()

# ============================================================================
# 2. TELEMETRY & OBSERVABILITY
# ============================================================================

def setup_telemetry() -> logging.Logger:
    """Initializes high-fidelity logging with UTC timestamps and thread contexts."""
    logger = logging.getLogger("Nexus")
    logger.setLevel(logging.DEBUG)
    
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03dZ | %(levelname)-8s | [%(module)s:%(lineno)d] | %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
        formatter.converter = time.gmtime
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger

log = setup_telemetry()

# ============================================================================
# 3. DOMAIN MODELS & DATA STRUCTURES
# ============================================================================

@dataclass
class TargetContext:
    vertical: str
    region: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class LiveMetrics:
    status_code: int = 0
    load_time_ms: float = 0.0
    is_live: bool = False
    ssl_valid: bool = False

@dataclass
class Lead:
    business_name: str
    domain: str
    location: str
    base_score: int
    est_value: str
    ai_infrastructure_flaw: str
    outreach_hook: str
    live_metrics: LiveMetrics = field(default_factory=LiveMetrics)
    final_score: int = 0
    is_duplicate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# ============================================================================
# 4. STATE MANAGEMENT (SQLite Deduplication)
# ============================================================================

class StateManager:
    """Manages local SQLite database to ensure zero duplicate outreach."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        log.debug(f"Initializing SQLite state manager at {self.db_path}")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT,
                    domain TEXT UNIQUE,
                    discovered_at TEXT,
                    run_id TEXT
                )
            """)
            conn.commit()

    def is_duplicate(self, domain: str) -> bool:
        if not domain or domain.lower() in ['none', 'n/a', '']:
            return False # Cannot deduplicate missing domains reliably here
            
        normalized = urlparse(domain if "://" in domain else f"http://{domain}").netloc
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM leads WHERE domain = ?", (normalized,))
            return cursor.fetchone() is not None

    def record_lead(self, lead: Lead, run_id: str):
        if lead.domain and lead.domain.lower() not in ['none', 'n/a', '']:
            normalized = urlparse(lead.domain if "://" in lead.domain else f"http://{lead.domain}").netloc
            with sqlite3.connect(self.db_path) as conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO leads (business_name, domain, discovered_at, run_id) VALUES (?, ?, ?, ?)",
                        (lead.business_name, normalized, datetime.now(timezone.utc).isoformat(), run_id)
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass # Already exists

# ============================================================================
# 5. LIVE INFRASTRUCTURE VALIDATION (Async)
# ============================================================================

class InfrastructureScanner:
    """Asynchronously pings target domains to measure real-world performance."""
    
    @staticmethod
    async def ping_domain(domain: str, session: aiohttp.ClientSession) -> LiveMetrics:
        if not domain or domain.lower() in ['none', 'n/a', 'null']:
            return LiveMetrics(is_live=False)
            
        url = domain if domain.startswith("http") else f"https://{domain}"
        start_time = time.perf_counter()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                load_time = (time.perf_counter() - start_time) * 1000
                return LiveMetrics(
                    status_code=response.status,
                    load_time_ms=round(load_time, 2),
                    is_live=response.status < 400,
                    ssl_valid=url.startswith("https")
                )
        except Exception as e:
            log.debug(f"Ping failed for {url}: {str(e)[:50]}")
            return LiveMetrics(is_live=False)

    @classmethod
    async def enrich_leads(cls, leads: List[Lead]):
        log.info(f"Initiating asynchronous infrastructure pings for {len(leads)} targets...")
        async with aiohttp.ClientSession() as session:
            tasks = [cls.ping_domain(lead.domain, session) for lead in leads]
            metrics_results = await asyncio.gather(*tasks)
            
            for lead, metrics in zip(leads, metrics_results):
                lead.live_metrics = metrics
                
                # Dynamic Scoring Algorithm
                score_mod = 0
                if not metrics.is_live: score_mod += 15 # Dead site = high priority for rebuild
                if metrics.load_time_ms > 3000: score_mod += 10 # Slow site = performance pitch
                
                lead.final_score = min(100, lead.base_score + score_mod)

# ============================================================================
# 6. HEURISTIC JSON PARSER
# ============================================================================

class JSONRepairEngine:
    """Repairs broken JSON payloads generated by LLM hallucinations."""
    
    @staticmethod
    def extract_and_parse(raw_text: str) -> Dict[str, Any]:
        # 1. Strip markdown fences if present
        clean_text = re.sub(r'```json|```', '', raw_text).strip()
        
        # 2. Try standard parse
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            log.warning("Standard JSON parse failed. Attempting heuristic repair...")
            
        # 3. Repair trailing commas
        clean_text = re.sub(r',\s*([\]}])', r'\1', clean_text)
        
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            log.critical(f"Heuristic repair failed: {e}")
            raise ValueError(f"Irreparable JSON payload: {clean_text[:200]}...")

# ============================================================================
# 7. AI RECONNAISSANCE MODULE
# ============================================================================

class IntelligenceAgent:
    """Handles communication with Google Gemini via asynchronous threading."""
    
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.schema = (
            "{"
            "\"leads\": ["
            "{\"business_name\": \"str\", \"domain\": \"str (or 'None')\", \"location\": \"str\", "
            "\"base_score\": int, \"est_value\": \"str\", \"ai_infrastructure_flaw\": \"str\", "
            "\"outreach_hook\": \"str\"}"
            "]"
            "}"
        )

    def _build_prompt(self, context: TargetContext) -> str:
        return (
            f"EXECUTE RECONNAISSANCE PROTOCOL.\n"
            f"Target Vertical: {context.vertical}\n"
            f"Geographic Vector: {context.region}\n\n"
            f"Identify 4 real, active businesses matching this vector that have severe digital "
            f"vulnerabilities (missing sites, outdated UI, broken mobile). "
            f"Calculate a 'base_score' (1-100) estimating ease of closing. "
            f"Provide a realistic contract 'est_value' (e.g., '2,500 - 4,000').\n"
            f"Write a hyper-personalized 2-sentence 'outreach_hook'.\n\n"
            f"CRITICAL REQUIREMENT: Output strictly minified JSON matching this schema exactly. No markdown.\n"
            f"{self.schema}"
        )

    def _blocking_call(self, prompt: str) -> str:
        res = self.client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction="Autonomous data extraction engine. Return ONLY valid JSON.",
                response_mime_type="application/json",
                temperature=0.3
            )
        )
        return res.text

    async def scan_market(self, context: TargetContext) -> List[Lead]:
        log.info(f"Querying Gemini AI for {context.vertical} in {context.region}")
        prompt = self._build_prompt(context)
        
        # Offload sync SDK call to threadpool to prevent blocking the async event loop
        raw_response = await asyncio.to_thread(self._blocking_call, prompt)
        
        parsed = JSONRepairEngine.extract_and_parse(raw_response)
        
        leads = []
        for item in parsed.get("leads", []):
            leads.append(Lead(
                business_name=item.get("business_name", "Unknown"),
                domain=item.get("domain", ""),
                location=item.get("location", ""),
                base_score=int(item.get("base_score", 50)),
                est_value=str(item.get("est_value", "1,000")),
                ai_infrastructure_flaw=item.get("ai_infrastructure_flaw", "Unknown"),
                outreach_hook=item.get("outreach_hook", "N/A")
            ))
        return leads

# ============================================================================
# 8. DISPATCH ROUTER
# ============================================================================

class DiscordRouter:
    """Asynchronous payload formatting and dispatching to Discord."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def _format_embed(self, lead: Lead, ctx: TargetContext) -> Dict:
        slug = lead.business_name.lower().replace(" ", "-").replace("'", "")
        
        # Dynamic telemetry string
        if lead.live_metrics.load_time_ms > 0:
            ping_str = f"{lead.live_metrics.load_time_ms}ms"
        else:
            ping_str = "TIMEOUT/OFFLINE"

        return {
            "title": f"[{lead.final_score}/100] {lead.business_name}",
            "color": 16711680 if lead.final_score >= 85 else 5814783,
            "fields": [
                {"name": "📍 Vector", "value": lead.location, "inline": True},
                {"name": "🌐 Asset", "value": lead.domain, "inline": True},
                {"name": "💰 Est Value", "value": f"${lead.est_value}", "inline": True},
                {"name": "📡 Live Ping", "value": ping_str, "inline": True},
                {"name": "🚨 AI Audit", "value": lead.ai_infrastructure_flaw, "inline": False},
                {"name": "🛠️ Mockup", "value": f"https://mockups.local/{slug}", "inline": False},
                {"name": "✉️ Pitch", "value": f"```{lead.outreach_hook}```", "inline": False}
            ],
            "footer": {"text": f"Cycle: {ctx.run_id} | Engine V4"}
        }

    async def broadcast(self, leads: List[Lead], context: TargetContext):
        if not self.webhook_url:
            return
            
        embeds = [self._format_embed(l, context) for l in leads if not l.is_duplicate]
        if not embeds:
            log.warning("All leads were duplicates. Skipping Discord broadcast.")
            return

        payload = {
            "username": "Nexus Omega",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2103/2103322.png",
            "content": f"🛡️ **[OMEGA PIPELINE]** New high-value targets processed:",
            "embeds": embeds[:10] # Max 10 per request
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as res:
                if res.status >= 400:
                    log.error(f"Discord API Error: {res.status} - {await res.text()}")
                else:
                    log.info(f"Successfully routed {len(embeds)} targets to Discord.")

# ============================================================================
# 9. MASTER ORCHESTRATOR
# ============================================================================

class PipelineOrchestrator:
    """Manages the full Directed Acyclic Graph (DAG) of the intelligence cycle."""
    
    def __init__(self):
        config.validate()
        self.state = StateManager(config.DB_PATH)
        self.agent = IntelligenceAgent(config.GEMINI_API_KEY)
        self.router = DiscordRouter(config.DISCORD_WEBHOOK_URL)

    async def run_cycle(self):
        cycle_start = time.perf_counter()
        ctx = TargetContext(vertical=random.choice(config.VERTICALS), region=random.choice(config.REGIONS))
        log.info(f"=== INITIATING CYCLE {ctx.run_id} | {ctx.vertical} in {ctx.region} ===")
        
        try:
            # 1. AI Reconnaissance
            leads = await self.agent.scan_market(ctx)
            
            # 2. State Management Deduplication
            for lead in leads:
                lead.is_duplicate = self.state.is_duplicate(lead.domain)
                if not lead.is_duplicate:
                    self.state.record_lead(lead, ctx.run_id)
            
            new_leads = [l for l in leads if not l.is_duplicate]
            log.info(f"Extracted {len(leads)} leads. ({len(leads) - len(new_leads)} duplicates skipped).")
            
            if new_leads:
                # 3. Live Infrastructure Validation
                await InfrastructureScanner.enrich_leads(new_leads)
                
                # 4. Omnichannel Dispatch
                await self.router.broadcast(new_leads, ctx)
                
        except Exception as e:
            log.error(f"Critical Pipeline Failure: {e}")
            log.debug(traceback.format_exc())
            
            # Fallback alert
            await self.router.broadcast([Lead(
                business_name="PIPELINE FAULT", domain="N/A", location="N/A", base_score=0, est_value="0",
                ai_infrastructure_flaw=str(e), outreach_hook="Check core logs.", final_score=0
            )], ctx)
            
        finally:
            elapsed = time.perf_counter() - cycle_start
            log.info(f"=== CYCLE {ctx.run_id} COMPLETED IN {elapsed:.2f}s ===")

def main():
    """Application Entry Point."""
    orchestrator = PipelineOrchestrator()
    asyncio.run(orchestrator.run_cycle())

if __name__ == "__main__":
    main()
