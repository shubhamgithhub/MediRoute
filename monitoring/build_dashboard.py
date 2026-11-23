#!/usr/bin/env python3
"""Generate the MediRoute CloudWatch dashboard locally."""
import argparse
import json
from pathlib import Path

REGION = "ap-southeast-2"
NAMESPACE = "MediRoute/Demo"
DAY = 86400
BLUE = "#1769e0"
TEAL = "#007c78"
PURPLE = "#7052be"
ORANGE = "#a84f00"
RED = "#b62337"
GRAY = "#5f6b7a"


def metric(name, ident, label, *, stat="Sum", color=BLUE, visible=True):
    return [NAMESPACE, name, "Environment", "dev",
            {"id": ident, "stat": stat, "label": label, "color": color, "visible": visible}]


def expression(value, ident, label, *, color=TEAL, axis="left"):
    return [{"expression": value, "id": ident, "label": label, "color": color, "yAxis": axis}]


def note(title, description, *, y, height):
    return {
        "type": "text", "x": 0, "y": y, "width": 24, "height": height,
        "properties": {"markdown": f"{title}\n\n{description}"},
    }


def widget(title, rows, *, x, y, width, height=6, period=DAY, view="timeSeries",
           start=None, settings=None):
    props = {
        "title": title, "region": REGION, "metrics": rows,
        "period": period, "view": view, "stacked": False,
    }
    if start is not None:
        props["start"] = start
    if settings:
        props.update(settings)
    return {"type": "metric", "x": x, "y": y, "width": width,
            "height": height, "properties": props}


def total_tiles(y, tiles):
    """Selected-range summaries. Daily trends use separate 24-hour buckets."""
    return [
        widget(title, [row], x=4 * index, y=y, width=4, height=4, period=300,
               view="singleValue", settings={"setPeriodToTimeRange": True, "fullPrecision": True})
        for index, (title, row) in enumerate(tiles)
    ]


