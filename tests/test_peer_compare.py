"""peer_compare: monkeypatch get_annual_statements,验证排名/统计/fallback/errors。"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from ashare_mcp import peer_compare


def _fake_statements(
    company_name: str,
    total_assets: float,
    parent_netprofit: float,
    total_equity: float,
    netcash_operate: float = 1.0,
    total_operate_income: float | None = None,
    operate_income: float | None = None,
) -> Dict[str, Any]:
    bs: Dict[str, Any] = {
        "TOTAL_ASSETS": total_assets,
        "TOTAL_EQUITY": total_equity,
    }
    pl: Dict[str, Any] = {
        "PARENT_NETPROFIT": parent_netprofit,
    }
    if total_operate_income is not None:
        pl["TOTAL_OPERATE_INCOME"] = total_operate_income
    if operate_income is not None:
        pl["OPERATE_INCOME"] = operate_income
    cf: Dict[str, Any] = {"NETCASH_OPERATE": netcash_operate}
    return {
        "stock_code": "SZTEST",
        "company_name": company_name,
        "report_date": "2024-12-31",
        "balance_sheet": bs,
        "income_statement": pl,
        "cash_flow_statement": cf,
    }


# 全局 fake: 按 (symbol, year) 返回 fixture。
# 测试间可替换。
_FIXTURE: Dict[tuple[str, int], Dict[str, Any]] = {}


def _fake_get(symbol: str, year: int) -> Dict[str, Any]:
    key = (symbol, year)
    if key not in _FIXTURE:
        raise ValueError(f"no fixture for {key}")
    return _FIXTURE[key]


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(peer_compare, "get_annual_statements", _fake_get)
    _FIXTURE.clear()
    yield
    _FIXTURE.clear()


def test_compare_peers_normal_three_companies():
    _FIXTURE[("SZ000001", 2024)] = _fake_statements("平安银行", 5e12, 4e11, 4e11, total_operate_income=1.6e11)
    _FIXTURE[("SH600036", 2024)] = _fake_statements("招商银行", 1e13, 1.4e12, 9e11, total_operate_income=3.4e11)
    _FIXTURE[("SH601398", 2024)] = _fake_statements("工商银行", 4e13, 3.6e12, 3e12, total_operate_income=8.4e11)
    # 给 ROE_avg 用的去年权益
    _FIXTURE[("SZ000001", 2023)] = _fake_statements("平安银行", 5e12, 3e11, 3.5e11, total_operate_income=1.5e11)
    _FIXTURE[("SH600036", 2023)] = _fake_statements("招商银行", 9e12, 1.3e12, 8e11, total_operate_income=3.3e11)
    _FIXTURE[("SH601398", 2023)] = _fake_statements("工商银行", 3.8e13, 3.5e12, 2.8e12, total_operate_income=8.3e11)

    out = peer_compare.compare_peers_impl(["000001", "600036", "601398"], 2024)

    assert out["year"] == 2024
    assert len(out["companies"]) == 3
    assert out["errors"] == []
    # 顺序按输入还原
    assert [c["stock_code"] for c in out["companies"]] == ["SZ000001", "SH600036", "SH601398"]

    # 排名:TOTAL_ASSETS 工商>招商>平安
    by_code = {c["stock_code"]: c for c in out["companies"]}
    assert by_code["SH601398"]["ranks"]["TOTAL_ASSETS"] == 1
    assert by_code["SH600036"]["ranks"]["TOTAL_ASSETS"] == 2
    assert by_code["SZ000001"]["ranks"]["TOTAL_ASSETS"] == 3

    # ROE 派生且 avg_equity
    for c in out["companies"]:
        assert c["values"]["ROE"] is not None
        assert c["roe_method"] == "avg_equity"

    # summary
    assert out["summary"]["TOTAL_ASSETS"]["count"] == 3
    assert out["summary"]["TOTAL_ASSETS"]["max"] == 4e13
    assert "ROE" in out["summary"]


def test_compare_peers_single_company_fails_recorded_in_errors():
    _FIXTURE[("SZ000001", 2024)] = _fake_statements("平安", 1e12, 1e11, 1e11, total_operate_income=1e11)
    _FIXTURE[("SZ000001", 2023)] = _fake_statements("平安", 9e11, 9e10, 9e10, total_operate_income=9e10)
    # 600036 不放 fixture -> fake_get 抛 ValueError -> 进 errors

    out = peer_compare.compare_peers_impl(["000001", "600036"], 2024)
    assert len(out["companies"]) == 1
    assert len(out["errors"]) == 1
    err = out["errors"][0]
    assert err["stock_code"] == "600036"
    assert "ValueError" in err["error"]


def test_compare_peers_invalid_code_recorded_in_errors_without_fetching():
    _FIXTURE[("SZ000001", 2024)] = _fake_statements("平安", 1e12, 1e11, 1e11, total_operate_income=1e11)
    _FIXTURE[("SZ000001", 2023)] = _fake_statements("平安", 9e11, 9e10, 9e10, total_operate_income=9e10)

    out = peer_compare.compare_peers_impl(["000001", "BAD"], 2024)
    assert any(e["stock_code"] == "BAD" and "ValueError" in e["error"] for e in out["errors"])
    assert len(out["companies"]) == 1


def test_compare_peers_roe_fallback_ending_equity_when_prev_unavailable():
    _FIXTURE[("SZ000001", 2024)] = _fake_statements("平安", 5e12, 4e11, 4e11, total_operate_income=1.6e11)
    # 不放 2023 fixture -> 去年权益 None -> ending_equity_fallback
    out = peer_compare.compare_peers_impl(["000001"], 2024)
    c = out["companies"][0]
    assert c["roe_method"] == "ending_equity_fallback"
    # ROE = 4e11 / 4e11 = 1.0
    assert c["values"]["ROE"] == pytest.approx(1.0)


def test_compare_peers_bank_total_operate_income_fallback_to_operate_income():
    # 不给 TOTAL_OPERATE_INCOME,只给 OPERATE_INCOME(银行场景)
    _FIXTURE[("SZ000001", 2024)] = _fake_statements(
        "平安银行", 5e12, 4e11, 4e11, operate_income=1.6e11,
    )
    _FIXTURE[("SZ000001", 2023)] = _fake_statements(
        "平安银行", 4.8e12, 3.8e11, 3.6e11, operate_income=1.5e11,
    )

    out = peer_compare.compare_peers_impl(["000001"], 2024)
    c = out["companies"][0]
    assert c["values"]["TOTAL_OPERATE_INCOME"] == 1.6e11
    assert c["fallbacks"] == {"TOTAL_OPERATE_INCOME": "OPERATE_INCOME"}


def test_compare_peers_empty_list_raises():
    with pytest.raises(ValueError):
        peer_compare.compare_peers_impl([], 2024)


def test_compare_peers_custom_metrics_only_those_appear_plus_roe():
    _FIXTURE[("SZ000001", 2024)] = _fake_statements("平安", 1e12, 1e11, 1e11, total_operate_income=1e11)
    _FIXTURE[("SZ000001", 2023)] = _fake_statements("平安", 9e11, 9e10, 9e10, total_operate_income=9e10)

    out = peer_compare.compare_peers_impl(["000001"], 2024, metrics=["TOTAL_ASSETS"])
    assert out["metrics"] == ["TOTAL_ASSETS", "ROE"]
    c = out["companies"][0]
    assert "TOTAL_ASSETS" in c["values"]
    # 没有 PARENT_NETPROFIT/TOTAL_EQUITY 在 metrics 里 -> values 里也没有
    assert "TOTAL_OPERATE_INCOME" not in c["values"]
