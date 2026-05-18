"""normalize_stock_code 各种格式 + 异常路径。"""
from __future__ import annotations

import pytest

from ashare_mcp.utils import normalize_stock_code


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 纯 6 位:按首位推断交易所
        ("000001", "SZ000001"),
        ("300750", "SZ300750"),
        ("600036", "SH600036"),
        ("601398", "SH601398"),
        ("430139", "BJ430139"),
        ("832000", "BJ832000"),
        # 带前缀(大写 / 小写 / 带点 / 不带点)
        ("SZ000001", "SZ000001"),
        ("sz000001", "SZ000001"),
        ("sz.000001", "SZ000001"),
        ("SH.600036", "SH600036"),
        # 后缀
        ("000001.SZ", "SZ000001"),
        ("600036.sh", "SH600036"),
        # 周围空白
        ("  600036  ", "SH600036"),
    ],
)
def test_normalize_valid(raw: str, expected: str):
    assert normalize_stock_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",                # 空串
        "   ",             # 全空白
        "ABC123",          # 非数字代码
        "12345",           # 不足 6 位
        "1234567",         # 超过 6 位
        "SZ12345",         # 前缀 + 不足 6 位
        "999999",          # 首位 9 在 SH 范围(应通过) — 反例改为下方
    ],
)
def test_normalize_invalid_or_unrecognized(raw):
    # "999999" 实际属于 SH 范围,所以单独从参数化里排除并验证它通过
    if raw == "999999":
        assert normalize_stock_code(raw) == "SH999999"
        return
    with pytest.raises(ValueError):
        normalize_stock_code(raw)


def test_normalize_non_string_raises():
    with pytest.raises(ValueError):
        normalize_stock_code(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        normalize_stock_code(123456)  # type: ignore[arg-type]


def test_normalize_unrecognized_first_digit():
    # 首位 1 / 7 不在任何映射里
    with pytest.raises(ValueError):
        normalize_stock_code("100001")
    with pytest.raises(ValueError):
        normalize_stock_code("700001")
