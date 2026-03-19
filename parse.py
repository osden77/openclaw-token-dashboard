#!/usr/bin/env python3
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

GLOB = "/Users/serveradmin/.openclaw/agents/*/sessions/*.jsonl"
OUT  = "/Users/serveradmin/token-dashboard/data.json"

models   = defaultdict(lambda: {"calls": 0, "input": 0, "output": 0,
                                 "cache_read": 0, "cache_write": 0, "cost": 0.0})
daily    = defaultdict(lambda: defaultdict(float))  # date -> model -> cost
last_ts  = None

for path in glob.glob(GLOB):
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "message":
                continue

            msg = entry.get("message", {})
            usage = msg.get("usage", {})
            cost_block = usage.get("cost", {})
            total_cost = cost_block.get("total", 0) or 0

            provider = msg.get("provider", "unknown")
            model    = msg.get("model", "unknown")
            key      = f"{provider}/{model}"

            ts_raw = entry.get("timestamp", "")
            if ts_raw:
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    date_str = ts.date().isoformat()
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                except ValueError:
                    date_str = "unknown"
            else:
                date_str = "unknown"

            m = models[key]
            m["calls"]       += 1
            m["input"]       += usage.get("input", 0) or 0
            m["output"]      += usage.get("output", 0) or 0
            m["cache_read"]  += usage.get("cacheRead", 0) or 0
            m["cache_write"] += usage.get("cacheWrite", 0) or 0
            m["cost"]        += total_cost

            daily[date_str][key] += total_cost

# Build model rows
model_rows = []
for key, m in sorted(models.items(), key=lambda x: -x[1]["cost"]):
    provider, _, model_name = key.partition("/")
    model_rows.append({
        "key":         key,
        "provider":    provider,
        "model":       model_name,
        "calls":       m["calls"],
        "input":       m["input"],
        "output":      m["output"],
        "cache_read":  m["cache_read"],
        "cache_write": m["cache_write"],
        "cost":        round(m["cost"], 6),
    })

# Build timeline (sorted by date)
timeline = []
for date in sorted(daily.keys()):
    for key, cost in sorted(daily[date].items()):
        timeline.append({"date": date, "model": key, "cost": round(cost, 6)})

# Totals
total_cost   = sum(r["cost"] for r in model_rows)
total_calls  = sum(r["calls"] for r in model_rows)
total_tokens = sum(r["input"] + r["output"] + r["cache_read"] + r["cache_write"]
                   for r in model_rows)

out = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "last_entry_at": last_ts.isoformat() if last_ts else None,
    "totals": {
        "cost":   round(total_cost, 6),
        "calls":  total_calls,
        "tokens": total_tokens,
    },
    "models":   model_rows,
    "timeline": timeline,
}

with open(OUT, "w") as f:
    json.dump(out, f, indent=2)

print(f"Wrote {OUT}")
print(f"  Models : {len(model_rows)}")
print(f"  Entries: {total_calls} calls, ${total_cost:.4f} total")
