"""Uptime Kuma public-status-page collector for Tesserae."""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from app.plugin_http import fetch_json

CACHE_TTL_S = 60
HTTP_TIMEOUT_S = 6
USER_AGENT = "tesserae/0.1 (+uptime_kuma_incident_board)"
STATUS_NAMES = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}


def _read_cache(path: Path, *, stale: bool = False) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if not stale and time.time() - path.stat().st_mtime >= CACHE_TTL_S:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _base_url(raw: Any) -> str | None:
    value = str(raw or "").strip().rstrip("/")
    if value and "://" not in value:
        value = "http://" + value
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return value


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _boolean(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def _latest(values: Any) -> dict[str, Any]:
    if not isinstance(values, list):
        return {}
    rows = [row for row in values if isinstance(row, dict)]
    return max(rows, key=lambda row: str(row.get("time") or ""), default={})


def _uptime_24(uptime_list: Any, monitor_id: str) -> float | None:
    if not isinstance(uptime_list, dict):
        return None
    value = _number(uptime_list.get(f"{monitor_id}_24"))
    if value is None:
        return None
    # Kuma represents uptime as a ratio, but tolerate percentage-shaped data.
    percentage = value * 100 if value <= 1 else value
    return round(max(0.0, min(100.0, percentage)), 2)


def _monitors(page: dict[str, Any], heartbeats: dict[str, Any]) -> list[dict[str, Any]]:
    heartbeat_list = heartbeats.get("heartbeatList") or {}
    uptime_list = heartbeats.get("uptimeList") or {}
    result: list[dict[str, Any]] = []

    groups = page.get("publicGroupList") or []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or "")
        monitors = group.get("monitorList") or []
        for monitor in monitors if isinstance(monitors, list) else []:
            if not isinstance(monitor, dict) or monitor.get("id") is None:
                continue
            monitor_id = str(monitor["id"])
            raw_history = heartbeat_list.get(monitor_id)
            latest = _latest(raw_history)
            try:
                status_code = int(latest.get("status"))
            except (TypeError, ValueError):
                status_code = -1
            ping = _number(latest.get("ping"))
            history: list[dict[str, Any]] = []
            if isinstance(raw_history, list):
                rows = sorted(
                    (row for row in raw_history if isinstance(row, dict)),
                    key=lambda row: str(row.get("time") or ""),
                )[-24:]
                for row in rows:
                    try:
                        history_status = int(row.get("status"))
                    except (TypeError, ValueError):
                        history_status = -1
                    history_ping = _number(row.get("ping"))
                    history.append({
                        "status": STATUS_NAMES.get(history_status, "unknown"),
                        "ping": round(history_ping, 1)
                        if history_ping is not None and history_ping >= 0 else None,
                    })
            result.append(
                {
                    "id": monitor_id,
                    "name": str(monitor.get("name") or f"Monitor {monitor_id}"),
                    "group": group_name,
                    "type": str(monitor.get("type") or ""),
                    "status": STATUS_NAMES.get(status_code, "unknown"),
                    "status_code": status_code,
                    "ping": round(ping, 1) if ping is not None and ping >= 0 else None,
                    "message": str(latest.get("msg") or ""),
                    "time": str(latest.get("time") or ""),
                    "uptime_24": _uptime_24(uptime_list, monitor_id),
                    "history": history,
                }
            )

    priority = {"down": 0, "pending": 1, "maintenance": 2, "unknown": 3, "up": 4}
    result.sort(key=lambda row: (priority[row["status"]], row["name"].lower()))
    return result


