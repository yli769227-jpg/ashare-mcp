"""
akshare 数据源封装。
- 拉东方财富 stock_*_sheet_by_yearly_em(只拉年报,比 by_report_em 快 3-5 倍)。
- 进程内存缓存(同 stock_kind 不重复拉,冷启动一次 ~10s/sheet)。
- 字段过滤:剔除元数据列、_YOY 同比列、空(NaN)字段。数值为 0 的字段保留 —— 0 与缺失语义不同(勾稽校验 / 历史序列 / 同业对比都依赖这个区分)。
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, Dict, Optional

import akshare as ak
import pandas as pd

from .utils import get_logger

logger = get_logger(__name__)


# 元数据列(返回前剔除,LLM 不需要,且在外层 dict 已有)
_METADATA_COLS = {
    "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR", "ORG_CODE", "ORG_TYPE",
    "REPORT_DATE", "REPORT_TYPE", "REPORT_DATE_NAME", "SECURITY_TYPE_CODE",
    "NOTICE_DATE", "UPDATE_DATE", "CURRENCY", "LISTING_STATE", "OPINION_TYPE",
    "SECURITY_TYPE", "INDUSTRY_CODE", "INDUSTRY_NAME", "BOOKKEEPING_STANDARDS",
}


def _fetch_em(symbol: str, kind: str) -> pd.DataFrame:
    """kind in {'balance', 'profit', 'cash_flow'}."""
    fn = {
        "balance": ak.stock_balance_sheet_by_yearly_em,
        "profit": ak.stock_profit_sheet_by_yearly_em,
        "cash_flow": ak.stock_cash_flow_sheet_by_yearly_em,
    }[kind]
    t0 = time.monotonic()
    logger.info(f"akshare fetch start: kind={kind} symbol={symbol}")
    try:
        df = fn(symbol=symbol)
    except (ValueError, KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        # akshare 对不存在的 symbol 或上游 HTML 解析失败会抛 TypeError/AttributeError/HTTPError 等
        # 统一包成 ValueError,LLM 客户端错误处理简单且与"无数据"语义一致
        logger.warning(
            f"akshare upstream error symbol={symbol} kind={kind}: "
            f"{type(e).__name__}: {e}"
        )
        raise ValueError(
            f"akshare upstream error for symbol={symbol} kind={kind} "
            f"(invalid code or upstream issue): {type(e).__name__}: {e}"
        ) from e
    if df is None or len(df) == 0:
        raise ValueError(f"no data from akshare for symbol={symbol} kind={kind} (invalid code?)")
    elapsed = time.monotonic() - t0
    logger.info(
        f"akshare fetch done: kind={kind} symbol={symbol} "
        f"rows={len(df)} cols={len(df.columns)} elapsed={elapsed:.1f}s"
    )
    return df


# 缓存 TTL:财报数据日内基本不变,但长跑 HTTP 服务进程级 lru_cache 永不过期
# 会在公司发新报告后仍返回陈旧数据。用「时间桶」把 TTL 折进 lru_cache 的 key:
# 每过 CACHE_TTL_SECONDS 时间桶递增,旧 key 自然失效、触发重取。
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 小时


@lru_cache(maxsize=128)
def _cached_ttl(symbol: str, kind: str, time_bucket: int) -> pd.DataFrame:
    # time_bucket 仅用于让 lru_cache key 随时间滚动失效,不参与抓取逻辑。
    return _fetch_em(symbol, kind)


def _cached(symbol: str, kind: str) -> pd.DataFrame:
    """带 TTL 的进程内缓存包装。同一时间桶内命中缓存,跨桶触发重取。"""
    time_bucket = int(time.time()) // CACHE_TTL_SECONDS
    info_before = _cached_ttl.cache_info()
    df = _cached_ttl(symbol, kind, time_bucket)
    info_after = _cached_ttl.cache_info()
    if info_after.hits > info_before.hits:
        logger.info(f"cache hit: symbol={symbol} kind={kind} bucket={time_bucket}")
    else:
        logger.info(
            f"cache miss/expired -> refetch: symbol={symbol} kind={kind} "
            f"bucket={time_bucket} ttl={CACHE_TTL_SECONDS}s"
        )
    return df


# 透出底层 lru_cache 的 cache_clear,供测试 / 手动失效使用(保持旧接口不变)
_cached.cache_clear = _cached_ttl.cache_clear  # type: ignore[attr-defined]


def _to_native(val: Any) -> Any:
    if hasattr(val, "item"):
        try:
            val = val.item()
        except (AttributeError, ValueError):
            pass
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    return val


def _filter_row(row: pd.Series) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for col, val in row.items():
        if col in _METADATA_COLS:
            continue
        if col.endswith("_YOY"):
            continue
        if pd.isna(val):
            continue
        # 注意:不要剔除数值为 0 的字段 —— 0 是真实披露值,与缺失(NaN)语义不同。
        # 剔 0 会导致勾稽校验误判 skipped、history 序列出现假 None、peer_compare 排除 0 值公司。
        out[col] = _to_native(val)
    return out


def _pick_annual(df: pd.DataFrame, year: int) -> Optional[pd.Series]:
    target = f"{year}-12-31"
    mask = df["REPORT_DATE"].astype(str).str.startswith(target)
    sub = df[mask]
    if len(sub) == 0:
        return None
    return sub.iloc[0]


def _available_annual_years(df: pd.DataFrame) -> list[str]:
    dates = df["REPORT_DATE"].astype(str)
    annual = dates[dates.str.contains("12-31")]
    return sorted({d[:4] for d in annual}, reverse=True)


def get_annual_statements(symbol: str, year: int) -> Dict[str, Any]:
    """
    拉某只 A 股某年的年报三大表(报告期 12-31)。

    Args:
        symbol: 已归一化的代码,如 'SZ000001'。
        year: 年份,如 2024。

    Returns:
        包含 stock_code / company_name / report_date / currency / unit /
        balance_sheet / income_statement / cash_flow_statement 的 dict。

    Raises:
        ValueError: 找不到该年的年报数据。
    """
    bs = _cached(symbol, "balance")
    pl = _cached(symbol, "profit")
    cf = _cached(symbol, "cash_flow")

    bs_row = _pick_annual(bs, year)
    pl_row = _pick_annual(pl, year)
    cf_row = _pick_annual(cf, year)

    if bs_row is None and pl_row is None and cf_row is None:
        avail = _available_annual_years(bs)
        raise ValueError(
            f"no annual data found for {symbol} year={year}. "
            f"available annual years (top 10): {avail[:10]}"
        )

    company_name = None
    for r in (bs_row, pl_row, cf_row):
        if r is not None:
            v = r.get("SECURITY_NAME_ABBR")
            if v and not pd.isna(v):
                company_name = v
                break

    return {
        "stock_code": symbol,
        "company_name": company_name,
        "report_date": f"{year}-12-31",
        "currency": "CNY",
        "unit": "yuan (元)",
        "balance_sheet": _filter_row(bs_row) if bs_row is not None else None,
        "income_statement": _filter_row(pl_row) if pl_row is not None else None,
        "cash_flow_statement": _filter_row(cf_row) if cf_row is not None else None,
    }
