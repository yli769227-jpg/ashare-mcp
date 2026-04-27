"""
财务报表勾稽校验。

每条 check 是一个独立函数,接收 (bs, pl, cf) 三个 dict,
返回一个 CheckResult dict 或 None(不适用 / 字段全缺)。

设计原则:
- 行业通用 — 不假设是银行还是工商企业,字段缺就 skip,不 fail。
- 容忍度 — 财报小数舍入很常见,差额 < tolerance 视为 PASS。
- 信号清晰 — passed / failed / skipped 三态,前端能据此着色。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# 默认容忍度:1 万元(财报最小披露精度通常是万元或元)
DEFAULT_TOLERANCE = 10_000.0

# 营业利润分解的容忍度:1000 万元(EM 数据多项加总的舍入累积可达百万级)
OP_DECOMP_TOLERANCE = 10_000_000.0


def detect_industry(bs: Optional[Dict[str, Any]], pl: Optional[Dict[str, Any]]) -> str:
    """
    判断公司行业类型 — 决定走哪条营业利润分解公式。

    返回 'bank' / 'industrial' / 'unknown'。

    判断规则:
      - 有 ACCEPT_DEPOSIT(吸收存款)且 > 10 亿 → bank
      - 有 TOTAL_OPERATE_INCOME 且 TOTAL_OPERATE_COST → industrial
      - 否则 unknown(保险等其他金融机构暂不支持)
    """
    if bs and (bs.get("ACCEPT_DEPOSIT") or 0) > 1_000_000_000:
        return "bank"
    if pl and "TOTAL_OPERATE_INCOME" in pl and "TOTAL_OPERATE_COST" in pl:
        return "industrial"
    return "unknown"


def _make_result(
    name: str,
    label: str,
    formula: str,
    lhs_value: Optional[float],
    rhs_value: Optional[float],
    tolerance: float = DEFAULT_TOLERANCE,
    missing_fields: Optional[list[str]] = None,
) -> Dict[str, Any]:
    if missing_fields:
        return {
            "name": name,
            "label": label,
            "formula": formula,
            "status": "skipped",
            "reason": f"missing fields: {missing_fields}",
        }
    diff = (lhs_value or 0.0) - (rhs_value or 0.0)
    passed = abs(diff) <= tolerance
    return {
        "name": name,
        "label": label,
        "formula": formula,
        "lhs_value": lhs_value,
        "rhs_value": rhs_value,
        "diff": diff,
        "tolerance": tolerance,
        "status": "passed" if passed else "failed",
    }


def _pick(d: Optional[Dict[str, Any]], *keys: str) -> tuple[Optional[float], list[str]]:
    """从 dict 里取多个字段;返回 (求和, 缺失字段列表)。任一缺失即累计为缺失,但已存在的部分仍参与求和。"""
    if d is None:
        return None, list(keys)
    total = 0.0
    missing: list[str] = []
    found_any = False
    for k in keys:
        v = d.get(k)
        if v is None:
            missing.append(k)
        else:
            total += float(v)
            found_any = True
    if not found_any:
        return None, missing
    return total, missing


def check_balance_sheet_equation(
    bs: Optional[Dict[str, Any]],
    pl: Optional[Dict[str, Any]],
    cf: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """资产负债平衡:TOTAL_ASSETS = TOTAL_LIABILITIES + TOTAL_EQUITY。"""
    name = "balance_sheet_equation"
    label = "资产负债平衡"
    formula = "TOTAL_ASSETS = TOTAL_LIABILITIES + TOTAL_EQUITY"

    if bs is None:
        return _make_result(name, label, formula, None, None, missing_fields=["balance_sheet"])

    ta = bs.get("TOTAL_ASSETS")
    tl = bs.get("TOTAL_LIABILITIES")
    te = bs.get("TOTAL_EQUITY")
    missing = [k for k, v in [("TOTAL_ASSETS", ta), ("TOTAL_LIABILITIES", tl), ("TOTAL_EQUITY", te)] if v is None]
    if missing:
        return _make_result(name, label, formula, None, None, missing_fields=missing)
    return _make_result(name, label, formula, float(ta), float(tl) + float(te))


def check_cash_flow_identity(
    bs: Optional[Dict[str, Any]],
    pl: Optional[Dict[str, Any]],
    cf: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """现金流恒等式:NETCASH_OPERATE + NETCASH_INVEST + NETCASH_FINANCE + RATE_CHANGE_EFFECT = CCE_ADD。"""
    name = "cash_flow_identity"
    label = "三大现金流之和 = 现金净增加额"
    formula = "NETCASH_OPERATE + NETCASH_INVEST + NETCASH_FINANCE + RATE_CHANGE_EFFECT = CCE_ADD"

    if cf is None:
        return _make_result(name, label, formula, None, None, missing_fields=["cash_flow_statement"])

    cce_add = cf.get("CCE_ADD")
    if cce_add is None:
        return _make_result(name, label, formula, None, None, missing_fields=["CCE_ADD"])

    # RATE_CHANGE_EFFECT 缺失时按 0 处理(汇率影响为零是合理状态)
    op = cf.get("NETCASH_OPERATE")
    inv = cf.get("NETCASH_INVEST")
    fin = cf.get("NETCASH_FINANCE")
    fx = cf.get("RATE_CHANGE_EFFECT") or 0.0

    missing = [k for k, v in [("NETCASH_OPERATE", op), ("NETCASH_INVEST", inv), ("NETCASH_FINANCE", fin)] if v is None]
    if missing:
        return _make_result(name, label, formula, None, None, missing_fields=missing)

    return _make_result(name, label, formula, float(op) + float(inv) + float(fin) + float(fx), float(cce_add))


def check_cce_period_change(
    bs: Optional[Dict[str, Any]],
    pl: Optional[Dict[str, Any]],
    cf: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """期末现金 = 期初现金 + 现金净增加额(END_CCE - BEGIN_CCE = CCE_ADD)。"""
    name = "cce_period_change"
    label = "期末现金 - 期初现金 = 现金净增加额"
    formula = "END_CCE - BEGIN_CCE = CCE_ADD"

    if cf is None:
        return _make_result(name, label, formula, None, None, missing_fields=["cash_flow_statement"])

    end = cf.get("END_CCE")
    begin = cf.get("BEGIN_CCE")
    cce_add = cf.get("CCE_ADD")
    missing = [k for k, v in [("END_CCE", end), ("BEGIN_CCE", begin), ("CCE_ADD", cce_add)] if v is None]
    if missing:
        return _make_result(name, label, formula, None, None, missing_fields=missing)

    return _make_result(name, label, formula, float(end) - float(begin), float(cce_add))


def check_operate_profit_decomp(
    bs: Optional[Dict[str, Any]],
    pl: Optional[Dict[str, Any]],
    cf: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    营业利润分解 — 行业感知。

    银行:OPERATE_PROFIT = OPERATE_INCOME - OPERATE_EXPENSE
    工商企业:OPERATE_PROFIT = TOTAL_OPERATE_INCOME - TOTAL_OPERATE_COST
                            + OTHER_INCOME + INVEST_INCOME
                            + FAIRVALUE_CHANGE_INCOME
                            + ASSET_IMPAIRMENT_INCOME + CREDIT_IMPAIRMENT_INCOME
                            + ASSET_DISPOSAL_INCOME [+ EXCHANGE_INCOME]
    """
    name = "operate_profit_decomp"
    label = "营业利润分解(行业感知)"
    industry = detect_industry(bs, pl)

    if industry == "unknown":
        return {
            "name": name,
            "label": label,
            "formula": "industry-aware (bank / industrial)",
            "status": "skipped",
            "reason": "unable to detect industry (need ACCEPT_DEPOSIT for bank, or TOTAL_OPERATE_INCOME+TOTAL_OPERATE_COST for industrial)",
        }

    if industry == "bank":
        formula = "[bank] OPERATE_PROFIT = OPERATE_INCOME - OPERATE_EXPENSE"
        op_inc = (pl or {}).get("OPERATE_INCOME")
        op_exp = (pl or {}).get("OPERATE_EXPENSE")
        op_pf = (pl or {}).get("OPERATE_PROFIT")
        missing = [
            k for k, v in [("OPERATE_INCOME", op_inc), ("OPERATE_EXPENSE", op_exp), ("OPERATE_PROFIT", op_pf)]
            if v is None
        ]
        if missing:
            return _make_result(name, label, formula, None, None, missing_fields=missing)
        result = _make_result(
            name, label, formula,
            float(op_inc) - float(op_exp), float(op_pf),
            tolerance=OP_DECOMP_TOLERANCE,
        )
        result["industry"] = "bank"
        return result

    # industrial
    formula = (
        "[industrial] OPERATE_PROFIT = TOTAL_OPERATE_INCOME - TOTAL_OPERATE_COST "
        "+ OTHER_INCOME + INVEST_INCOME + FAIRVALUE_CHANGE_INCOME "
        "+ ASSET_IMPAIRMENT_INCOME + CREDIT_IMPAIRMENT_INCOME "
        "+ ASSET_DISPOSAL_INCOME [+ EXCHANGE_INCOME]"
    )
    toi = (pl or {}).get("TOTAL_OPERATE_INCOME")
    toc = (pl or {}).get("TOTAL_OPERATE_COST")
    op_pf = (pl or {}).get("OPERATE_PROFIT")
    missing = [
        k for k, v in [("TOTAL_OPERATE_INCOME", toi), ("TOTAL_OPERATE_COST", toc), ("OPERATE_PROFIT", op_pf)]
        if v is None
    ]
    if missing:
        return _make_result(name, label, formula, None, None, missing_fields=missing)

    addend_keys = [
        "OTHER_INCOME",
        "INVEST_INCOME",
        "FAIRVALUE_CHANGE_INCOME",
        "ASSET_IMPAIRMENT_INCOME",
        "CREDIT_IMPAIRMENT_INCOME",
        "ASSET_DISPOSAL_INCOME",
        "EXCHANGE_INCOME",
    ]
    addend_sum = sum(float((pl or {}).get(k) or 0) for k in addend_keys)
    lhs = float(toi) - float(toc) + addend_sum
    result = _make_result(name, label, formula, lhs, float(op_pf), tolerance=OP_DECOMP_TOLERANCE)
    result["industry"] = "industrial"
    return result


# 注册全部 checks(顺序即输出顺序)
ALL_CHECKS = [
    check_balance_sheet_equation,
    check_cash_flow_identity,
    check_cce_period_change,
    check_operate_profit_decomp,
]


def run_all_checks(
    bs: Optional[Dict[str, Any]],
    pl: Optional[Dict[str, Any]],
    cf: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    results = [fn(bs, pl, cf) for fn in ALL_CHECKS]
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
    }
    return {"checks": results, "summary": summary}
