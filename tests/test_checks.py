"""三表勾稽 — dict literal 构造,断言每条 check 的 passed/failed/skipped 路径。"""
from __future__ import annotations

import re

from ashare_mcp.checks import (
    ALL_CHECKS,
    DEFAULT_TOLERANCE,
    OP_DECOMP_TOLERANCE,
    check_balance_sheet_equation,
    check_cash_flow_identity,
    check_cce_period_change,
    check_operate_profit_decomp,
    detect_industry,
    run_all_checks,
)


# ---------- balance_sheet_equation ----------

def test_bs_equation_passed():
    bs = {"TOTAL_ASSETS": 1_000_000.0, "TOTAL_LIABILITIES": 600_000.0, "TOTAL_EQUITY": 400_000.0}
    r = check_balance_sheet_equation(bs, None, None)
    assert r["status"] == "passed"
    assert r["diff"] == 0.0


def test_bs_equation_failed_when_diff_above_tolerance():
    bs = {"TOTAL_ASSETS": 1_000_000.0, "TOTAL_LIABILITIES": 600_000.0, "TOTAL_EQUITY": 200_000.0}
    r = check_balance_sheet_equation(bs, None, None)
    assert r["status"] == "failed"
    assert abs(r["diff"]) > DEFAULT_TOLERANCE


def test_bs_equation_within_tolerance_still_passed():
    # 舍入差 5000 元,在 1 万元容忍度内
    bs = {"TOTAL_ASSETS": 1_000_005.0, "TOTAL_LIABILITIES": 600_000.0, "TOTAL_EQUITY": 400_000.0}
    r = check_balance_sheet_equation(bs, None, None)
    assert r["status"] == "passed"


def test_bs_equation_skipped_missing_field():
    r = check_balance_sheet_equation({"TOTAL_ASSETS": 1.0}, None, None)
    assert r["status"] == "skipped"
    assert "TOTAL_LIABILITIES" in r["reason"]
    assert "TOTAL_EQUITY" in r["reason"]


def test_bs_equation_skipped_no_balance_sheet():
    r = check_balance_sheet_equation(None, None, None)
    assert r["status"] == "skipped"


# ---------- cash_flow_identity ----------

def test_cf_identity_passed_with_fx_zero_default():
    cf = {
        "NETCASH_OPERATE": 100_000.0,
        "NETCASH_INVEST": -30_000.0,
        "NETCASH_FINANCE": -20_000.0,
        "CCE_ADD": 50_000.0,
    }
    r = check_cash_flow_identity(None, None, cf)
    assert r["status"] == "passed"


def test_cf_identity_passed_with_fx_effect():
    cf = {
        "NETCASH_OPERATE": 100_000.0,
        "NETCASH_INVEST": -30_000.0,
        "NETCASH_FINANCE": -20_000.0,
        "RATE_CHANGE_EFFECT": 2_000.0,
        "CCE_ADD": 52_000.0,
    }
    r = check_cash_flow_identity(None, None, cf)
    assert r["status"] == "passed"


def test_cf_identity_failed():
    cf = {
        "NETCASH_OPERATE": 100_000.0,
        "NETCASH_INVEST": -30_000.0,
        "NETCASH_FINANCE": -20_000.0,
        "CCE_ADD": 999_999.0,
    }
    r = check_cash_flow_identity(None, None, cf)
    assert r["status"] == "failed"


def test_cf_identity_skipped_missing_cce_add():
    cf = {"NETCASH_OPERATE": 1.0, "NETCASH_INVEST": 1.0, "NETCASH_FINANCE": 1.0}
    r = check_cash_flow_identity(None, None, cf)
    assert r["status"] == "skipped"


def test_cf_identity_skipped_missing_cf_sheet():
    assert check_cash_flow_identity(None, None, None)["status"] == "skipped"


# ---------- cce_period_change ----------

def test_cce_period_change_passed():
    cf = {"END_CCE": 500_000.0, "BEGIN_CCE": 450_000.0, "CCE_ADD": 50_000.0}
    r = check_cce_period_change(None, None, cf)
    assert r["status"] == "passed"


def test_cce_period_change_failed():
    cf = {"END_CCE": 500_000.0, "BEGIN_CCE": 100_000.0, "CCE_ADD": 50_000.0}
    r = check_cce_period_change(None, None, cf)
    assert r["status"] == "failed"


def test_cce_period_change_skipped():
    r = check_cce_period_change(None, None, {"END_CCE": 1.0})
    assert r["status"] == "skipped"