def _incident(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    title = str(value.get("title") or "").strip()
    content = str(value.get("content") or value.get("description") or "").strip()
    if not title and not content:
        return None
    return {
        "title": title or "Active incident",
        "content": content,
        "style": str(value.get("style") or "warning"),
    }


def fetch(
    options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]
) -> dict[str, Any]:
    del settings
    base = _base_url(options.get("base_url"))
    slug = str(options.get("status_page_slug") or "").strip().strip("/")
    label = str(options.get("label") or "").strip()
    display_style = str(options.get("display_style") or "constellation").strip()
    if display_style not in {
        "constellation", "orbital", "grafana", "grid", "minimal", "terminal", "dos", "windows95", "windows311"
    }:
        display_style = "constellation"
    color_scheme = str(options.get("color_scheme") or "auto").strip()
    if color_scheme not in {"auto", "light", "dark"}:
        color_scheme = "auto"
    density = str(options.get("density") or "comfortable").strip()
    if density not in {"comfortable", "compact"}:
        density = "comfortable"
    show_history = _boolean(options.get("show_history"), True)
    try:
        monitor_limit = max(1, min(12, int(options.get("monitor_limit") or 8)))
    except (TypeError, ValueError):
        monitor_limit = 8
    presentation = {
        "display_style": display_style,
        "color_scheme": color_scheme,
        "density": density,
        "show_history": show_history,
        "monitor_limit": monitor_limit,
    }
    orbital_topology = str(options.get("orbital_topology") or "automatic").strip()
    if orbital_topology not in {"automatic", "star", "orbit"}:
        orbital_topology = "automatic"
    radar_background = str(options.get("radar_background") or "rings_grid").strip()
    if radar_background not in {"rings_grid", "rings", "grid", "none"}:
        radar_background = "rings_grid"
    orbital_node_size = str(options.get("orbital_node_size") or "medium").strip()
    if orbital_node_size not in {"small", "medium", "large"}:
        orbital_node_size = "medium"
    connection_thickness = str(options.get("connection_thickness") or "medium").strip()
    if connection_thickness not in {"thin", "medium", "heavy"}:
        connection_thickness = "medium"
    node_details = str(options.get("node_details") or "full").strip()
    if node_details not in {"name", "status", "full"}:
        node_details = "full"
    heartbeat_length = str(options.get("heartbeat_length") or "24").strip()
    if heartbeat_length not in {"8", "12", "24"}:
        heartbeat_length = "24"
    accent_color = str(options.get("accent_color") or "#9bd36e").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent_color):
        accent_color = "#9bd36e"
    orbital_darkness = str(options.get("orbital_darkness") or "pure_black").strip()
    if orbital_darkness not in {"standard", "pure_black"}:
        orbital_darkness = "pure_black"
    presentation.update({
        "orbital_topology": orbital_topology,
        "show_secondary_lines": _boolean(options.get("show_secondary_lines"), True),
        "relationship_overrides": str(options.get("relationship_overrides") or "")[:2000],
        "radar_background": radar_background,
        "orbital_node_size": orbital_node_size,
        "connection_thickness": connection_thickness,
        "show_signal_log": _boolean(options.get("show_signal_log"), True),
        "show_summary_metrics": _boolean(options.get("show_summary_metrics"), True),
        "node_details": node_details,
        "heartbeat_length": heartbeat_length,
        "accent_color": accent_color.lower(),
        "orbital_darkness": orbital_darkness,
    })
    if not base:
        return {"error": "Enter a valid http:// or https:// Uptime Kuma URL."}
    if not slug:
        return {"error": "Enter the slug of a published Uptime Kuma status page."}

    data_dir = Path(ctx["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{base}|{slug}".encode()).hexdigest()[:12]
    cache_path = data_dir / f"uptime-kuma-{digest}.json"
    if not ctx.get("fresh"):
        cached = _read_cache(cache_path)
        if cached is not None:
            # Presentation is per cell while the normalized Kuma payload is
            # shared by every cell targeting this status page.
            cached.update(presentation)
            cached["label"] = label or str(
                cached.get("page_title") or cached.get("label") or "Uptime Kuma"
            )
            return cached

    encoded_slug = quote(slug, safe="")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        page = fetch_json(
            f"{base}/api/status-page/{encoded_slug}",
            headers=headers,
            timeout=HTTP_TIMEOUT_S,
            retries=0,
        )
        heartbeats = fetch_json(
            f"{base}/api/status-page/heartbeat/{encoded_slug}",
            headers=headers,
            timeout=HTTP_TIMEOUT_S,
            retries=0,
        )
        if not isinstance(page, dict) or not isinstance(heartbeats, dict):
            raise ValueError("Unexpected Uptime Kuma response")
    except Exception:
        cached = _read_cache(cache_path, stale=True)
        if cached is not None:
            cached["stale"] = True
            cached.update(presentation)
            cached["label"] = label or str(
                cached.get("page_title") or cached.get("label") or "Uptime Kuma"
            )
            return cached
        return {"error": "Couldn't read that Uptime Kuma status page."}

    monitors = _monitors(page, heartbeats)
    counts = {name: 0 for name in ("up", "down", "pending", "maintenance", "unknown")}
    for monitor in monitors:
        counts[monitor["status"]] += 1

    operational = bool(monitors) and counts["down"] == counts["pending"] == counts["unknown"] == 0
    config = page.get("config") if isinstance(page.get("config"), dict) else {}
    page_title = str(config.get("title") or "Uptime Kuma")
    result = {
        "page_title": page_title,
        "slug": slug,
        "label": label or page_title,
        **presentation,
        "operational": operational,
        "counts": counts,
        "monitors": monitors,
        "incident": _incident(page.get("incident")),
        "maintenance_count": len(page.get("maintenanceList") or []),
        "updated_at": int(time.time()),
        "stale": False,
    }
    with contextlib.suppress(OSError):
        cache_path.write_text(json.dumps(result), encoding="utf-8")
    return result
