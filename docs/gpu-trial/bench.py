#!/usr/bin/env python3
"""Run a prompt set against any OpenAI-compatible endpoint and record what actually happened.

Judges three things a vendor benchmark does not: whether the model returns parseable JSON every time,
how long it takes on our real prompt sizes, and what it actually says — kept verbatim so a human can
read it rather than trust a score.

    # local model on the rented GPU
    python bench.py --base-url http://127.0.0.1:8000/v1 --model local-coder --repeat 3 --label local

    # the hosted baseline, for comparison
    python bench.py --base-url https://api.deepseek.com/v1 --model deepseek-flash \
                    --api-key-file ~/.config/deepseek/api_key --repeat 3 --label hosted

    python compare.py results/local-*.json results/hosted-*.json
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def call(base_url, model, api_key, system, user, max_tokens, timeout, extra=None):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    # Provider-specific switches (e.g. DeepSeek's {"thinking": {"type": "disabled"}}). Without this,
    # a reasoning model can spend the entire budget on hidden thinking and return empty content — which
    # looks like a model failure and is actually a harness bug.
    if extra:
        payload.update(extra)
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers=headers, method="POST")
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    elapsed = time.time() - started
    payload = json.loads(raw)
    content = payload["choices"][0]["message"].get("content") or ""
    usage = payload.get("usage") or {}
    return content, usage, elapsed


def extract_json(text):
    """Models wrap JSON in fences or prose. Try hard before calling it a parse failure."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        return json.loads(text), None
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1]), None
            except Exception as exc:
                return None, str(exc)[:200]
        return None, "no JSON object found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", default="sample_prompt.json")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key-file")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--label", default="run")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--extra-json", help='provider switches, e.g. \'{"thinking":{"type":"disabled"}}\'')
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    extra = json.loads(args.extra_json) if args.extra_json else None

    api_key = ""
    if args.api_key_file and os.path.exists(args.api_key_file):
        api_key = open(args.api_key_file).read().strip()

    prompts = json.load(open(args.prompts))
    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = {"label": args.label, "model": args.model, "base_url": args.base_url,
               "at": stamp, "runs": []}

    for prompt in prompts:
        for i in range(args.repeat):
            entry = {"prompt": prompt["name"], "expect": prompt.get("expect"), "run": i + 1}
            try:
                content, usage, elapsed = call(args.base_url, args.model, api_key,
                                               prompt["system"], prompt["user"],
                                               args.max_tokens, args.timeout, extra)
                entry.update({"ok": True, "seconds": round(elapsed, 1),
                              "prompt_tokens": usage.get("prompt_tokens"),
                              "completion_tokens": usage.get("completion_tokens"),
                              "tokens_per_second": round(
                                  (usage.get("completion_tokens") or 0) / elapsed, 1) if elapsed else None,
                              "output": content})
                if prompt.get("expect") == "json":
                    parsed, err = extract_json(content)
                    entry["json_valid"] = parsed is not None
                    entry["json_error"] = err
                    entry["keys"] = sorted(parsed.keys()) if isinstance(parsed, dict) else None
            except urllib.error.HTTPError as exc:
                entry.update({"ok": False, "error": f"HTTP {exc.code}: {exc.read().decode()[:200]}"})
            except Exception as exc:
                import traceback
                entry.update({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                              "traceback": traceback.format_exc()[-700:]})
            results["runs"].append(entry)
            status = "ok" if entry.get("ok") else "FAILED"
            note = ""
            if entry.get("expect") == "json" and entry.get("ok"):
                note = f" | json={'valid' if entry.get('json_valid') else 'INVALID'}"
            print(f"{prompt['name']} run {i + 1}: {status} "
                  f"{entry.get('seconds', '')}s{note} {entry.get('error', '')}")

    path = os.path.join(args.outdir, f"{args.label}-{stamp}.json")
    json.dump(results, open(path, "w"), indent=1)
    print("wrote", path)


if __name__ == "__main__":
    sys.exit(main())
