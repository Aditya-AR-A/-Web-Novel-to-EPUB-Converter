from scripts.proxy_manager import fetch_with_proxy_rotation, get_all_proxies, _proxy_failures, _quarantined_until
import requests

print("Testing direct connection...")
try:
    resp = fetch_with_proxy_rotation("https://freewebnovel.com/novel/invalid-url-that-does-not-exist/chapter-1", retries=3)
except Exception as e:
    print("Expected exception caught.")

print("_proxy_failures:", _proxy_failures)
