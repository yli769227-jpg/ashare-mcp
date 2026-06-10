"""data_source._filter_row / get_annual_statements:0 值保留语义(0 != 缺失)。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ashare_mcp import data_source
from ashare_mcp.checks import run_all_checks
from ashare_mcp.data_source import _filter_row, get_annual_statements


def test_filter_row_keeps_zero_drops_nan_metadata_yoy():
    row = pd.Series(
        {
            "TOTAL_ASSETS": 1_000_000.0,
            "RATE_CHANGE_EFFECT": 0.0,          # 真实为 0 的字段必须保留
            "GOODWILL": 0,                       # int 0 同样保留
            "INVENTORY": np.nan,                 # NaN 剔除
            "SECUCODE": "000001.SZ",             # 元数据剔除
            "TOTAL_ASSETS_YOY": 5.2,             # _YOY 列剔除
        }
    )
    out = _filter_row(row)
    assert out["RATE_CHANGE_EFFECT"] == 0.0
    assert out["GOODWILL"] == 0
    assert out["TOTAL_ASSETS"] == 1_000_000.0
    assert "INVENTORY" not in out
    assert "SECUCODE" not in out
    assert "TOTAL_ASSETS_YOY" not in out


def _df_one_year(row: dict) -> pd.DataFrame:
    rec = {"REPORT_DATE": "2024-12-31 00:00:00", "SECURITY_NAME_ABBR": "测试公司"}
    rec.update(row)
    return pd.DataFrame([rec])


def test_cross_check_passes_when_field_is_truly_zero(monkeypatch):
    """CCE_ADD 真实为 0(三大现金流恰好相抵)时,勾稽必须 passed 而不是 skipped。"""
    bs_df = _df_one_year(
        {"TOTAL_ASSETS": 1_000_000.0, "TOTAL_LIABILITIES": 600_000.0, "TOTAL_EQUITY": 400_000.0}
    )
    pl_df = _df_one_year({"NETPROFIT": 1.0})
    cf_df = _df_one_year(
        {
            "NETCASH_OPERATE": 50_000.0,
            "NETCASH_INVEST": -30_000.0,
            "NETCASH_FINANCE": -20_000.0,
            "CCE_ADD": 0.0,           # 0 值字段:旧实现会被剔掉导致 skipped
            "END_CCE": 100_000.0,
            "BEGIN_CCE": 100_000.0,
        }
    )

    def fake_fetch(symbol, kind):
        return {"balance": bs_df, "profit": pl_df, "cash_flow": cf_df}[kind]

    monkeypatch.setattr(data_source, "_fetch_em", fake_fetch)
    data_source._cached.cache_clear()
    try:
        stmts = get_annual_statements("SZ000001", 2024)
        assert stmts["cash_flow_statement"]["CCE_ADD"] == 0.0

        out = run_all_checks(
            stmts["balance_sheet"],
            stmts["income_statement"],
            stmts["cash_flow_statement"],
        )
        by_name = {c["name"]: c for c in out["checks"]}
        assert by_name["cash_flow_identity"]["status"] == "passed"
        assert by_name["cce_period_change"]["status"] == "passed"
        assert by_name["balance_sheet_equation"]["status"] == "passed"
    finally:
        data_source._cached.cache_clear()


def test_check_passed_directly_with_zero_field():
    """checks 层直接喂 0 值:0 参与计算,不进 missing_fields。"""
    cf = {
        "NETCASH_OPERATE": 0.0,   # 经营现金流真实为 0
        "NETCASH_INVEST": -30_000.0,
        "NETCASH_FINANCE": 30_000.0,
        "CCE_ADD": 0.0,
    }
    out = run_all_checks(None, None, cf)
    by_name = {c["name"]: c for c in out["checks"]}
    assert by_name["cash_flow_identity"]["status"] == "passed"
