#!/usr/bin/env bash
# Sonar heartbeat — no_agent passive ecosystem watcher.
# SKims OpenRouter pricing, Hermes changelog/docs, AI news feed, OpenRouter status.
# Exit 0 on no-change (silent).
# Exit 1 and writes /tmp/sonar_diff.txt when changes are detected (triggers LLM pass).
set -euo pipefail

ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
HB="$HOME/.hermes/carrier/SONAR_HEARTBEAT"
DIFF_FILE="/tmp/sonar_diff.txt"

mkdir -p "$(dirname "$HB")" "$VAULT/_agent/signal_watch" "$ROOT/_agent/signal_watch"
date -u +%Y-%m-%dT%H:%M:%SZ > "$HB"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

python3 - "$VAULT" "$ROOT" "$DIFF_FILE" "$FORCE" <<'PY'
import urllib.request, json, hashlib, re, datetime, os, sys
from pathlib import Path

vault_dir = sys.argv[1]
root_dir = sys.argv[2]
diff_file_path = sys.argv[3]
force = sys.argv[4] == "1"

vault_state = Path(vault_dir) / "_agent" / "signal_watch" / "state.json"
root_state = Path(root_dir) / "_agent" / "signal_watch" / "state.json"
diff_file = Path(diff_file_path)

vault_state.parent.mkdir(parents=True, exist_ok=True)
root_state.parent.mkdir(parents=True, exist_ok=True)

now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Read prior state
old_state = {}
if vault_state.exists():
    try:
        old_state = json.loads(vault_state.read_text())
    except Exception:
        pass
elif root_state.exists():
    try:
        old_state = json.loads(root_state.read_text())
    except Exception:
        pass

sources_state = {}
diffs = []

# 1. OpenRouter Models & Pricing
try:
    req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "Carrier-Sonar/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        or_data = json.loads(resp.read().decode('utf-8'))
    models = or_data.get("data", [])
    pricing_map = {}
    for m in models:
        mid = m.get("id")
        if not mid: continue
        p = m.get("pricing") or {}
        pricing_map[mid] = {
            "name": m.get("name", mid),
            "prompt": str(p.get("prompt", "0")),
            "completion": str(p.get("completion", "0")),
            "context_length": m.get("context_length", 0),
        }
    pricing_hash = hashlib.sha256(json.dumps(pricing_map, sort_keys=True).encode()).hexdigest()
    sources_state["openrouter_pricing"] = {
        "hash": pricing_hash,
        "models_count": len(models),
        "pricing": pricing_map,
    }
    
    # Diff against old state
    old_or = old_state.get("sources", {}).get("openrouter_pricing", {})
    old_pricing = old_or.get("pricing", {})
    if old_pricing:
        old_ids = set(old_pricing.keys())
        new_ids = set(pricing_map.keys())
        added = new_ids - old_ids
        removed = old_ids - new_ids
        
        price_changes = []
        for mid in (old_ids & new_ids):
            op = old_pricing[mid]
            np = pricing_map[mid]
            try:
                op_prompt = float(op.get("prompt", "0"))
                np_prompt = float(np.get("prompt", "0"))
                op_comp = float(op.get("completion", "0"))
                np_comp = float(np.get("completion", "0"))
                
                if op_prompt != np_prompt or op_comp != np_comp:
                    price_changes.append({
                        "id": mid,
                        "name": np.get("name", mid),
                        "old_prompt": op_prompt,
                        "new_prompt": np_prompt,
                        "old_comp": op_comp,
                        "new_comp": np_comp,
                    })
            except Exception:
                pass
        
        if added or removed or price_changes:
            diff_lines = [f"### OpenRouter Model & Pricing Updates ({len(models)} models tracked)"]
            if added:
                diff_lines.append(f"- **New models added ({len(added)}):** " + ", ".join(sorted(list(added))[:10]) + ("..." if len(added) > 10 else ""))
            if removed:
                diff_lines.append(f"- **Models removed ({len(removed)}):** " + ", ".join(sorted(list(removed))[:10]) + ("..." if len(removed) > 10 else ""))
            if price_changes:
                diff_lines.append(f"- **Price changes detected ({len(price_changes)}):**")
                for pc in price_changes[:10]:
                    diff_lines.append(f"  - `{pc['id']}`: Prompt {pc['old_prompt']} -> {pc['new_prompt']} | Comp {pc['old_comp']} -> {pc['new_comp']}")
            diffs.append("\n".join(diff_lines))
except Exception as e:
    diffs.append(f"### OpenRouter Pricing Check Warning\n- Fetch failed: {e}")

