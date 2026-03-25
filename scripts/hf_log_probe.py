import itertools
import json
import os
import re
import sys

import requests


def extract_filtered_lines(url: str, token: str, max_lines: int = 800) -> list[str]:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, stream=True, timeout=30)
    out: list[str] = [f"status={r.status_code}"]
    if r.status_code != 200:
        out.append(r.text[:500])
        return out

    pat = re.compile(
        r"error|traceback|exception|failed|epub|upload|storage|chapter fetch failed|"
        r"generation failed|500|no_chapters|source_blocked|source_not_found|s3|bucket|mongo|sql",
        re.I,
    )

    matched: list[str] = []
    for ln in itertools.islice(r.iter_lines(decode_unicode=True), max_lines):
        if not ln:
            continue
        txt = ln
        if ln.startswith("data: "):
            payload = ln[6:]
            try:
                txt = json.loads(payload).get("data", payload)
            except Exception:
                txt = payload
        if pat.search(txt):
            matched.append(txt)

    out.extend(matched[-200:])
    if len(out) == 1:
        out.append("No matching lines in sampled stream")
    return out


def main() -> None:
    token = (sys.argv[1] if len(sys.argv) > 1 else "") or os.getenv("HF_TOKEN") or ""
    if not token:
        print("HF_TOKEN missing")
        return

    base = "https://huggingface.co/api/spaces/ArnolDADI/webnovel-to-epub/logs"
    for kind in ("run", "build"):
        print(f"\n--- {kind.upper()} ---")
        for line in extract_filtered_lines(f"{base}/{kind}", token):
            print(line)


if __name__ == "__main__":
    main()
