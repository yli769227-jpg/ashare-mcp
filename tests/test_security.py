"""
tests/test_security.py — 测试 src/ashare_mcp/security.py 的三个 validator。

覆盖:
  - validate_ticker:
      ✅ 合法形态全通(纯 6 位 / 大写前缀 / 小写前缀 / 带点前缀 / 后缀 / 大小写后缀)
      ❌ path-traversal / 注入字符 / 超长 / 非字符串 / 空串 全拒
  - safe_path:
      ✅ base 内的相对路径通过,resolve 出绝对路径仍在 base 下
      ❌ '../' 越狱、不在 base 下的绝对路径 全拒
  - safe_url:
      ✅ 普通 https://公网域名 (跳过 DNS 解析时)
      ❌ file:// / gopher:// / ftp:// / 空 scheme 全拒
      ❌ 127.0.0.1 / 10.x / 192.168.x / 169.254.169.254 (云元数据) / localhost / ::1 全拒
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ashare_mcp.security import safe_path, safe_url, validate_ticker


# ---------- validate_ticker ----------

@pytest.mark.parametrize(
    "good",
    [
        "000001",
        "300750",
        "600036",
        "430139",
        "832000",
        "SZ000001",
        "sz000001",
        "sz.000001",
        "SH.600036",
        "000001.SZ",
        "600036.sh",
        "  600036  ",   # trim 后合法
    ],
)
def test_validate_ticker_accepts_legal_forms(good: str):
    out = validate_ticker(good)
    assert isinstance(out, str)
    # trim 后不带前后空白
    assert out == good.strip()


@pytest.mark.parametrize(
    "bad",
    [
        "",                       # 空串
        "   ",                    # 全空白
        "../000001",              # path traversal
        "../../etc/passwd",
        "/etc/passwd",
        "000001/../../etc",
        "000001;rm -rf /",        # 命令注入字符
        "000001';--",             # SQL-ish 字符
        "000001 OR 1=1",
        "<script>alert(1)</script>",
        "000001\x00.SH",          # null byte
        "000\n001",               # 内嵌换行(strip 后仍含)
        "ABCDEF",                 # 非数字
        "12345",                  # 不足 6 位
        "1234567",                # 多余位
        "SZSZ000001",             # 双前缀
        "SZ00000",                # 前缀+不足
        "X" * 100,                # 超长
        "999999.US",              # 不允许的后缀
    ],
)
def test_validate_ticker_rejects_attacks_and_bad_shapes(bad: str):
    with pytest.raises(ValueError):
        validate_ticker(bad)


def test_validate_ticker_rejects_non_string():
    for bad in (None, 123456, 600036, ["000001"], {"t": "000001"}):
        with pytest.raises(ValueError):
            validate_ticker(bad)  # type: ignore[arg-type]


# ---------- safe_path ----------

def test_safe_path_accepts_in_base(tmp_path: Path):
    base = tmp_path / "sandbox"
    base.mkdir()
    target = base / "sub" / "file.txt"
    target.parent.mkdir()
    target.write_text("ok", encoding="utf-8")

    resolved = safe_path("sub/file.txt", base)
    assert resolved == target.resolve()


def test_safe_path_rejects_dotdot_escape(tmp_path: Path):
    base = tmp_path / "sandbox"
    base.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("password=hunter2", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes base"):
        safe_path("../secret.txt", base)


def test_safe_path_rejects_absolute_outside(tmp_path: Path):
    base = tmp_path / "sandbox"
    base.mkdir()
    with pytest.raises(ValueError, match="escapes base"):
        safe_path("/etc/passwd", base)


def test_safe_path_rejects_empty_or_nonstring(tmp_path: Path):
    base = tmp_path / "sandbox"
    base.mkdir()
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            safe_path(bad, base)
    with pytest.raises(ValueError):
        safe_path(None, base)  # type: ignore[arg-type]


def test_safe_path_accepts_absolute_inside(tmp_path: Path):
    base = tmp_path / "sandbox"
    base.mkdir()
    (base / "ok.txt").write_text("ok", encoding="utf-8")
    abs_in = str((base / "ok.txt").resolve())
    out = safe_path(abs_in, base)
    assert out == (base / "ok.txt").resolve()


# ---------- safe_url ----------

def test_safe_url_accepts_public_https():
    # resolve_dns=False 避免离线 CI 因 DNS 失败误伤
    out = safe_url("https://www.example.com/path?q=1", resolve_dns=False)
    assert out.startswith("https://")


def test_safe_url_accepts_public_http():
    out = safe_url("http://example.org/", resolve_dns=False)
    assert out.startswith("http://")


@pytest.mark.parametrize(
    "bad",
    [
        "file:///etc/passwd",
        "file:///c:/Windows/System32/config/SAM",
        "ftp://example.com/x",
        "gopher://example.com/",
        "data:text/html;base64,PHNjcmlwdD4=",
        "javascript:alert(1)",
        "",                          # 空串
        "   ",                       # 全空白
        "no-scheme.example.com/x",   # 没 scheme
    ],
)
def test_safe_url_rejects_dangerous_schemes(bad: str):
    with pytest.raises(ValueError):
        safe_url(bad, resolve_dns=False)


@pytest.mark.parametrize(
    "ssrf",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",   # AWS / Azure / GCP metadata
        "http://localhost/",
        "http://metadata.google.internal/",
        "https://localhost:8080/",
    ],
)
def test_safe_url_rejects_ssrf_targets(ssrf: str):
    with pytest.raises(ValueError):
        safe_url(ssrf, resolve_dns=False)


def test_safe_url_rejects_non_string():
    for bad in (None, 123, b"http://example.com", ["http://x"]):
        with pytest.raises(ValueError):
            safe_url(bad, resolve_dns=False)  # type: ignore[arg-type]