# 2. Hermes docs / llms.txt
try:
    req = urllib.request.Request("https://hermes-agent.nousresearch.com/docs/llms.txt", headers={"User-Agent": "Carrier-Sonar/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        docs_bytes = resp.read()
    docs_hash = hashlib.sha256(docs_bytes).hexdigest()
    docs_text = docs_bytes.decode('utf-8', errors='ignore')
    docs_lines = [l.strip() for l in docs_text.splitlines() if l.strip()]
    sources_state["hermes_docs"] = {
        "hash": docs_hash,
        "lines_count": len(docs_lines),
    }
    old_docs = old_state.get("sources", {}).get("hermes_docs", {})
    if old_docs.get("hash") and old_docs.get("hash") != docs_hash:
        diffs.append(f"### Hermes Docs / Changelog Update\n- Docs index hash changed (`{old_docs.get('hash')[:8]}` -> `{docs_hash[:8]}`).\n- Line count: {len(docs_lines)} (was {old_docs.get('lines_count')}).")
except Exception as e:
    diffs.append(f"### Hermes Docs Check Warning\n- Fetch failed: {e}")

# 3. Hugging Face Blog Feed
try:
    import xml.etree.ElementTree as ET
    req = urllib.request.Request("https://huggingface.co/blog/feed.xml", headers={"User-Agent": "Carrier-Sonar/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        xml_data = resp.read()
    root = ET.fromstring(xml_data)
    hf_items = []
    for item in (root.findall('.//{http://www.w3.org/2005/Atom}entry') or root.findall('.//item') or root.findall('.//entry'))[:20]:
        title = (item.findtext('{http://www.w3.org/2005/Atom}title') or item.findtext('title') or "").strip()
        link = (item.findtext('{http://www.w3.org/2005/Atom}id') or item.findtext('link') or "").strip()
        updated = (item.findtext('{http://www.w3.org/2005/Atom}updated') or item.findtext('pubDate') or "").strip()
        if title:
            hf_items.append({"title": title, "link": link, "updated": updated})
    hf_hash = hashlib.sha256(json.dumps(hf_items, sort_keys=True).encode()).hexdigest()
    sources_state["huggingface_blog"] = {
        "hash": hf_hash,
        "latest_title": hf_items[0]["title"] if hf_items else "",
        "items": hf_items,
    }
    old_hf = old_state.get("sources", {}).get("huggingface_blog", {})
    if old_hf.get("hash") and old_hf.get("hash") != hf_hash:
        old_titles = {i["title"] for i in old_hf.get("items", [])}
        new_posts = [i for i in hf_items if i["title"] not in old_titles]
        hf_diff = [f"### Hugging Face AI Blog Update"]
        if new_posts:
            hf_diff.append(f"- **New posts ({len(new_posts)}):**")
            for np in new_posts[:5]:
                hf_diff.append(f"  - [{np['title']}]({np['link']})")
        else:
            hf_diff.append(f"- Feed content updated (latest: {hf_items[0]['title'] if hf_items else 'none'})")
        diffs.append("\n".join(hf_diff))
except Exception as e:
    diffs.append(f"### Hugging Face Blog Check Warning\n- Fetch failed: {e}")

# 4. OpenRouter Status
try:
    req = urllib.request.Request("https://status.openrouter.ai", headers={"User-Agent": "Carrier-Sonar/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        st_html = resp.read().decode('utf-8', errors='ignore')
    
    active_incidents = re.findall(r'\\\"activeIncidents\\\",(\[[^\]]*\])', st_html)
    scheduled = re.findall(r'\\\"scheduledMaintenance\\\",(\[[^\]]*\])', st_html)
    incidents_data = active_incidents[0] if active_incidents else "[]"
    sched_data = scheduled[0] if scheduled else "[]"
    
    st_summary = {
        "active_incidents": incidents_data,
        "scheduled_maintenance": sched_data,
    }
    st_hash = hashlib.sha256(json.dumps(st_summary, sort_keys=True).encode()).hexdigest()
    sources_state["openrouter_status"] = {
        "hash": st_hash,
        "active_incidents": incidents_data,
        "scheduled_maintenance": sched_data,
    }
    old_st = old_state.get("sources", {}).get("openrouter_status", {})
    if old_st.get("hash") and old_st.get("hash") != st_hash:
        diffs.append(f"### OpenRouter Status Change\n- Status payload changed.\n- Incidents: {incidents_data}\n- Maintenance: {sched_data}")
except Exception as e:
    diffs.append(f"### OpenRouter Status Check Warning\n- Fetch failed: {e}")

# Save new state
new_state = {
    "last_checked": now_utc,
    "sources": sources_state,
    "last_diff_detected": now_utc if (diffs or force) else old_state.get("last_diff_detected"),
}

state_json_str = json.dumps(new_state, indent=2) + "\n"
vault_state.write_text(state_json_str)
root_state.write_text(state_json_str)

if not old_state:
    print(f"SONAR BASELINE: Initial signal state established ({sources_state.get('openrouter_pricing', {}).get('models_count', 0)} models, docs indexed, feeds tracked).")
    if diff_file.exists(): diff_file.unlink()
    sys.exit(0)

if diffs or force:
    report = [
        f"# Sonar Signal Diff — {now_utc}",
        f"**Trigger:** {'Forced Weekly Digest' if force else 'Ecosystem Change Detected'}",
        "",
        "## Signals Summary",
    ]
    if diffs:
        report.extend(diffs)
    else:
        report.append("No automated diffs detected (forced digest run).")
    
    diff_text = "\n\n".join(report) + "\n"
    diff_file.write_text(diff_text)
    print(f"SONAR SIGNAL DETECTED: {len(diffs)} source diff(s) written to {diff_file_path}")
    sys.exit(1)
else:
    if diff_file.exists(): diff_file.unlink()
    sys.exit(0)
PY
