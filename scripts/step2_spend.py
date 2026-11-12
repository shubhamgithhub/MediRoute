"""Total OpenRouter spend of the Step 2 overnight run (capability judge + grader), in USD."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "evaluation"
total = 0.0
for name in ("step2_llm_capability_cache.jsonl", "step2_grader_calls.jsonl"):
    path = ROOT / name
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                total += float(json.loads(line).get("cost") or 0)
            except Exception:
                pass
print(f"{total:.4f}")
if len(sys.argv) > 1 and total >= float(sys.argv[1]):
    sys.exit(1)
