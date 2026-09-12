import importlib.util
from pathlib import Path
import sys
import types

PLUGIN = Path(__file__).parents[1]


def load_server(fetch_json):
    app = types.ModuleType("app")
    http = types.ModuleType("app.plugin_http")
    http.fetch_json = fetch_json
    sys.modules["app"] = app
    sys.modules["app.plugin_http"] = http
    spec = importlib.util.spec_from_file_location("uptime_kuma_server", PLUGIN / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_normalizes_status_page(tmp_path):
    page = {
        "config": {"title": "Homelab"},
        "incident": None,
        "maintenanceList": [],
        "publicGroupList": [{"name": "Services", "monitorList": [
            {"id": 2, "name": "Core Server", "type": "ping"},
            {"id": 17, "name": "Media Service", "type": "http"},
        ]}],
    }
    beats = {
        "heartbeatList": {
            "2": [{"status": 1, "time": "2026-09-12 04:00:00", "ping": 1.2, "msg": ""}],
            "17": [{"status": 0, "time": "2026-09-12 04:00:00", "ping": None, "msg": "timeout"}],
        },
        "uptimeList": {"2_24": 1, "17_24": 0.95},
    }

    def fake(url, **kwargs):
        return beats if "/heartbeat/" in url else page

    server = load_server(fake)
    result = server.fetch(
        {"base_url": "192.168.1.20:3001", "status_page_slug": "homelab"},
        {},
        ctx={"data_dir": str(tmp_path), "fresh": True},
    )
    assert result["label"] == "Homelab"
    assert result["slug"] == "homelab"
    assert result["operational"] is False
    assert result["counts"]["down"] == 1
    assert result["monitors"][0]["name"] == "Media Service"
    assert result["monitors"][1]["uptime_24"] == 100.0
    assert result["display_style"] == "constellation"


def test_display_style_is_per_cell_even_with_shared_cache(tmp_path):
    page = {"config": {"title": "Lab"}, "publicGroupList": []}
    beats = {"heartbeatList": {}, "uptimeList": {}}

    def fake(url, **kwargs):
        return beats if "/heartbeat/" in url else page

    server = load_server(fake)
    common = {"base_url": "http://kuma:3001", "status_page_slug": "lab"}
    server.fetch({**common, "display_style": "grid"}, {}, ctx={"data_dir": str(tmp_path), "fresh": True})
    result = server.fetch({**common, "display_style": "grafana"}, {}, ctx={"data_dir": str(tmp_path)})
    assert result["display_style"] == "grafana"


def test_custom_title_is_per_cell_even_with_shared_cache(tmp_path):
    page = {"config": {"title": "Orlando"}, "publicGroupList": []}
    beats = {"heartbeatList": {}, "uptimeList": {}}

    def fake(url, **kwargs):
        return beats if "/heartbeat/" in url else page

    server = load_server(fake)
    common = {"base_url": "http://kuma:3001", "status_page_slug": "lab"}
    first = server.fetch(
        {**common, "label": "Network One"},
        {},
        ctx={"data_dir": str(tmp_path), "fresh": True},
    )
    second = server.fetch(
        {**common, "label": "My Homelab"},
        {},
        ctx={"data_dir": str(tmp_path)},
    )
    defaulted = server.fetch(common, {}, ctx={"data_dir": str(tmp_path)})
    assert first["label"] == "Network One"
    assert second["label"] == "My Homelab"
    assert defaulted["label"] == "Orlando"


def test_dos_display_style_is_accepted(tmp_path):
    page = {"config": {"title": "Lab"}, "publicGroupList": []}
    beats = {"heartbeatList": {}, "uptimeList": {}}

    def fake(url, **kwargs):
        return beats if "/heartbeat/" in url else page

    server = load_server(fake)
    result = server.fetch(
        {"base_url": "http://kuma:3001", "status_page_slug": "lab", "display_style": "dos"},
        {},
        ctx={"data_dir": str(tmp_path), "fresh": True},
    )
    assert result["display_style"] == "dos"


def test_orbital_options_are_validated(tmp_path):
    page = {"config": {"title": "Lab"}, "publicGroupList": []}
    beats = {"heartbeatList": {}, "uptimeList": {}}

    def fake(url, **kwargs):
        return beats if "/heartbeat/" in url else page

    server = load_server(fake)
    result = server.fetch(
        {
            "base_url": "http://kuma:3001",
            "status_page_slug": "lab",
            "display_style": "orbital",
            "accent_color": "red; background:url(bad)",
            "monitor_limit": 999,
            "show_secondary_lines": "false",
        },
        {},
        ctx={"data_dir": str(tmp_path), "fresh": True},
    )
    assert result["display_style"] == "orbital"
    assert result["accent_color"] == "#9bd36e"
    assert result["monitor_limit"] == 12
    assert result["show_secondary_lines"] is False


def test_invalid_url_is_rejected(tmp_path):
    server = load_server(lambda *args, **kwargs: {})
    result = server.fetch(
        {"base_url": "file:///etc/passwd", "status_page_slug": "homelab"},
        {},
        ctx={"data_dir": str(tmp_path)},
    )
    assert "valid" in result["error"]