def build():
    widgets = [
        note("# MediRoute operations", "Sydney · Demo environment · **Last 24 hours** by default. "
             "Daily trends use UTC. A dash indicates missing observations.", y=0, height=3),
        note("## Application status", "**1** healthy · **0** failed · **—** no recent check. "
             "In-task probes run about once a minute. App health checks the patient page and proxied API. "
             "The deployment workflow checks public HTTPS separately. This panel does not measure public uptime.",
             y=3, height=3),
    ]
    health_y = 6
    widgets += [
        widget("App · latest check", [metric("AppProbeSuccess", "app", "App", stat="Minimum", color=TEAL)],
               x=0, y=health_y, width=6, period=60, view="singleValue", start="-PT5M"),
        widget("API · latest check", [metric("ApiProbeSuccess", "api", "API", stat="Minimum", color=BLUE)],
               x=6, y=health_y, width=6, period=60, view="singleValue", start="-PT5M"),
        widget("Health check history · last 3 hours", [
            metric("AppProbeSuccess", "app", "App", stat="Minimum", color=TEAL),
            metric("ApiProbeSuccess", "api", "API", stat="Minimum", color=BLUE),
        ], x=12, y=health_y, width=12, period=60, start="-PT3H",
            settings={"yAxis": {"left": {"min": 0, "max": 1, "showUnits": False}}}),
        note("## API performance", "Number cards cover the selected range. A query is a recommendation HTTP attempt. "
             "**Retried** counts the browser's Try again action. **Failed** counts server-side failures and "
             "**Rejected** counts HTTP 4xx. Latency includes measured attempts.", y=12, height=3),
    ]
    widgets += total_tiles(15, [
        ("Queries", metric("Queries", "q", "Attempts")),
        ("Average latency (ms)", metric("QueryTimeMs", "avg", "Mean", stat="Average", color=TEAL)),
        ("p95 latency (ms)", metric("QueryTimeMs", "p95", "p95", stat="p95", color=PURPLE)),
        ("Failed", metric("QueriesFailed", "f", "Server failures", color=RED)),
        ("Retried", metric("QueriesRetried", "r", "Browser retries", color=ORANGE)),
        ("Rejected", metric("QueriesRejected", "rejected", "HTTP 4xx", color=GRAY)),
    ])
    widgets += [
        widget("Daily queries, failures, retries and rejections", [
            metric("Queries", "q", "Queries"),
            metric("QueriesFailed", "f", "Failed", color=RED),
            metric("QueriesRetried", "r", "Retried", color=ORANGE),
            metric("QueriesRejected", "rejected", "Rejected", color=GRAY),
            expression("IF(q>0,100*f/q)", "error_rate", "Server error rate (%)", color=PURPLE, axis="right"),
        ], x=0, y=19, width=12,
            settings={"yAxis": {"right": {"min": 0, "max": 100, "showUnits": False}}}),
        widget("Daily query latency · average, p50, p95 (ms)", [
            metric("QueryTimeMs", "avg", "Average", stat="Average", color=TEAL),
            metric("QueryTimeMs", "p50", "p50", stat="p50"),
            metric("QueryTimeMs", "p95", "p95", stat="p95", color=PURPLE),
        ], x=12, y=19, width=12),
        note("## LLM statistics", "One call means one OpenRouter network attempt, including retries and fallbacks. "
             "Latency is provider-call wall time. Token totals use reported input and output values. "
             "Cost is recorded provider usage and can be partial.", y=25, height=3),
    ]
    widgets += total_tiles(28, [
        ("LLM calls", metric("LLMCalls", "calls", "Attempts")),
        ("Average call time (ms)", metric("LLMCallTimeMs", "avg", "Mean", stat="Average", color=TEAL)),
        ("p95 call time (ms)", metric("LLMCallTimeMs", "p95", "p95", stat="p95", color=PURPLE)),
        ("Input tokens", metric("LLMInputTokens", "input", "Input", color=BLUE)),
        ("Output tokens", metric("LLMOutputTokens", "output", "Output", color=PURPLE)),
        ("Recorded cost (USD)", metric("LLMCostUSD", "cost", "Known cost", color=TEAL)),
    ])
    widgets += [
        widget("Daily LLM calls and failed attempts", [
            metric("LLMCalls", "calls", "Calls"),
            metric("LLMCallsFailed", "failed", "Failed calls", color=RED),
            metric("LLMCostMissing", "unknown_cost", "Calls with unknown cost", color=ORANGE),
            metric("LLMCostUSD", "samples", "Costs reported", stat="SampleCount", visible=False),
            expression("IF(calls>0,100*samples/calls)", "coverage", "Cost reporting (%)", axis="right"),
        ], x=0, y=32, width=12,
            settings={"yAxis": {"right": {"min": 0, "max": 100, "showUnits": False}}}),
        widget("Daily LLM tokens · provider-reported", [
            metric("LLMInputTokens", "input", "Input"),
            metric("LLMOutputTokens", "output", "Output", color=PURPLE),
        ], x=12, y=32, width=12),
        widget("Daily LLM response time (ms)", [
            metric("LLMCallTimeMs", "avg", "Average", stat="Average", color=TEAL),
            metric("LLMCallTimeMs", "p95", "p95", stat="p95", color=PURPLE),
        ], x=0, y=38, width=12),
        widget("Daily LLM cost (USD)", [
            metric("LLMCostUSD", "cost", "Known daily cost"),
            metric("Queries", "q", "Queries", visible=False),
            metric("LLMCalls", "calls", "Calls", visible=False),
            metric("LLMCostMissing", "missing", "Calls missing cost", visible=False),
            metric("LLMCostUSD", "samples", "Costs reported", stat="SampleCount", visible=False),
            expression("IF((q>0) AND (calls>0) AND (missing==0) AND (samples==calls),cost/q)",
                       "cost_per_query", "USD/query when cost is complete", axis="right"),
        ], x=12, y=38, width=12),
    ]
    return {"start": "-PT24H", "periodOverride": "inherit", "widgets": widgets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("mediroute-dashboard.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}.")


if __name__ == "__main__":
    main()
