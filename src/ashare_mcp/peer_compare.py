"""
同业横向对比。

- 并发拉取 N 家公司年报(ThreadPoolExecutor + lru cache 线程安全)。
- 默认 metric 集合行业通用(银行 + 工商企业 + 制造业都有意义)。
- 自动 fallback:TOTAL_OPERATE_INCOME 缺失时退到 OPERATE_INCOME(银行场景)。
- 派生指标 ROE = PARENT_NETPROFIT / TOTAL_EQUITY(期末权益简化版)。
- 单家失败不挂整个 tool,记入 errors 字段。
"""
from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from .data_source import get_annual_statements
from .utils import get_logger, normalize_stock_code

logger = get_logger(__name__)

DEFAULT_METRICS = [
    "TOTAL_ASSETS",
    "TOTAL_OPERATE_INCOME",
    "PARENT_NETPROFIT",
    "NETCASH_OPERATE",
    "TOTAL_EQUITY",
]

# 某些字段在某行业缺失时的 fallback(如银行业没有 TOTAL_OPERATE_INCOME)
FALLBACK_MAP = {
    "TOTAL_OPERATE_INCOME": "OPERATE_INCOME",
}


def _find_metric(stmts: dict, key: str) -> tuple[Optional[float], Optional[str]]:
    """三表里找 metric,支持 fallback。返回 (value, used_key)。"""
    keys_to_try = [key]
    if key in FALLBACK_MAP:
        keys_to_try.append(FALLBACK_MAP[key])
    for try_key in keys_to_try:
        for sheet_name in ("balance_sheet", "income_statement", "cash_flow_statement"):
            sheet = stmts.get(sheet_name) or {}
            if try_key in sheet and sheet[try_key] is not None:
                return float(sheet[try_key]), try_key
    return None, None


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _get_prev_equity(symbol: str, year: int) -> Optional[float]:
    """拉去年同期权益(为算 ROE_avg 用)。失败返回 None,不挂主流程。"""
    try:
        prev = get_annual_statements(symbol, year - 1)
        prev_bs = prev.get("balance_sheet") or {}
        return prev_bs.get("TOTAL_PARENT_EQUITY") or prev_bs.get("TOTAL_EQUITY")
    except Exception as e:
        logger.info(f"prev-year equity unavailable for {symbol} year={year-1}: {e}")
        return None


def _compute_one(symbol: str, year: int, metrics: List[str]) -> Dict[str, Any]:
    """拉一家公司 → 提取 metrics + 派生 ROE_avg(失败降级到 ROE_ending)。"""
    stmts = get_annual_statements(symbol, year)
    values: Dict[str, Any] = {}
    fallbacks: Dict[str, str] = {}
    for m in metrics:
        v, used = _find_metric(stmts, m)
        values[m] = v
        if used and used != m:
            fallbacks[m] = used

    pnp = values.get("PARENT_NETPROFIT")
    eq_end = values.get("TOTAL_EQUITY")

    # ROE: 默认平均权益(本年 + 去年期末权益的均值),失败降级到期末权益
    prev_eq = _get_prev_equity(symbol, year)
    roe_method: str
    if pnp is not None and eq_end is not None and prev_eq is not None and (eq_end + prev_eq) > 0:
        values["ROE"] = pnp / ((eq_end + prev_eq) / 2)
        roe_method = "avg_equity"
    else:
        values["ROE"] = _safe_div(pnp, eq_end)
        roe_method = "ending_equity_fallback" if prev_eq is None else "avg_equity_failed"

    return {
        "stock_code": symbol,
        "company_name": stmts.get("company_name"),
        "values": values,
        "roe_method": roe_method,
        "fallbacks": fallbacks if fallbacks else None,
    }


def compare_peers_impl(
    stock_codes: List[str],
    year: int,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not stock_codes:
        raise ValueError("stock_codes is empty")

    metrics = list(metrics) if metrics else list(DEFAULT_METRICS)

    # 归一化代码,无效代码进 errors,不参与拉取
    normalized: List[tuple[str, str]] = []
    errors: List[Dict[str, Any]] = []
    for code in stock_codes:
        try:
            normalized.append((code, normalize_stock_code(code)))
        except ValueError as e:
            errors.append({"stock_code": code, "error": f"ValueError: {e}"})

    companies: List[Dict[str, Any]] = []
    if normalized:
        logger.info(
            f"compare_peers: parallel fetch {len(normalized)} companies year={year} metrics={metrics}"
        )
        with ThreadPoolExecutor(max_workers=min(8, len(normalized))) as ex:
            futures = {
                ex.submit(_compute_one, sym, year, metrics): (orig, sym)
                for orig, sym in normalized
            }
            for fut in as_completed(futures):
                orig, sym = futures[fut]
                try:
                    companies.append(fut.result())
                except Exception as e:
                    logger.warning(f"compare_peers: {sym} failed: {type(e).__name__}: {e}")
                    errors.append({"stock_code": orig, "error": f"{type(e).__name__}: {e}"})

    # 按用户输入顺序还原
    order = {sym: i for i, (_, sym) in enumerate(normalized)}
    companies.sort(key=lambda c: order.get(c["stock_code"], 9999))

    all_metrics = metrics + ["ROE"]

    # summary: max / min / avg / std / count(只统计非空值)
    summary: Dict[str, Any] = {}
    for m in all_metrics:
        vals = [c["values"].get(m) for c in companies if c["values"].get(m) is not None]
        if not vals:
            continue
        summary[m] = {
            "max": max(vals),
            "min": min(vals),
            "avg": sum(vals) / len(vals),
            "std": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "count": len(vals),
        }

    # ranks: 每个 metric 从大到小排,rank=1 最大;value 缺失则 rank=None
    for m in all_metrics:
        valid = [(i, c["values"].get(m)) for i, c in enumerate(companies)]
        valid = [(i, v) for i, v in valid if v is not None]
        valid.sort(key=lambda x: x[1], reverse=True)
        rank_map = {i: rank + 1 for rank, (i, _) in enumerate(valid)}
        for i, c in enumerate(companies):
            c.setdefault("ranks", {})[m] = rank_map.get(i)

    return {
        "year": year,
        "report_date": f"{year}-12-31",
        "metrics": all_metrics,
        "companies": companies,
        "summary": summary,
        "errors": errors,
    }
