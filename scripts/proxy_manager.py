import random
import threading
from typing import Optional, List, Dict, Iterable, Set
import yaml
import os
import time
import requests
import csv
import re

# Environment / runtime configuration
PRIMARY_PROXY = os.getenv("PRIMARY_PROXY")  # e.g. http://user:pass@host:port
DISABLE_PUBLIC_PROXIES = os.getenv("DISABLE_PUBLIC_PROXIES") == "1"
SCRAPER_UA = os.getenv("SCRAPER_UA")  # override rotating UA
MIN_PROXY_HEALTH = int(os.getenv("MIN_PROXY_HEALTH", "-3"))  # when failures score <= value, quarantine
RETRY_BACKOFF_BASE = float(os.getenv("RETRY_BACKOFF_BASE", "0.6"))
MAX_BACKOFF = float(os.getenv("MAX_BACKOFF", "4.0"))
ENABLE_BLOCK_DETECT = os.getenv("ENABLE_BLOCK_DETECT", "1") == "1"
SHORT_CIRCUIT_ON_FIRST_403 = os.getenv("SHORT_CIRCUIT_ON_FIRST_403", "1") == "1"
LENIENT_ON_BLOCK = os.getenv("LENIENT_ON_BLOCK", "0") == "1"  # if set, still return response even if flagged blocked
ADAPTIVE_BLOCK = os.getenv("ADAPTIVE_BLOCK", "1") == "1"  # multi-pass strategy before giving up
BLOCK_MIN_CONTENT_BYTES = int(os.getenv("BLOCK_MIN_CONTENT_BYTES", "3000"))  # accept if above size even if signals found
BLOCK_EXPECT_PATTERNS = os.getenv("BLOCK_EXPECT_PATTERNS", "chapter,read,next").lower().split(',')  # keywords that suggest real content
BLOCK_SIGNAL_MIN_HITS = int(os.getenv("BLOCK_SIGNAL_MIN_HITS", "1"))  # require at least this many block signals to treat as blocked
BLOCK_ACCEPT_IF_METADATA = os.getenv("BLOCK_ACCEPT_IF_METADATA", "1") == "1"  # allow if core novel metadata markers present

_proxies_lock = threading.Lock()
_proxies: List[str] = []
_last_load_time: float = 0.0
_CACHE_TTL = 300  # seconds to reload proxies.yaml
_proxy_failures: Dict[str, int] = {}
_quarantined_until: Dict[str, float] = {}
_QUARANTINE_SECONDS = 600
_dead_proxies: Set[str] = set()  # permanently excluded once they hard-fail or block

NEVER_REUSE_FAILED = os.getenv("NEVER_REUSE_FAILED", "1") == "1"

PROXY_YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'proxies.yaml')
PROXY_CSV_PATH = os.path.join(os.path.dirname(__file__), 'proxy_list.csv')


