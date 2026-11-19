#!/usr/bin/env python3
"""Turn two bench.py result files into the comparison a client meeting can survive.

    python compare.py results/local-*.json results/hosted-*.json

Writes results/compare-<label>-<label>-<stamp>.md: a score table first, then the full outputs side by
side so the reader can judge the reasoning rather than trust the score.
"""
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load(pattern):
    matches = sorted(glob.glob(pattern))
    if not matches:
        sys.exit(f"no files match {pattern}")
    return json.load(open(matches[-1]))


def summarise(result):
    out = {}
    for run in result["runs"]:
        key = run["prompt"]
        block = out.setdefault(key, {"runs": 0, "ok": 0, "json_valid": 0, "seconds": [], "tps": []})
        block["runs"] += 1
        if run.get("ok"):
            block["ok"] += 1
            block["seconds"].append(run.get("seconds") or 0)
            if run.get("tokens_per_second"):
                block["tps"].append(run["tokens_per_second"])
            if run.get("expect") == "json":
                block["json_valid"] += 1 if run.get("json_valid") else 0
    for block in out.values():
        block["median_seconds"] = round(sorted(block["seconds"])[len(block["seconds"]) // 2], 1) \
            if block["seconds"] else None
        block["median_tps"] = round(sorted(block["tps"])[len(block["tps"]) // 2], 1) if block["tps"] else None
    return out


def first_output(result, prompt, want_json=False):
    for run in result["runs"]:
        if run["prompt"] == prompt and run.get("ok"):
            text = run.get("output", "")
            if want_json:
                try:
                    start, end = text.find("{"), text.rfind("}")
                    return json.dumps(json.loads(text[start:end + 1]), indent=1)[:4000]
                except Exception:
                    return text[:4000]
            return text[:4000]
    return "_(no successful run)_"


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    sa, sb = summarise(a), summarise(b)

    lines = [
        f"# Model comparison — {a['label']} vs {b['label']}",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"- **{a['label']}**: `{a['model']}` at {a['base_url']}",
        f"- **{b['label']}**: `{b['model']}` at {b['base_url']}",
        "",
        "## Score",
        "",
        "| Prompt | Model | Runs | JSON valid | Median latency | Median tok/s |",
        "|---|---|---|---|---|---|",
    ]
    for name in sa:
        for label, summary in ((a["label"], sa[name]), (b["label"], sb.get(name, {}))):
            if not summary:
                continue
            json_col = (f"{summary['json_valid']}/{summary['runs']}"
                        if name.startswith("monitor") else "n/a")
            lines.append(f"| {name} | {label} | {summary['runs']} | {json_col} | "
                         f"{summary['median_seconds']}s | {summary['median_tps']} |")

    lines += ["", "## Outputs", ""]
    for name in sa:
        lines += [f"### {name}", ""]
        want_json = name.startswith("monitor")
        for label, result in ((a["label"], a), (b["label"], b)):
            lines += [f"**{label} — `{result['model']}`**", "", "```",
                      first_output(result, name, want_json), "```", ""]

    out = Path("results") / f"compare-{a['label']}-{b['label']}-" \
                            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    print("wrote", out)


if __name__ == "__main__":
    main()
