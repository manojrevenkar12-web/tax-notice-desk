"""Apply config/gates.yaml to an evaluation report."""

from __future__ import annotations

from typing import Any

from .. import config


def decide(report: dict[str, Any]) -> dict[str, Any]:
    gates = config.load("gates")["gates"]
    rows, failed = [], []
    for metric, limit in gates.items():
        v = report["metrics"].get(metric)
        if v is None:
            status = "no cases"
        elif "min" in limit:
            status = "pass" if v >= limit["min"] else "fail"
        else:
            status = "pass" if v <= limit["max"] else "fail"
        if status == "fail":
            failed.append(metric)
        rows.append({"metric": metric, "value": v, "limit": limit, "status": status})
    return {"split": report["split"], "ship": not failed, "failed": failed, "checks": rows}


def render(d: dict[str, Any], report: dict[str, Any]) -> str:
    lines = [f"# Release decision on `{d['split']}` ({report['notices']} notices)", "",
             f"**{'Ships' if d['ship'] else 'Does not ship'}.**" + (f" Failed: {', '.join(d['failed'])}." if d["failed"] else ""),
             "", "| Gate | Value | Limit | Result |", "|---|---|---|---|"]
    for r in d["checks"]:
        lim = f"≥ {r['limit']['min']}" if "min" in r["limit"] else f"≤ {r['limit']['max']}"
        lines.append(f"| {r['metric']} | {r['value']} | {lim} | {r['status']} |")
    lines += ["", f"Model calls {report.get('model_calls', 0)}, cost ${report.get('model_cost_usd', 0)}; "
              f"{report['seconds']} s for {report['notices']} notices."]
    return "\n".join(lines) + "\n"