def _load_proxies(force: bool = False) -> None:
    global _proxies, _last_load_time
    with _proxies_lock:
        now = time.time()
        if force or now - _last_load_time > _CACHE_TTL or not _proxies:
            collected: List[str] = []
            # YAML source (plain list of proxy URLs)
            if os.path.exists(PROXY_YAML_PATH):
                try:
                    with open(PROXY_YAML_PATH, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                    items = data.get('proxies', []) if isinstance(data, dict) else []
                    for raw in items:
                        if not isinstance(raw, str):
                            continue
                        p = raw.strip()
                        if not p:
                            continue
                        if '://' in p:
                            collected.append(p)
                        elif ':' in p:
                            # assume http if only host:port is provided
                            collected.append(f"http://{p}")
                        else:
                            # skip bare IPs without port
                            continue
                except Exception as e:
                    print(f"[proxy_manager] Failed to load proxies.yaml: {e}")
            # CSV source (columns: ip, port, protocols)
            if os.path.exists(PROXY_CSV_PATH):
                try:
                    with open(PROXY_CSV_PATH, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            ip = (row.get('ip') or '').strip()
                            port = str(row.get('port') or '').strip()
                            proto = (row.get('protocols') or '').strip().lower()
                            if not ip or not port:
                                continue
                            # Map protocol to URL scheme supported by requests
                            if proto.startswith('socks5'):
                                scheme = 'socks5'
                            elif proto.startswith('socks4'):
                                scheme = 'socks4'
                            else:
                                # treat any http/https as http proxy
                                scheme = 'http'
                            collected.append(f"{scheme}://{ip}:{port}")
                except Exception as e:
                    print(f"[proxy_manager] Failed to load proxy_list.csv: {e}")

            # Normalize, dedupe, shuffle
            dedup = []
            seen_set = set()
            for p in collected:
                p = p.strip()
                if not p or p in seen_set:
                    continue
                seen_set.add(p)
                dedup.append(p)
            random.shuffle(dedup)
            if DISABLE_PUBLIC_PROXIES:
                _proxies = []
            else:
                # Drop any quarantined proxies still within quarantine window
                now_ts = time.time()
                filtered = [p for p in dedup if (p not in _quarantined_until or _quarantined_until[p] < now_ts) and p not in _dead_proxies]
                _proxies = filtered
            _last_load_time = now


def get_random_proxy_url() -> Optional[str]:
    _load_proxies()
    if PRIMARY_PROXY:
        return PRIMARY_PROXY
    if not _proxies:
        return None
    return random.choice(_proxies)


def get_all_proxies() -> List[str]:
    """Return a snapshot of all configured proxies (may be empty)."""
    _load_proxies()
    return list(_proxies)


def sample_proxy_pool(count: int) -> List[Optional[str]]:
    """Sample up to `count` proxies for parallel streams.

    If there are fewer proxies than `count`, this returns all proxies and pads
    the remainder with None values to indicate direct connection as fallback.
    """
    _load_proxies()
    if count <= 0:
        return []
    if PRIMARY_PROXY:
        # Always include primary proxy as first slot, rest None (direct) to avoid hammering
        return [PRIMARY_PROXY] + [None] * (count - 1)
    if not _proxies:
        return [None] * count
    # Prefer SOCKS proxies for better CONNECT support
    socks = [p for p in _proxies if p.startswith('socks')]
    http = [p for p in _proxies if not p.startswith('socks')]
    pool = socks or http
    if len(pool) >= count:
        base = random.sample(pool, count)
    else:
        base = list(pool)
    while len(base) < count:
        base.append(None)  # prefer leaving some streams without proxy than repeating too much
    return base[:count]


def build_requests_proxy(proxy_url: Optional[str]) -> Optional[Dict[str, str]]:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


class BlockedError(RuntimeError):
    """Raised when response appears to be from anti-bot / block page."""
    pass


def _looks_blocked(resp: requests.Response) -> bool:
    if resp.status_code in (401, 403, 429):
        return True
    txt = resp.text.lower()[:16000]
    signals = [
        'captcha', 'access denied', 'forbidden', 'cloudflare', 'ddos protection',
        'verify you are human', 'just a moment'
    ]
    hits = [s for s in signals if s in txt]
    if len(hits) < BLOCK_SIGNAL_MIN_HITS:
        return False
    if BLOCK_ACCEPT_IF_METADATA:
        # If page already contains strong metadata markers for a novel page, treat as legitimate
        # Common selectors / tokens: title tag with novel name context, og:novel:author, m-book1 image container
        if any(k in txt for k in ['og:novel:author', 'og:novel:novel_name', 'm-book1', 'synopsis']):
            return False
    return True


def fetch_with_proxy_rotation(
    url: str,
    *,
    retries: int = 4,
    timeout: int = 15,
    allow_no_proxy: bool = True,
    preferred_first_proxy: Optional[str] = None,
    avoid_proxies: Optional[Iterable[Optional[str]]] = None,
) -> requests.Response:
    """Attempt to fetch a URL rotating proxies on failure.

    Order:
      1. If `preferred_first_proxy` is provided, try it first.
      2. Else (optional) first attempt without proxy if `allow_no_proxy`.
      3. Subsequent attempts with random proxies (unique sequence where possible),
         avoiding any proxies provided in `avoid_proxies` when feasible.
    """
    attempted: List[Optional[str]] = []
    avoid: Set[Optional[str]] = set(avoid_proxies or [])
    last_exc: Optional[Exception] = None
    user_agents = [
        # A small pool of realistic desktop UAs
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    ]
    for attempt in range(retries):
        if attempt == 0 and preferred_first_proxy is not None:
            proxy_url = preferred_first_proxy
        elif attempt == 0 and allow_no_proxy and not PRIMARY_PROXY:
            proxy_url = None
        elif attempt == 1 and allow_no_proxy and not PRIMARY_PROXY:
            proxy_url = None
        else:
            # Build a candidate set avoiding previously attempted and avoid list
            _load_proxies()
            available = [p for p in _proxies if p not in attempted and p not in avoid and p not in _dead_proxies]
            proxy_url = None
            if available:
                proxy_url = random.choice(available)
            else:
                # If we haven't tried direct yet and it's allowed, try it now
                if allow_no_proxy and None not in attempted:
                    proxy_url = None
                else:
                    # Fall back to any proxy not in avoid, even if re-trying
                    fallback = [p for p in _proxies if p not in avoid] or [None]
                    proxy_url = random.choice(fallback)
        attempted.append(proxy_url)
        proxies = build_requests_proxy(proxy_url)
        headers = {
            'User-Agent': SCRAPER_UA or random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Connection': 'keep-alive',
            'Referer': 'https://freewebnovel.com/'
        }
        try:
            resp = requests.get(url, timeout=timeout, proxies=proxies, headers=headers)
            resp.raise_for_status()
            if ENABLE_BLOCK_DETECT and _looks_blocked(resp):
                txt_lower = resp.text.lower()
                size_ok = len(resp.content) >= BLOCK_MIN_CONTENT_BYTES
                pattern_hits = sum(1 for k in BLOCK_EXPECT_PATTERNS if k and k in txt_lower)
                adaptive_accept = ADAPTIVE_BLOCK and (size_ok and pattern_hits >= 1)
                if LENIENT_ON_BLOCK or adaptive_accept:
                    reason = "LENIENT_ON_BLOCK" if LENIENT_ON_BLOCK else f"ADAPTIVE(size_ok={size_ok}, patterns={pattern_hits})"
                    print(f"[proxy_manager] Block signals present but accepting via {reason}: {url}")
                else:
                    # One extra alternate-UA attempt (once) if adaptive not allowed
                    alt_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'
                    if 'attempt-alt-ua' not in headers:
                        headers['User-Agent'] = alt_ua
                        headers['attempt-alt-ua'] = '1'
                        try:
                            resp2 = requests.get(url, timeout=timeout, proxies=proxies, headers=headers)
                            resp2.raise_for_status()
                            if ENABLE_BLOCK_DETECT and _looks_blocked(resp2):
                                raise BlockedError(f"Blocked content detected (status={resp2.status_code}) after alt UA")
                            print(f"[proxy_manager] Recovered after alt UA for {url}")
                            if proxy_url and proxy_url in _proxy_failures:
                                _proxy_failures[proxy_url] = 0
                            return resp2
                        except Exception as e_alt:
                            last_exc = e_alt
                            # print(f"[proxy_manager] Alt UA retry still blocked: {e_alt}")
                    if proxy_url and NEVER_REUSE_FAILED:
                        _dead_proxies.add(proxy_url)
                        # print(f"[proxy_manager] Marked proxy dead (blocked) {proxy_url}")
                    raise BlockedError(f"Blocked content detected (status={resp.status_code})")
            if attempt > 0:
                print(f"[proxy_manager] Success after {attempt+1} attempt(s) using proxy={proxy_url}")
            if proxy_url and proxy_url in _proxy_failures:
                _proxy_failures[proxy_url] = 0
            return resp
        except BlockedError as e:
            last_exc = e
            # print(f"[proxy_manager] Blocked for {url} proxy={proxy_url}: {e}")
            if proxy_url:
                if NEVER_REUSE_FAILED:
                    _dead_proxies.add(proxy_url)
                    # print(f"[proxy_manager] Permanently disabling blocked proxy {proxy_url}")
                _proxy_failures[proxy_url] = _proxy_failures.get(proxy_url, 0) - 1
            if SHORT_CIRCUIT_ON_FIRST_403:
                break
        except Exception as e:
            last_exc = e
            # print(f"[proxy_manager] Attempt {attempt+1}/{retries} failed for {url} proxy={proxy_url}: {e}")
            if proxy_url:
                if NEVER_REUSE_FAILED:
                    _dead_proxies.add(proxy_url)
                    # print(f"[proxy_manager] Permanently disabling failed proxy {proxy_url}")
                else:
                    score = _proxy_failures.get(proxy_url, 0) + 1
                    _proxy_failures[proxy_url] = score
                    if score <= MIN_PROXY_HEALTH:
                        _quarantined_until[proxy_url] = time.time() + _QUARANTINE_SECONDS
                        # print(f"[proxy_manager] Quarantined {proxy_url} fail_score={score}")
        # Backoff with jitter unless last attempt
        if attempt < retries - 1:
            sleep_for = min(MAX_BACKOFF, RETRY_BACKOFF_BASE * (2 ** attempt))
            sleep_for *= random.uniform(0.75, 1.25)
            time.sleep(sleep_for)
    # Exhausted
    assert last_exc is not None
    raise last_exc
