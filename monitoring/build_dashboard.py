#!/usr/bin/env python3
"""Generate the low-cost MediRoute dashboard locally; makes no AWS calls."""
import argparse
import json
from pathlib import Path

REGION = "ap-southeast-2"
NAMESPACE = "MediRoute/Demo"


def metric(name, ident, *, stat="Sum", visible=True):
    return [NAMESPACE, name, "Environment", "dev",
            {"id": ident, "stat": stat, "visible": visible}]


def expression(value, ident, label):
    return [{"expression": value, "id": ident, "label": label}]


def build():
    widgets = [{
        "type": "text", "x": 0, "y": 0, "width": 24, "height": 4,
        "properties": {"markdown": (
            "# MediRoute — on-demand demo\n"
            "Managed by `monitoring/build_dashboard.py`. Region: Sydney. "
            "Seven custom metric series, fixed `Environment=dev`. "
            "No Container Insights, alarms, paid probes, or log-query widgets.\n\n"
            "Graphs appear only after the instrumented backend is deployed and used. "
            "Blank means no observations, not zero traffic or zero spending. "
            "Stop the task after the demonstration."
        )},
    }]

    def graph(title, metrics, *, period=3600, view="timeSeries"):
        index = len(widgets) - 1
        widgets.append({
            "type": "metric", "x": 12 * (index % 2), "y": 4 + 6 * (index // 2),
            "width": 12, "height": 6,
            "properties": {
                "title": title, "region": REGION, "view": view, "period": period,
                "metrics": metrics, "stacked": False,
            },
        })

    graph("Recommendation requests / hour", [metric("Queries", "q")])
    graph("Recommendation requests / day (UTC)", [metric("Queries", "q")], period=86400)
    graph("Server failures and rejected requests / hour",
          [metric("QueriesFailed", "f"), metric("QueriesRejected", "r")])
    graph("Server error rate (%) — excludes 4xx rejections",
          [metric("Queries", "q", visible=False), metric("QueriesFailed", "f", visible=False),
           expression("IF(q>0,100*f/q)", "rate", "Server failure rate (%)")])
    graph("Response time — p50 and p95 (ms)",
          [metric("QueryTimeMs", "median", stat="p50"), metric("QueryTimeMs", "tail", stat="p95")])
    graph("Known OpenRouter cost / day (USD; may be partial)",
          [metric("LLMCostUSD", "cost")], period=86400)
    graph("Observed LLM USD / query — complete-cost windows only",
          [metric("Queries", "q", visible=False),
           metric("LLMCalls", "calls", visible=False),
           metric("LLMCostMissing", "missing", visible=False),
           metric("LLMCostUSD", "cost", visible=False),
           metric("LLMCostUSD", "samples", stat="SampleCount", visible=False),
           expression("IF((q>0) AND (calls>0) AND (missing==0) AND (samples==calls),cost/q)",
                      "cost_per_query", "Observed USD/query")])
    graph("LLM calls and calls with unknown cost / hour",
          [metric("LLMCalls", "calls"), metric("LLMCostMissing", "missing")])
    graph("Provider cost coverage (%)",
          [metric("LLMCalls", "calls", visible=False),
           metric("LLMCostUSD", "samples", stat="SampleCount", visible=False),
           expression("IF(calls>0,100*samples/calls)", "coverage", "Calls with reported cost (%)")])
    graph("Requests in selected range",
          [metric("Queries", "q"), metric("QueriesFailed", "f"), metric("QueriesRejected", "r")],
          view="singleValue")
    # singleValue should aggregate the selected time range, not show the last bucket.
    widgets[-1]["properties"]["setPeriodToTimeRange"] = True
    widgets.append({
        "type": "text", "x": 0, "y": 34, "width": 24, "height": 6,
        "properties": {"markdown": (
            "## Interpretation and intentionally disabled collection\n"
            "- A query is one POST to patient-routing, analyze, hospitals/recommend, or "
            "hospitals/semantic-recommendations. Follow-up submissions count separately.\n"
            "- Cost is provider-confirmed usage from each OpenRouter network attempt, including "
            "retries. Missing cost is unknown. Known daily cost may understate actual charges. "
            "USD/query compares totals in the same hourly window; it is not per-request billing.\n"
            "- **CPU/memory: not collected. Container Insights remains disabled.**\n"
            "- **Uptime: not measured.** Planned demo shutdowns are not outages. A future independent "
            "probe must run only during agreed demo windows. Request success is not uptime.\n"
            "- OpenRouter spending is separate from your AWS bill. No patient data is included "
            "in these metric events."
        )},
    })
    return {"start": "-P7D", "periodOverride": "inherit", "widgets": widgets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("mediroute-dashboard.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}. No AWS changes made.")


if __name__ == "__main__":
    main()
