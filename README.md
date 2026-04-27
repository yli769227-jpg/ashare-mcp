# ashare-mcp

> 把 A 股财报变成 LLM 可调的工具。An MCP server that turns Chinese A-share financial statements into tools your LLM can call.

让 Claude(或任何 MCP 客户端)用一句"平安银行 2024 年报怎么样?"直接拿到结构化的资产负债表 / 利润表 / 现金流量表,字段经过精选、单位明确、缓存友好。

数据来源东方财富,通过 [akshare](https://github.com/akfamily/akshare),全部免费、无需 token。

---

## 为什么再做一个

GitHub 上"金融 LLM"项目大多卷在 **trading agent** 和 **SEC 10-K RAG**——前者同质化严重,后者只服务美股。**A 股 + 中文 + MCP 协议层** 的组合几乎空白。

`ashare-mcp` 的定位很窄:**做 A 股财报这一件事,做到能被任何 LLM 客户端十秒接入**。它不预测股价、不写研报、不替你做决策——它只把数据从东方财富搬到 LLM 的工具调用里,字段干净、单位清楚、错误明确。

## 快速开始

```bash
git clone https://github.com/yli769227-jpg/ashare-mcp.git
cd ashare-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

跑一次冒烟测试:

```bash
python -c "from ashare_mcp.data_source import get_annual_statements; \
  r = get_annual_statements('SZ000001', 2024); \
  print(r['company_name'], r['balance_sheet']['TOTAL_ASSETS'])"
# -> 平安银行 5769270000000.0
```

## 接入 Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`(Mac):

```json
{
  "mcpServers": {
    "ashare": {
      "command": "/absolute/path/to/ashare-mcp/.venv/bin/python",
      "args": ["-m", "ashare_mcp.server"]
    }
  }
}
```

重启 Claude Desktop,就能直接问:

> 帮我看一下平安银行 2024 年报,总资产、总负债、净利润、经营性现金流分别多少?

## 工具列表(v0)

| 工具 | 输入 | 输出 |
|---|---|---|
| `get_three_statements` | `stock_code`, `year` | 年报三大表(精选 ~150 字段)|

代码归一化支持 `000001` / `SZ000001` / `sz.000001` / `000001.SZ` 多种格式。

## 架构

```mermaid
flowchart LR
    LLM[Claude / 任意 MCP 客户端] -->|JSON-RPC over stdio| Server[ashare-mcp<br/>FastMCP server]
    Server -->|代码归一化| Norm[股票代码归一化<br/>SZ/SH/BJ 自动判断]
    Server -->|拉取三表| DS[数据源封装<br/>akshare 包装层]
    DS -->|缓存命中| Cache[(进程内存缓存<br/>lru_cache)]
    DS -->|缓存未命中| YearlyEM[akshare<br/>by_yearly_em]
    YearlyEM -->|HTTP| EM[东方财富<br/>财报数据接口]
    DS -->|字段过滤| Filter[剔除元数据列<br/>剔除同比列<br/>剔除空/零字段]
    Server -->|结构化 JSON| LLM
```

**关键设计**:

- **字段名保留东方财富原始英文**(`TOTAL_ASSETS` / `LOAN_ADVANCE` / `NETPROFIT`)。LLM 直接能理解,且银行 / 工商企业 / 保险等不同行业字段都在同一份字典里,无需做行业判断。
- **进程内存缓存**让"同一公司多年份对比"几乎零成本——冷启动一次拉全量,后续年份切换 < 1ms。
- **日志走 stderr**,不污染 MCP stdio 协议通道。

## 路线图

| 版本 | 工具 | 状态 |
|---|---|---|
| v0(当前) | `get_three_statements` | ✅ |
| v1 | `cross_check_balance`(资产负债勾稽校验) | 设计中 |
| v1 | `compare_peers`(同业 N 家同期横向对比) | 设计中 |
| v2 | 季度数据 + 同比/环比派生指标 | 待定 |
| v2 | MCP 官方 registry 发布 | 待定 |

## 本地开发

```bash
# 增量验证(每次改完跑一遍)
python -c "from ashare_mcp.utils import normalize_stock_code; \
  assert normalize_stock_code('000001') == 'SZ000001'"

python -c "from ashare_mcp.server import mcp; \
  import asyncio; print([t.name for t in asyncio.run(mcp.list_tools())])"
```

## 数据声明

- 数据源:东方财富,通过 [akshare](https://github.com/akfamily/akshare)。
- 数据延迟、口径、准确性以东方财富为准,**不构成投资建议**。
- 仅用于教育与研究目的。

## License

MIT — see [LICENSE](./LICENSE).
