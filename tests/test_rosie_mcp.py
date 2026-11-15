"""MCP clients launch stdio servers from arbitrary working directories."""
import pytest

pytest.importorskip("mcp")


def test_default_history_path_is_repo_relative_not_cwd_relative(tmp_path, monkeypatch):
    import rosie_mcp
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_ask(question, bankroll=0., history_file="", **_):
        seen["history"] = history_file
        return {}

    monkeypatch.setattr("rosie_query.ask_game", fake_ask)
    rosie_mcp.ask_rosie("Cavs vs Mavs tonight")
    from pathlib import Path
    assert Path(seen["history"]).is_absolute()
    assert Path(seen["history"]) == Path(rosie_mcp.__file__).resolve().parent / "data" / "nba_history.csv"


def test_absolute_paths_are_preserved(tmp_path):
    import rosie_mcp
    target = str(tmp_path / "h.csv")
    assert rosie_mcp._resolve(target) == target
    assert rosie_mcp._resolve("") == ""


def test_stake_cap_tool_reports_one_percent_ceiling():
    import rosie_mcp
    out = rosie_mcp.stake_cap(500)
    assert out["max_per_position_usd"] == 5.0 and out["applies_only_when"] == "REVIEW"