# ---------- operate_profit_decomp ----------

def test_operate_profit_decomp_industrial_passed():
    pl = {
        "TOTAL_OPERATE_INCOME": 10_000_000_000.0,
        "TOTAL_OPERATE_COST": 8_000_000_000.0,
        "OTHER_INCOME": 100_000_000.0,
        "INVEST_INCOME": 50_000_000.0,
        "OPERATE_PROFIT": 2_150_000_000.0,
    }
    r = check_operate_profit_decomp(None, pl, None)
    assert r["status"] == "passed"
    assert r["industry"] == "industrial"


def test_operate_profit_decomp_industrial_failed_above_tolerance():
    pl = {
        "TOTAL_OPERATE_INCOME": 10_000_000_000.0,
        "TOTAL_OPERATE_COST": 8_000_000_000.0,
        "OPERATE_PROFIT": 1_000_000_000.0,  # 差 10 亿,远超容忍 1000 万
    }
    r = check_operate_profit_decomp(None, pl, None)
    assert r["status"] == "failed"
    assert abs(r["diff"]) > OP_DECOMP_TOLERANCE


def test_operate_profit_decomp_bank_passed():
    bs = {"ACCEPT_DEPOSIT": 5_000_000_000_000.0}  # 5 万亿存款 -> bank
    pl = {
        "OPERATE_INCOME": 200_000_000_000.0,
        "OPERATE_EXPENSE": 120_000_000_000.0,
        "OPERATE_PROFIT": 80_000_000_000.0,
    }
    r = check_operate_profit_decomp(bs, pl, None)
    assert r["status"] == "passed"
    assert r["industry"] == "bank"


def test_operate_profit_decomp_skipped_unknown_industry():
    r = check_operate_profit_decomp(None, None, None)
    assert r["status"] == "skipped"
    assert "industry" in r["reason"]


# ---------- detect_industry ----------

def test_detect_industry_bank():
    assert detect_industry({"ACCEPT_DEPOSIT": 2_000_000_000}, None) == "bank"


def test_detect_industry_industrial():
    assert detect_industry({}, {"TOTAL_OPERATE_INCOME": 1, "TOTAL_OPERATE_COST": 1}) == "industrial"


def test_detect_industry_unknown():
    assert detect_industry({}, {}) == "unknown"


# ---------- run_all_checks aggregation ----------

def test_run_all_checks_summary_aggregates_correctly():
    # 1 passed (bs equation) + 3 skipped (cf two checks + decomp)
    bs = {"TOTAL_ASSETS": 100.0, "TOTAL_LIABILITIES": 60.0, "TOTAL_EQUITY": 40.0}
    out = run_all_checks(bs, None, None)
    assert out["summary"]["total"] == 4
    assert out["summary"]["passed"] == 1
    assert out["summary"]["skipped"] == 3
    assert out["summary"]["failed"] == 0
    names = [c["name"] for c in out["checks"]]
    assert names == [
        "balance_sheet_equation",
        "cash_flow_identity",
        "cce_period_change",
        "operate_profit_decomp",
    ]


# ---------- docstring 防漂移 ----------

def test_cross_check_docstring_count_matches_all_checks():
    """server.cross_check_balance 的 docstring 宣称的勾稽条数必须与 ALL_CHECKS 一致。
    新增/删除 check 而忘记同步 MCP docstring(LLM 唯一看到的说明书)时此测试报警。"""
    from ashare_mcp import server

    doc = server.cross_check_balance.__doc__
    assert doc, "cross_check_balance docstring missing"

    actual_total = run_all_checks(None, None, None)["summary"]["total"]
    assert actual_total == len(ALL_CHECKS)

    # 1) 文字宣称:"当前包含 N 条勾稽"
    m = re.search(r"当前包含\s*(\d+)\s*条勾稽", doc)
    assert m, "docstring 缺少 '当前包含 N 条勾稽' 宣称"
    assert int(m.group(1)) == actual_total, (
        f"docstring 宣称 {m.group(1)} 条,实际 ALL_CHECKS {actual_total} 条 — 请同步 docstring"
    )

    # 2) summary 示例:'"total": N'
    m2 = re.search(r'"total":\s*(\d+)', doc)
    assert m2, "docstring 缺少 summary total 示例"
    assert int(m2.group(1)) == actual_total

    # 3) 编号列表条数与 total 一致(行首 'N. ' 形式)
    numbered = re.findall(r"^\s+(\d+)\.\s", doc, flags=re.MULTILINE)
    assert len(numbered) == actual_total
