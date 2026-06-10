"""
公司历史时间序列工具(v2 P0 底座)。

- 复用 data_source._cached:同一公司全年份的三表已 lru_cache,跨年份查询零成本。
- 同业 fallback:银行业 TOTAL_OPERATE_INCOME 自动退到 OPERATE_INCOME。
- 输出 series / yoy / cagr / stats / anomalies,后续杜邦分析 / 利润质量 / 红旗扫描皆基于此。
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from .checks import detect_industry
from .data_source import (
    _available_annual_years,
    _cached,
    _filter_row,
    _pick_annual,
)
from .security import validate_ticker
from .utils import get_logger, normalize_stock_code

logger = get_logger(__name__)


DEFAULT_METRICS: List[str] = [
    # 营收
    "TOTAL_OPERATE_INCOME",   # 银行业 fallback OPERATE_INCOME
    # 利润
    "PARENT_NETPROFIT",
    "NETPROFIT",
    "OPERATE_PROFIT",
    # 资产
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
    # 现金流
    "NETCASH_OPERATE",
    "NETCASH_INVEST",
    "NETCASH_FINANCE",
    # 红旗预备(后续 red_flag_scan 用,但底座先把数据备齐)
    "ACCOUNTS_RECE",
    "INVENTORY",
    "GOODWILL",
]

FALLBACK_MAP: Dict[str, str] = {
    "TOTAL_OPERATE_INCOME": "OPERATE_INCOME",
}

# YoY 突变阈值(±30%)
ANOMALY_THRESHOLD = 0.30
# 上限保护:akshare 最多给 ~10-15 年
MAX_YEARS = 20

# YoY 序列里某一年值类型:数值 / None / "from_negative"
YoYItem = Union[float, str, None]


def _find_metric_in_year(
    bs: Optional[Dict[str, Any]],
    pl: Optional[Dict[str, Any]],
    cf: Optional[Dict[str, Any]],
    key: str,
) -> Tuple[Optional[float], Optional[str]]:
    """
    在某一年的三表里查找 metric,支持 fallback。

    优先级:balance_sheet -> income_statement -> cash_flow_statement。
    返回 (value, used_key)。值缺失返回 (None, None)。
    """
    keys_to_try = [key]
    if key in FALLBACK_MAP:
        keys_to_try.append(FALLBACK_MAP[key])
    for try_key in keys_to_try:
        for sheet in (bs, pl, cf):
            if sheet and try_key in sheet and sheet[try_key] is not None:
                try:
                    return float(sheet[try_key]), try_key
                except (TypeError, ValueError):
                    continue
    return None, None


def _compute_yoy(series: List[Optional[float]]) -> List[YoYItem]:
    """
    按年序计算 YoY,长度与输入序列相同(第 0 项恒为 None)。

    规则:
      - 当年或上一年缺失 -> None
      - 上一年值 <= 0   -> "from_negative"(LLM 自行解释)
      - 否则           -> (cur - prev) / prev
    """
    out: List[YoYItem] = [None]
    for i in range(1, len(series)):
        prev = series[i - 1]
        cur = series[i]
        if prev is None or cur is None:
            out.append(None)
            continue
        if prev <= 0:
            out.append("from_negative")
            continue
        out.append((cur - prev) / prev)
    return out


def _compute_cagr(series: List[Optional[float]]) -> Optional[float]:
    """首末非空且首值 > 0 时计算 CAGR。否则 None。"""
    n = len(series)
    if n < 2:
        return None
    start = series[0]
    end = series[-1]
    if start is None or end is None:
        return None
    if start <= 0 or end <= 0:
        return None
    try:
        return (end / start) ** (1.0 / (n - 1)) - 1.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _compute_stats(series: List[Optional[float]], yoy: List[YoYItem]) -> Dict[str, Any]:
    """mean / std 基于 series 的非空值;trend 基于 yoy 中纯数值的符号。"""
    nums = [v for v in series if v is not None]
    if nums:
        mean = sum(nums) / len(nums)
        std = statistics.stdev(nums) if len(nums) > 1 else 0.0
    else:
        mean = None
        std = None

    yoy_nums: List[float] = [v for v in yoy if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(yoy_nums) < 2:
        trend = "insufficient_data"
    elif all(v >= 0 for v in yoy_nums):
        trend = "up"
    elif all(v <= 0 for v in yoy_nums):
        trend = "down"
    else:
        trend = "volatile"

    return {"mean": mean, "std": std, "trend": trend}


def _detect_anomalies(
    years: List[int],
    metric: str,
    yoy: List[YoYItem],
) -> List[Dict[str, Any]]:
    """yoy 是数值且 |yoy| > ANOMALY_THRESHOLD 时记一条。"""
    out: List[Dict[str, Any]] = []
    for year, v in zip(years, yoy):
        if isinstance(v, bool):
            continue
        if not isinstance(v, (int, float)):
            continue
        if math.isnan(v):
            continue
        if abs(v) > ANOMALY_THRESHOLD:
            note = "突变上升" if v > 0 else "突变下滑"
            out.append({"year": year, "metric": metric, "yoy": v, "note": note})
    return out


def _extract_year_statements(
    bs_df: pd.DataFrame,
    pl_df: pd.DataFrame,
    cf_df: pd.DataFrame,
    year: int,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    """
    提取某年三表(已过滤元数据/空值/零值/_YOY 列)和公司名。

    返回 (balance_sheet, income_statement, cash_flow_statement, company_name)。
    任一行缺失即在该位置返回 None。
    """
    bs_row = _pick_annual(bs_df, year)
    pl_row = _pick_annual(pl_df, year)
    cf_row = _pick_annual(cf_df, year)

    bs = _filter_row(bs_row) if bs_row is not None else None
    pl = _filter_row(pl_row) if pl_row is not None else None
    cf = _filter_row(cf_row) if cf_row is not None else None

    company_name = None
    for r in (bs_row, pl_row, cf_row):
        if r is not None:
            v = r.get("SECURITY_NAME_ABBR")
            if v is not None and not pd.isna(v):
                company_name = v
                break

    return bs, pl, cf, company_name


def track_company_history_impl(
    stock_code: str,
    years: int = 5,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    拉取某公司最近 N 年的多 metric 时间序列并计算 YoY / CAGR / stats / anomalies。

    Args:
        stock_code: A 股代码,任意常见格式。
        years: 想要的年份数(默认 5)。> 20 自动截到 20。
        metrics: 自定义 metric 列表;不传走 DEFAULT_METRICS。

    Returns:
        见模块顶部 docstring 描述的 schema。

    Raises:
        ValueError: years <= 0,或公司一年都没有年报数据。
    """
    if years <= 0:
        raise ValueError(f"years must be positive, got {years}")
    if years > MAX_YEARS:
        logger.info(f"years={years} clamped to MAX_YEARS={MAX_YEARS}")
        years = MAX_YEARS

    metric_keys: List[str] = list(metrics) if metrics else list(DEFAULT_METRICS)
    # 形态白名单(拦注入字符 / path-traversal) → 再交易所归一化
    symbol = normalize_stock_code(validate_ticker(stock_code))

    logger.info(
        f"track_company_history start: symbol={symbol} years={years} metrics={len(metric_keys)}"
    )

    # 1. 拉全量历史三表(lru_cache 命中则零成本)
    bs_df = _cached(symbol, "balance")
    pl_df = _cached(symbol, "profit")
    cf_df = _cached(symbol, "cash_flow")

    # 2. 取可用年份并截到最近 N 个,递增排序
    avail_desc = _available_annual_years(bs_df)  # ["2024","2023",...]
    if not avail_desc:
        raise ValueError(f"no annual data found for {symbol}")
    avail_int_desc = [int(y) for y in avail_desc]
    picked_desc = avail_int_desc[:years]
    picked_years = sorted(picked_desc)  # 递增:最早 -> 最近
    # missing_years:用户请求超过实际可用时,缺失年份 = 最近年-(years-1) 起到最近年里、不在 picked 里的
    if avail_int_desc and len(picked_years) < years:
        most_recent = avail_int_desc[0]
        wanted = list(range(most_recent - years + 1, most_recent + 1))
        missing_years = sorted(set(wanted) - set(picked_years))
    else:
        missing_years = []

    logger.info(f"available years: {avail_desc[:10]}, picked: {picked_years}")

    # 3. 提取每年三表
    per_year: Dict[int, Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = {}
    company_name: Optional[str] = None
    industry: str = "unknown"
    industry_detected = False

    for y in picked_years:
        bs, pl, cf, cname = _extract_year_statements(bs_df, pl_df, cf_df, y)
        per_year[y] = (bs, pl, cf)
        if company_name is None and cname:
            company_name = cname
        # 第一个非空年的三表跑 detect_industry
        if not industry_detected and (bs is not None or pl is not None):
            industry = detect_industry(bs, pl)
            industry_detected = True
            logger.info(f"industry detected: {industry}")

    if not industry_detected:
        # 三表都没有 — 已被前面 ValueError 兜住,但兜底
        raise ValueError(f"no annual data extractable for {symbol}, picked_years={picked_years}")

    report_dates = [f"{y}-12-31" for y in picked_years]

    # 4. 对每个 metric 组成时间序列 + 记录 fallback
    series: Dict[str, List[Optional[float]]] = {}
    fallbacks: Dict[str, str] = {}
    for m in metric_keys:
        vals: List[Optional[float]] = []
        used_per_year: List[Optional[str]] = []
        for y in picked_years:
            bs, pl, cf = per_year[y]
            v, used = _find_metric_in_year(bs, pl, cf, m)
            vals.append(v)
            used_per_year.append(used)
        series[m] = vals
        # 如果任何一年用了 fallback 的 key,记入 fallbacks(以最常见的非原 key 为准)
        non_orig = [u for u in used_per_year if u is not None and u != m]
        if non_orig:
            # 用首个出现的 fallback key
            fallbacks[m] = non_orig[0]

    # 5. yoy / cagr / stats / anomalies
    yoy: Dict[str, List[YoYItem]] = {}
    cagr: Dict[str, Optional[float]] = {}
    stats: Dict[str, Dict[str, Any]] = {}
    anomalies: List[Dict[str, Any]] = []

    for m in metric_keys:
        s = series[m]
        y_seq = _compute_yoy(s)
        yoy[m] = y_seq
        cagr[m] = _compute_cagr(s)
        stats[m] = _compute_stats(s, y_seq)
        anomalies.extend(_detect_anomalies(picked_years, m, y_seq))

    logger.info(
        f"track_company_history done: years={len(picked_years)} "
        f"anomalies={len(anomalies)} fallbacks={list(fallbacks.keys())}"
    )

    return {
        "stock_code": symbol,
        "company_name": company_name,
        "industry": industry,
        "years": picked_years,
        "report_dates": report_dates,
        "missing_years": missing_years,
        "series": series,
        "fallbacks": fallbacks if fallbacks else {},
        "yoy": yoy,
        "cagr": cagr,
        "stats": stats,
        "anomalies": anomalies,
    }
