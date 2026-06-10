"""history: monkeypatch _cached 返回 DataFrame,测 YoY/CAGR/trend/anomalies/fallbacks。"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from ashare_mcp import history


def _make_df(years: List[int], rows: List[Dict[str, float]]) -> pd.DataFrame:
    """构造 akshare 风格的年报 DataFrame —— 必须有 REPORT_DATE 列(date 字符串)。"""
    assert len(years) == len(rows)
    records = []
    for y, row in zip(years, rows):
        rec = {"REPORT_DATE": f"{y}-12-31 00:00:00", "SECURITY_NAME_AB BR": ""}
        rec["SECURITY_NAME_ABBR"] = row.pop("_name", "测试公司")
        rec.update(row)
        records.append(rec)
    # 模拟 akshare 返回:倒序(最近年在前)
    records.sort(key=lambda r: r["REPORT_DATE"], reverse=True)
    return pd.DataFrame(records)


# 5 年工商企业 fixture:营收逐年增长,利润 2022 突变下滑
INDUSTRIAL_BS = _make_df(
    [2020, 2021, 2022, 2023, 2024],
    [
        {"TOTAL_ASSETS": 1.0e10, "TOTAL_EQUITY": 4.0e9, "TOTAL_LIABILITIES": 6.0e9, "_name": "测试工业"},
        {"TOTAL_ASSETS": 1.1e10, "TOTAL_EQUITY": 4.4e9, "TOTAL_LIABILITIES": 6.6e9, "_name": "测试工业"},
        {"TOTAL_ASSETS": 1.2e10, "TOTAL_EQUITY": 4.5e9, "TOTAL_LIABILITIES": 7.5e9, "_name": "测试工业"},
        {"TOTAL_ASSETS": 1.3e10, "TOTAL_EQUITY": 5.0e9, "TOTAL_LIABILITIES": 8.0e9, "_name": "测试工业"},
        {"TOTAL_ASSETS": 1.5e10, "TOTAL_EQUITY": 5.8e9, "TOTAL_LIABILITIES": 9.2e9, "_name": "测试工业"},
    ],
)

INDUSTRIAL_PL = _make_df(
    [2020, 2021, 2022, 2023, 2024],
    [
        {"TOTAL_OPERATE_INCOME": 5.0e9, "TOTAL_OPERATE_COST": 4.0e9, "PARENT_NETPROFIT": 5.0e8, "NETPROFIT": 5.0e8, "OPERATE_PROFIT": 1.0e9, "_name": "测试工业"},
        {"TOTAL_OPERATE_INCOME": 5.5e9, "TOTAL_OPERATE_COST": 4.4e9, "PARENT_NETPROFIT": 5.5e8, "NETPROFIT": 5.5e8, "OPERATE_PROFIT": 1.1e9, "_name": "测试工业"},
        # 2022 利润突变下滑 -50%
        {"TOTAL_OPERATE_INCOME": 6.0e9, "TOTAL_OPERATE_COST": 5.4e9, "PARENT_NETPROFIT": 2.75e8, "NETPROFIT": 2.75e8, "OPERATE_PROFIT": 6.0e8, "_name": "测试工业"},
        {"TOTAL_OPERATE_INCOME": 6.5e9, "TOTAL_OPERATE_COST": 5.6e9, "PARENT_NETPROFIT": 4.0e8, "NETPROFIT": 4.0e8, "OPERATE_PROFIT": 9.0e8, "_name": "测试工业"},
        {"TOTAL_OPERATE_INCOME": 7.0e9, "TOTAL_OPERATE_COST": 6.0e9, "PARENT_NETPROFIT": 5.0e8, "NETPROFIT": 5.0e8, "OPERATE_PROFIT": 1.0e9, "_name": "测试工业"},
    ],
)

INDUSTRIAL_CF = _make_df(
    [2020, 2021, 2022, 2023, 2024],
    [
        {"NETCASH_OPERATE": 8.0e8, "NETCASH_INVEST": -5.0e8, "NETCASH_FINANCE": -1.0e8, "_name": "测试工业"},
        {"NETCASH_OPERATE": 9.0e8, "NETCASH_INVEST": -5.0e8, "NETCASH_FINANCE": -1.0e8, "_name": "测试工业"},
        {"NETCASH_OPERATE": 7.0e8, "NETCASH_INVEST": -5.0e8, "NETCASH_FINANCE": -2.0e8, "_name": "测试工业"},
        {"NETCASH_OPERATE": 8.5e8, "NETCASH_INVEST": -4.5e8, "NETCASH_FINANCE": -2.0e8, "_name": "测试工业"},
        {"NETCASH_OPERATE": 1.0e9, "NETCASH_INVEST": -5.0e8, "NETCASH_FINANCE": -2.0e8, "_name": "测试工业"},
    ],
)


# 银行 fixture:无 TOTAL_OPERATE_INCOME,只有 OPERATE_INCOME(测 fallback)
BANK_BS = _make_df(
    [2022, 2023, 2024],
    [
        {"TOTAL_ASSETS": 5.0e12, "TOTAL_EQUITY": 4.0e11, "TOTAL_LIABILITIES": 4.6e12, "ACCEPT_DEPOSIT": 3.0e12, "_name": "测试银行"},
        {"TOTAL_ASSETS": 5.3e12, "TOTAL_EQUITY": 4.3e11, "TOTAL_LIABILITIES": 4.87e12, "ACCEPT_DEPOSIT": 3.2e12, "_name": "测试银行"},
        {"TOTAL_ASSETS": 5.7e12, "TOTAL_EQUITY": 4.6e11, "TOTAL_LIABILITIES": 5.24e12, "ACCEPT_DEPOSIT": 3.4e12, "_name": "测试银行"},
    ],
)

BANK_PL = _make_df(
    [2022, 2023, 2024],
    [
        {"OPERATE_INCOME": 1.5e11, "PARENT_NETPROFIT": 4.0e10, "NETPROFIT": 4.0e10, "OPERATE_PROFIT": 5.0e10, "_name": "测试银行"},
        {"OPERATE_INCOME": 1.6e11, "PARENT_NETPROFIT": 4.5e10, "NETPROFIT": 4.5e10, "OPERATE_PROFIT": 5.5e10, "_name": "测试银行"},
        {"OPERATE_INCOME": 1.65e11, "PARENT_NETPROFIT": 4.6e10, "NETPROFIT": 4.6e10, "OPERATE_PROFIT": 5.6e10, "_name": "测试银行"},
    ],
)

BANK_CF = _make_df(
    [2022, 2023, 2024],
    [
        {"NETCASH_OPERATE": 5.0e10, "NETCASH_INVEST": -2.0e10, "NETCASH_FINANCE": -1.0e10, "_name": "测试银行"},
        {"NETCASH_OPERATE": 5.5e10, "NETCASH_INVEST": -2.2e10, "NETCASH_FINANCE": -1.1e10, "_name": "测试银行"},
        {"NETCASH_OPERATE": 6.0e10, "NETCASH_INVEST": -2.4e10, "NETCASH_FINANCE": -1.2e10, "_name": "测试银行"},
    ],
)


def _patch_industrial(monkeypatch):
    def fake(symbol, kind):
        return {"balance": INDUSTRIAL_BS, "profit": INDUSTRIAL_PL, "cash_flow": INDUSTRIAL_CF}[kind]
    monkeypatch.setattr(history, "_cached", fake)


def _patch_bank(monkeypatch):
    def fake(symbol, kind):
        return {"balance": BANK_BS, "profit": BANK_PL, "cash_flow": BANK_CF}[kind]
    monkeypatch.setattr(history, "_cached", fake)


def test_history_industrial_basic_shape(monkeypatch):
    _patch_industrial(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    assert out["stock_code"] == "SZ000001"
    assert out["company_name"] == "测试工业"
    assert out["industry"] == "industrial"
    assert out["years"] == [2020, 2021, 2022, 2023, 2024]
    assert out["report_dates"] == [
        "2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31",
    ]
    assert out["missing_years"] == []


def test_history_yoy_first_is_none_and_values_correct(monkeypatch):
    _patch_industrial(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    yoy = out["yoy"]["TOTAL_OPERATE_INCOME"]
    assert yoy[0] is None
    assert yoy[1] == pytest.approx(0.10)   # 5.0 -> 5.5
    assert yoy[2] == pytest.approx((6.0 - 5.5) / 5.5)
    # 利润 2022 -50% 突变
    pnp_yoy = out["yoy"]["PARENT_NETPROFIT"]
    assert pnp_yoy[2] == pytest.approx(-0.5)


def test_history_anomalies_detected(monkeypatch):
    _patch_industrial(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    # PARENT_NETPROFIT 2022 -50% > 30% 阈值
    found = [a for a in out["anomalies"] if a["metric"] == "PARENT_NETPROFIT" and a["year"] == 2022]
    assert len(found) == 1
    assert found[0]["yoy"] == pytest.approx(-0.5)
    assert found[0]["note"] == "突变下滑"


def test_history_cagr_correct(monkeypatch):
    _patch_industrial(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    # TOTAL_OPERATE_INCOME 5.0e9 -> 7.0e9, n=5, periods=4
    expected = (7.0e9 / 5.0e9) ** (1.0 / 4.0) - 1.0
    assert out["cagr"]["TOTAL_OPERATE_INCOME"] == pytest.approx(expected)


def test_history_stats_trend_up(monkeypatch):
    _patch_industrial(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    # 营收逐年增长 -> trend up
    assert out["stats"]["TOTAL_OPERATE_INCOME"]["trend"] == "up"
    # 利润 2022 跌、其他年涨 -> volatile
    assert out["stats"]["PARENT_NETPROFIT"]["trend"] == "volatile"


def test_history_bank_fallback(monkeypatch):
    _patch_bank(monkeypatch)
    out = history.track_company_history_impl("000001", years=3)
    assert out["industry"] == "bank"
    # TOTAL_OPERATE_INCOME 没数据 -> 走 fallback OPERATE_INCOME
    assert out["fallbacks"].get("TOTAL_OPERATE_INCOME") == "OPERATE_INCOME"
    assert out["series"]["TOTAL_OPERATE_INCOME"] == [1.5e11, 1.6e11, 1.65e11]


def test_history_missing_years_when_request_more_than_available(monkeypatch):
    _patch_bank(monkeypatch)  # 只有 3 年
    out = history.track_company_history_impl("000001", years=5)
    # 实际只能拿到 3 年(2022/2023/2024),用户要 5 年 -> 缺 2020/2021
    assert out["years"] == [2022, 2023, 2024]
    assert out["missing_years"] == [2020, 2021]


# 缺 2023 的工商企业 fixture(2020/2021/2022/2024,中间缺口)
GAP_BS = _make_df(
    [2020, 2021, 2022, 2024],
    [
        {"TOTAL_ASSETS": 1.0e10, "TOTAL_EQUITY": 4.0e9, "TOTAL_LIABILITIES": 6.0e9, "_name": "缺口公司"},
        {"TOTAL_ASSETS": 1.1e10, "TOTAL_EQUITY": 4.4e9, "TOTAL_LIABILITIES": 6.6e9, "_name": "缺口公司"},
        {"TOTAL_ASSETS": 1.2e10, "TOTAL_EQUITY": 4.5e9, "TOTAL_LIABILITIES": 7.5e9, "_name": "缺口公司"},
        {"TOTAL_ASSETS": 1.5e10, "TOTAL_EQUITY": 5.8e9, "TOTAL_LIABILITIES": 9.2e9, "_name": "缺口公司"},
    ],
)

GAP_PL = _make_df(
    [2020, 2021, 2022, 2024],
    [
        {"TOTAL_OPERATE_INCOME": 5.0e9, "TOTAL_OPERATE_COST": 4.0e9, "PARENT_NETPROFIT": 5.0e8, "_name": "缺口公司"},
        {"TOTAL_OPERATE_INCOME": 5.5e9, "TOTAL_OPERATE_COST": 4.4e9, "PARENT_NETPROFIT": 5.5e8, "_name": "缺口公司"},
        {"TOTAL_OPERATE_INCOME": 6.0e9, "TOTAL_OPERATE_COST": 5.4e9, "PARENT_NETPROFIT": 6.0e8, "_name": "缺口公司"},
        {"TOTAL_OPERATE_INCOME": 8.0e9, "TOTAL_OPERATE_COST": 6.0e9, "PARENT_NETPROFIT": 8.0e8, "_name": "缺口公司"},
    ],
)

GAP_CF = _make_df(
    [2020, 2021, 2022, 2024],
    [
        {"NETCASH_OPERATE": 8.0e8, "_name": "缺口公司"},
        {"NETCASH_OPERATE": 9.0e8, "_name": "缺口公司"},
        {"NETCASH_OPERATE": 7.0e8, "_name": "缺口公司"},
        {"NETCASH_OPERATE": 1.0e9, "_name": "缺口公司"},
    ],
)


def _patch_gap(monkeypatch):
    def fake(symbol, kind):
        return {"balance": GAP_BS, "profit": GAP_PL, "cash_flow": GAP_CF}[kind]
    monkeypatch.setattr(history, "_cached", fake)


def test_history_gap_year_yoy_is_none_not_fake_growth(monkeypatch):
    """缺 2023 时,2024 相对 2022 的两年涨幅不能当 YoY,必须为 None。"""
    _patch_gap(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    assert out["years"] == [2020, 2021, 2022, 2024]
    yoy = out["yoy"]["TOTAL_OPERATE_INCOME"]
    assert yoy[0] is None
    assert yoy[1] == pytest.approx(0.10)              # 2020 -> 2021 连续
    assert yoy[2] == pytest.approx((6.0 - 5.5) / 5.5)  # 2021 -> 2022 连续
    assert yoy[3] is None                              # 2022 -> 2024 跨缺口


def test_history_gap_year_reported_in_missing_years(monkeypatch):
    """即使 picked 数量满足请求,中间缺口也必须出现在 missing_years。"""
    _patch_gap(monkeypatch)
    out = history.track_company_history_impl("000001", years=4)
    assert out["years"] == [2020, 2021, 2022, 2024]
    assert 2023 in out["missing_years"]


def test_history_gap_year_cagr_uses_year_span(monkeypatch):
    """CAGR 指数 = 1/(末年 - 首年) = 1/4,而不是 1/(数据点数-1) = 1/3。"""
    _patch_gap(monkeypatch)
    out = history.track_company_history_impl("000001", years=5)
    expected = (8.0e9 / 5.0e9) ** (1.0 / (2024 - 2020)) - 1.0
    assert out["cagr"]["TOTAL_OPERATE_INCOME"] == pytest.approx(expected)


def test_history_years_zero_raises(monkeypatch):
    _patch_industrial(monkeypatch)
    with pytest.raises(ValueError):
        history.track_company_history_impl("000001", years=0)


def test_history_years_clamped_to_max(monkeypatch):
    _patch_industrial(monkeypatch)
    # 请求 100 年:不报错,只是被截到可用的 5 年
    out = history.track_company_history_impl("000001", years=100)
    assert len(out["years"]) == 5


def test_history_invalid_code_raises(monkeypatch):
    _patch_industrial(monkeypatch)
    with pytest.raises(ValueError):
        history.track_company_history_impl("BAD_CODE", years=3)
