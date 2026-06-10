"""
同业横向对比。

- 并发拉取 N 家公司年报(ThreadPoolExecutor + lru cache 线程安全)。
- 默认 metric 集合行业通用(银行 + 工商企业 + 制造业都有意义)。
- 自动 fallback:TOTAL_OPERATE_INCOME 缺失时退到 OPERATE_INCOME(银行场景)。
- 派生指标 ROE = PARENT_NETPROFIT / 平均权益((本年期末 + 上年期末) / 2)。
  权益口径两年一致:优先 TOTAL_PARENT_EQUITY(与分子归母净利润同口径),缺失时 fallback TOTAL_EQUITY;
  上年数据拉不到时降级为期末权益。实际方法 / 口径见每家公司的 roe_method / roe_equity_basis 字段:
    roe_method ∈ {avg_equity, ending_equity_fallback, avg_equity_failed}
    roe_equity_basis ∈ {TOTAL_PARENT_EQUITY, TOTAL_EQUITY, None}。
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

# 单次对比的公司数上限。每家公司要打 3 次上游接口(三表),
# 不设上限时公开 HTTP 部署可被单个请求放大成数千次上游抓取。
MAX_STOCK_CODES = 20

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


# ROE 分母权益口径,按优先级:归母权益(与分子 PARENT_NETPROFIT 匹配)> 总权益
_EQUITY_BASIS_KEYS = ("TOTAL_PARENT_EQUITY", "TOTAL_EQUITY")


def _get_prev_balance_sheet(symbol: str, year: int) -> Optional[Dict[str, Any]]:
    """拉去年同期资产负债表(为算 ROE_avg 用)。失败返回 None,不挂主流程。"""
    try:
        prev = get_annual_statements(symbol, year - 1)
        return prev.get("balance_sheet") or {}
    except Exception as e:
        logger.info(f"prev-year balance sheet unavailable for {symbol} year={year-1}: {e}")
        return None


def _pick_equity(bs: Dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    """按 _EQUITY_BASIS_KEYS 优先级取期末权益。注意用 is None 判断,0 是合法值。"""
    for key in _EQUITY_BASIS_KEYS:
        v = bs.get(key)
        if v is not None:
            try:
                return float(v), key
            except (TypeError, ValueError):
                continue
    return None, None


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
    cur_bs = stmts.get("balance_sheet") or {}

    # ROE: 默认平均权益(本年 + 去年期末权益的均值),失败降级到期末权益。
    # 权益口径两年必须一致:优先 TOTAL_PARENT_EQUITY(与分子 PARENT_NETPROFIT 同口径),
    # 任一年缺失则两年一致地 fallback 到 TOTAL_EQUITY。实际口径写入 roe_equity_basis。
    prev_bs = _get_prev_balance_sheet(symbol, year)
    roe_method: str
    roe_equity_basis: Optional[str] = None

    basis_key: Optional[str] = None
    if prev_bs is not None:
        for key in _EQUITY_BASIS_KEYS:
            if cur_bs.get(key) is not None and prev_bs.get(key) is not None:
                basis_key = key
                break

    eq_cur: Optional[float] = None
    eq_prev: Optional[float] = None
    if basis_key is not None:
        try:
            eq_cur = float(cur_bs[basis_key])
            eq_prev = float(prev_bs[basis_key])
        except (TypeError, ValueError):
            eq_cur = eq_prev = None

    if pnp is not None and eq_cur is not None and eq_prev is not None and (eq_cur + eq_prev) > 0:
        values["ROE"] = pnp / ((eq_cur + eq_prev) / 2)
        roe_method = "avg_equity"
        roe_equity_basis = basis_key
    else:
        eq_end, end_key = _pick_equity(cur_bs)
        values["ROE"] = _safe_div(pnp, eq_end)
        roe_equity_basis = end_key if values["ROE"] is not None else None
        # prev_bs 拉不到 / 两年没有一致口径 → ending_equity_fallback;
        # 口径找到了但分子缺失或权益和 <= 0 → avg_equity_failed
        roe_method = "ending_equity_fallback" if basis_key is None else "avg_equity_failed"

    return {
        "stock_code": symbol,
        "company_name": stmts.get("company_name"),
        "values": values,
        "roe_method": roe_method,
        "roe_equity_basis": roe_equity_basis,
        "fallbacks": fallbacks if fallbacks else None,
    }


def compare_peers_impl(
    stock_codes: List[str],
    year: int,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not stock_codes:
        raise ValueError("stock_codes is empty")
    if len(stock_codes) > MAX_STOCK_CODES:
        logger.warning(
            f"compare_peers rejected: {len(stock_codes)} stock_codes exceeds limit {MAX_STOCK_CODES}"
        )
        raise ValueError(
            f"too many stock_codes: got {len(stock_codes)}, max {MAX_STOCK_CODES}. "
            f"Please split into multiple smaller requests."
        )

    metrics = list(metrics) if metrics else list(DEFAULT_METRICS)

    # 入口去重(保持首次出现顺序):重复代码会产生重复条目并让 summary count 虚高。
    deduped: List[str] = []
    seen: set[str] = set()
    for code in stock_codes:
        if code not in seen:
            seen.add(code)
            deduped.append(code)
    if len(deduped) < len(stock_codes):
        logger.info(
            f"compare_peers: deduped stock_codes {len(stock_codes)} -> {len(deduped)}"
        )
    stock_codes = deduped

    # 归一化代码,无效代码进 errors,不参与拉取。
    # 归一化后再次去重:不同输入格式(000001 / SZ000001 / 000001.SZ)指向同一只股票,
    # 否则会产生重复 company 条目并让 summary count 虚高。
    normalized: List[tuple[str, str]] = []
    seen_sym: set[str] = set()
    errors: List[Dict[str, Any]] = []
    for code in stock_codes:
        try:
            sym = normalize_stock_code(code)
        except ValueError as e:
            errors.append({"stock_code": code, "error": f"ValueError: {e}"})
            continue
        if sym in seen_sym:
            logger.info(f"compare_peers: skip duplicate normalized symbol {sym} (from {code!r})")
            continue
        seen_sym.add(sym)
        normalized.append((code, sym))

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
