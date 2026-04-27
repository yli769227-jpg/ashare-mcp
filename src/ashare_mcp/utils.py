"""日志 + 股票代码归一化。"""
from __future__ import annotations

import logging
import sys


def get_logger(name: str = "ashare_mcp") -> logging.Logger:
    # MCP stdio 把 stdout 当协议通道,日志必须走 stderr。
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def normalize_stock_code(code: str) -> str:
    """
    把各种 A 股代码格式归一化为 'SZ000001' / 'SH600600' / 'BJ430139'。

    支持:
      '000001'       -> 'SZ000001'
      'SZ000001'     -> 'SZ000001'
      'sz000001'     -> 'SZ000001'
      'sz.000001'    -> 'SZ000001'
      '000001.SZ'    -> 'SZ000001'
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError(f"invalid stock code: {code!r}")

    s = code.strip().upper().replace(".", "").replace(" ", "")

    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            digits = s[len(prefix):]
            if digits.isdigit() and len(digits) == 6:
                return f"{prefix}{digits}"
            raise ValueError(f"invalid stock code: {code!r}")
        if s.endswith(prefix):
            digits = s[: -len(prefix)]
            if digits.isdigit() and len(digits) == 6:
                return f"{prefix}{digits}"
            raise ValueError(f"invalid stock code: {code!r}")

    if s.isdigit() and len(s) == 6:
        first = s[0]
        if first in ("0", "2", "3"):
            return f"SZ{s}"
        if first in ("5", "6", "9"):
            return f"SH{s}"
        if first in ("4", "8"):
            return f"BJ{s}"

    raise ValueError(f"unrecognized stock code format: {code!r}")
