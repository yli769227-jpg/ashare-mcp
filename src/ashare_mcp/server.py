"""
ashare-mcp: 把 A 股财报变成 LLM 可调的 MCP 工具。
"""
from __future__ import annotations

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from .checks import run_all_checks
from .data_source import get_annual_statements
from .peer_compare import compare_peers_impl
from .utils import get_logger, normalize_stock_code

logger = get_logger(__name__)

mcp = FastMCP("ashare-mcp")


@mcp.tool()
def get_three_statements(stock_code: str, year: int) -> dict:
    """
    拉取 A 股某只股票某年的年报三大财务报表(资产负债表 / 利润表 / 现金流量表)。

    参数:
      stock_code: A 股代码,支持多种格式 —— '000001' / 'SZ000001' / 'sz.000001' / '000001.SZ'。
      year: 年份(整数),如 2024。仅支持年报(报告期 12-31)。

    返回:
      {
        "stock_code": "SZ000001",
        "company_name": "平安银行",
        "report_date": "2024-12-31",
        "currency": "CNY",
        "unit": "yuan (元)",
        "balance_sheet": {...},        # 字段如 TOTAL_ASSETS / LOAN_ADVANCE / ACCEPT_DEPOSIT
        "income_statement": {...},      # 字段如 OPERATE_INCOME / NETPROFIT / PARENT_NETPROFIT
        "cash_flow_statement": {...},   # 字段如 NETCASH_OPERATE / NETCASH_INVEST / NETCASH_FINANCE
      }

    数据源: 东方财富(via akshare)。字段名为东方财富原始英文(SCREAMING_SNAKE_CASE)。
    单位: 人民币元。
    缓存: 进程内存缓存,同一只股票多次查询(不同年份)只走一次网络。
    """
    logger.info(f"tool=get_three_statements stock_code={stock_code!r} year={year}")
    try:
        symbol = normalize_stock_code(stock_code)
        logger.info(f"normalized: {stock_code!r} -> {symbol!r}")
        result = get_annual_statements(symbol, year)
        logger.info(
            f"returned: company={result['company_name']!r} "
            f"bs={len(result['balance_sheet'] or {})} "
            f"pl={len(result['income_statement'] or {})} "
            f"cf={len(result['cash_flow_statement'] or {})}"
        )
        return result
    except Exception as e:
        logger.exception(f"get_three_statements failed: {type(e).__name__}: {e}")
        raise


@mcp.tool()
def cross_check_balance(stock_code: str, year: int) -> dict:
    """
    跑财务勾稽校验,检测三大表数据是否互相自洽。返回每条校验的 passed/failed/skipped 状态与误差。

    参数:
      stock_code: A 股代码,支持多种格式(同 get_three_statements)。
      year: 年份,如 2024。仅支持年报。

    返回:
      {
        "stock_code": "SZ000001",
        "company_name": "平安银行",
        "report_date": "2024-12-31",
        "checks": [
          {
            "name": "balance_sheet_equation",
            "label": "资产负债平衡",
            "formula": "TOTAL_ASSETS = TOTAL_LIABILITIES + TOTAL_EQUITY",
            "lhs_value": 5769270000000.0,
            "rhs_value": 5769270000000.0,
            "diff": 0.0,
            "tolerance": 10000.0,
            "status": "passed"
          },
          ...
        ],
        "summary": {"total": 3, "passed": 3, "failed": 0, "skipped": 0}
      }

    当前 v1 包含 3 条行业通用勾稽:
      1. 资产负债平衡: TOTAL_ASSETS = TOTAL_LIABILITIES + TOTAL_EQUITY
      2. 现金流恒等式: 三大现金流 + 汇率影响 = 现金净增加额
      3. 期末/期初现金对账: END_CCE - BEGIN_CCE = CCE_ADD

    容忍度 1 万元(财报舍入)。字段缺失时该条 status='skipped',不影响其它校验。
    """
    logger.info(f"tool=cross_check_balance stock_code={stock_code!r} year={year}")
    try:
        symbol = normalize_stock_code(stock_code)
        statements = get_annual_statements(symbol, year)
        result = run_all_checks(
            statements["balance_sheet"],
            statements["income_statement"],
            statements["cash_flow_statement"],
        )
        out = {
            "stock_code": symbol,
            "company_name": statements["company_name"],
            "report_date": statements["report_date"],
            **result,
        }
        logger.info(
            f"checks: passed={out['summary']['passed']} "
            f"failed={out['summary']['failed']} skipped={out['summary']['skipped']}"
        )
        return out
    except Exception as e:
        logger.exception(f"cross_check_balance failed: {type(e).__name__}: {e}")
        raise


@mcp.tool()
def compare_peers(
    stock_codes: List[str],
    year: int,
    metrics: Optional[List[str]] = None,
) -> dict:
    """
    同业 N 家公司同年年报横向对比,自动算排名 / 最大最小 / 均值 / 标准差,加派生指标 ROE。

    参数:
      stock_codes: 公司代码列表,如 ['000001', '600036', '601398']。建议 2-10 家。
                   支持各种格式:'000001' / 'SZ000001' / 'sz.000001' / '000001.SZ'。
      year: 年份。
      metrics: 可选,自定义对比字段。默认包括:
               TOTAL_ASSETS / TOTAL_OPERATE_INCOME / PARENT_NETPROFIT / NETCASH_OPERATE / TOTAL_EQUITY。
               派生指标 ROE = PARENT_NETPROFIT / TOTAL_EQUITY 总是会算上。
               银行业 TOTAL_OPERATE_INCOME 缺失时自动 fallback 到 OPERATE_INCOME(在 fallbacks 字段里标注)。

    返回:
      {
        "year": 2024,
        "report_date": "2024-12-31",
        "metrics": ["TOTAL_ASSETS", ..., "ROE"],
        "companies": [
          {
            "stock_code": "SZ000001",
            "company_name": "平安银行",
            "values": {metric: number},
            "ranks":  {metric: rank},      # 1 = 最大
            "fallbacks": {original_key: actual_key} | null
          }
        ],
        "summary": {
          metric: {"max", "min", "avg", "std", "count"}
        },
        "errors": [
          {"stock_code": "...", "error": "..."}  # 单家失败不挂整体
        ]
      }

    并发实现: ThreadPoolExecutor(max_workers=8),N 家公司并行拉。
    缓存联动: 已经查过的公司走 lru cache,< 1ms 复用。
    """
    logger.info(f"tool=compare_peers stock_codes={stock_codes} year={year} metrics={metrics}")
    try:
        result = compare_peers_impl(stock_codes, year, metrics)
        logger.info(
            f"compare_peers done: companies={len(result['companies'])} "
            f"errors={len(result['errors'])}"
        )
        return result
    except Exception as e:
        logger.exception(f"compare_peers failed: {type(e).__name__}: {e}")
        raise


def main() -> None:
    logger.info("ashare-mcp server starting (stdio transport)")
    mcp.run()


if __name__ == "__main__":
    main()
