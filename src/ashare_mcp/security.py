"""
集中防御层 (Security validators)
=================================

把 MCP / HTTP 入口的"用户可控参数"在进入业务逻辑前过一遍。
设计原则:

1. **白名单**: 只接受明确允许的形态,任何越界一律 raise ValueError。
2. **不破坏既有 happy path**: 合法输入原样返回(或返回 canonical 形式),
   失败抛 ValueError 让 FastAPI 的 422 handler 自然接住。
3. **可观测**: 拒绝路径写 warning 日志,带上输入截断(避免 log injection)。

防御范围:
- `validate_ticker(t)`      —— A 股 ticker 形态白名单,拦 path-traversal / 注入字符
- `safe_path(p, base)`      —— 任意路径在 join+resolve 后必须落在 base 下
- `safe_url(u)`             —— 仅允许 http(s),拒绝 IP 字面量 / 内网段 /
                                 file:// / 非标准协议(SSRF preventive)
"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Ticker
# ---------------------------------------------------------------------------

# 接受的 ticker 形态(由 normalize_stock_code 的合约推导,严格白名单):
#   - 6 位纯数字              如 '000001' / '600036' / '430139'
#   - 前缀 SH/SZ/BJ + 6 位     如 'SZ000001' / 'sz000001' / 'SH.600036'
#   - 6 位 + 后缀 .SH/.SZ/.BJ  如 '000001.SZ' / '600036.sh'
# 边界: 长度上限 16 (覆盖 'sh.000001 ' 极限),先 trim 再正则。
#       禁止任何 / \ . . / ; ' " ` < > 等注入字符 —— 正则就只放数字 + 字母 + 单点。
_TICKER_RE = re.compile(
    r"^(?:"
    r"\d{6}"                                # 纯 6 位
    r"|[SsZzHhBbJj]{2}\.?\d{6}"             # 前缀 + (可选点) + 6 位
    r"|\d{6}\.[SsZzHhBbJj]{2}"              # 6 位 + 点 + 后缀
    r")$"
)

_TICKER_MAX_LEN = 16


def validate_ticker(t: str) -> str:
    """
    校验 A 股 ticker 形态。**只判形态,不做交易所归一化**(那是 normalize_stock_code 的事)。

    合法形态(大小写均可):
      - '000001'         (6 位纯数字)
      - 'SZ000001'       (前缀 + 6 位)
      - 'sz.000001'      (前缀 + 点 + 6 位)
      - 'SH.600036'
      - '000001.SZ'      (6 位 + 点 + 后缀)
      - '600036.sh'

    拒绝(全部 raise ValueError):
      - 空串 / None / 非字符串
      - 含 '/' '\\' ';' '\'' '"' '`' '<' '>' '..' 等注入字符
      - 长度 > 16
      - 不匹配上述白名单
      - 6 位但首位不在 A 股交易所映射里(0/2/3/5/6/9/4/8) —— 这一条交给
        normalize_stock_code 兜底,本函数只挡形态

    Returns:
        trim 后的原值(供下游 normalize_stock_code 消费),保证只含
        数字 + 字母 + 一个可选点。
    """
    if not isinstance(t, str):
        logger.warning(f"validate_ticker reject: non-string type={type(t).__name__}")
        raise ValueError(f"ticker must be str, got {type(t).__name__}")
    s = t.strip()
    if not s:
        raise ValueError("ticker is empty")
    if len(s) > _TICKER_MAX_LEN:
        logger.warning(f"validate_ticker reject: too long len={len(s)}")
        raise ValueError(f"ticker too long: {len(s)} > {_TICKER_MAX_LEN}")
    if not _TICKER_RE.match(s):
        # 截断输入避免日志注入(只取前 32 字符的 repr)
        safe_repr = repr(s)[:64]
        logger.warning(f"validate_ticker reject: bad form {safe_repr}")
        raise ValueError(f"invalid ticker format: {safe_repr}")
    return s


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

def safe_path(user_path: str, base: Path) -> Path:
    """
    把用户路径限制在 base 目录下。

    防御:
      - 拒绝非字符串 / 空串
      - expanduser + resolve 后,必须是 base.resolve() 的子路径
      - 拦截 '../' / 绝对路径越狱 / 软链跳出

    Args:
        user_path: 用户传入的路径(相对或绝对)。
        base: 允许的根目录。会被 resolve 一次。

    Returns:
        resolve 后的绝对 Path(保证在 base 下,可能不存在)。

    Raises:
        ValueError: 类型不对 / 越界。
    """
    if not isinstance(user_path, str) or not user_path.strip():
        raise ValueError(f"invalid path: {user_path!r}")
    if not isinstance(base, Path):
        raise ValueError(f"base must be Path, got {type(base).__name__}")

    base_resolved = base.expanduser().resolve()
    # 把 user_path join 到 base 之后再 resolve,绝对路径会被 Path 语义覆盖 base
    # 所以这里显式禁止绝对路径(避免歧义),只接受相对路径
    p = Path(user_path).expanduser()
    if p.is_absolute():
        # 允许"已经在 base 下的绝对路径"(用户给的就是绝对路径),resolve 后再判
        candidate = p.resolve()
    else:
        candidate = (base_resolved / p).resolve()

    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        logger.warning(
            f"safe_path reject: escape attempt user_path={user_path!r} "
            f"resolved={candidate} base={base_resolved}"
        )
        raise ValueError(
            f"path escapes base directory: {user_path!r} -> {candidate} (base={base_resolved})"
        )
    return candidate


# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------

# 内网 / 本地 / 链路本地 / 多播 / 保留段
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]

_BLOCKED_HOSTS_LITERAL = {
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",   # GCP metadata
    "169.254.169.254",            # AWS / Azure / GCP metadata IP literal
}


def _is_blocked_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    for net in _PRIVATE_NETS:
        if ip in net:
            return True
    return False


def safe_url(u: str, *, resolve_dns: bool = True) -> str:
    """
    校验 URL 安全性 (SSRF 防御 preventive)。

    允许:
      - 协议: http / https
      - 必须有 hostname

    拒绝(全部 raise ValueError):
      - 非字符串 / 空串
      - 协议不在 {http, https} (拦 file:// / gopher:// / ftp:// / data: 等)
      - hostname 是 IP 字面量且落在内网 / loopback / link-local / multicast / reserved
      - hostname 命中 _BLOCKED_HOSTS_LITERAL (localhost / metadata.google.internal / ...)
      - resolve_dns=True 时,DNS 解析结果包含内网 IP (DNS rebinding 防御)

    Args:
        u: 待校验 URL。
        resolve_dns: 是否做 DNS 解析检查;离线测试或受信任白名单可设 False。
                     默认 True (production-safe 默认值)。

    Returns:
        原 URL 字符串(校验通过)。

    Raises:
        ValueError: 任何拒绝条件命中。
    """
    if not isinstance(u, str) or not u.strip():
        raise ValueError(f"invalid url: {u!r}")
    parsed = urlparse(u.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        logger.warning(f"safe_url reject: scheme={scheme!r} url_prefix={u[:64]!r}")
        raise ValueError(f"unsupported url scheme: {scheme!r} (only http/https allowed)")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"url has no hostname: {u!r}")

    if host in _BLOCKED_HOSTS_LITERAL:
        logger.warning(f"safe_url reject: blocked host literal={host!r}")
        raise ValueError(f"blocked hostname: {host!r}")

    # 如果 hostname 本身就是 IP 字面量,直接判
    if _is_blocked_ip(host):
        logger.warning(f"safe_url reject: ip literal in private/reserved range host={host!r}")
        raise ValueError(f"hostname is private/reserved IP: {host!r}")

    # DNS 解析检查(可关闭以便离线测试 / 受信任白名单跳过)
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as e:
            logger.warning(f"safe_url reject: dns failed host={host!r}: {e}")
            raise ValueError(f"cannot resolve hostname: {host!r}: {e}") from e
        for fam, _stype, _proto, _canon, sockaddr in infos:
            addr = sockaddr[0]
            if _is_blocked_ip(addr):
                logger.warning(
                    f"safe_url reject: dns resolved to private ip host={host!r} addr={addr!r}"
                )
                raise ValueError(
                    f"hostname {host!r} resolves to private/reserved ip {addr!r}"
                )

    return u
