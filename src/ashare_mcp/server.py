"""
ashare-mcp: 把 A 股财报变成 LLM 可调的 MCP 工具。
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .data_source import get_annual_statements
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


def main() -> None:
    logger.info("ashare-mcp server starting (stdio transport)")
    mcp.run()


if __name__ == "__main__":
    main()
