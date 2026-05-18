# ashare-mcp · Web 前端

A 股财报工具的配套 Web demo,使用 React 18 + TypeScript + Vite + Tailwind CSS。

## 功能

- **三大报表**:按股票代码 + 年份查询资产负债表、利润表、现金流量表
- **勾稽校验**:自动核对财报恒等式,展示通过/未通过项
- **同业对比**:多家公司指标横评 + 排名 + 统计摘要
- **历史趋势**:多年序列、YoY、CAGR、异常点

## 启动

```bash
cd web
npm install
cp .env.example .env.local   # 可选:自定义后端地址
npm run dev                  # → http://localhost:5173
```

构建生产包:

```bash
npm run build
npm run preview
```

## 配置

通过环境变量 `VITE_API_BASE` 指定后端 FastAPI 地址,默认 `http://localhost:8000`。

```
# .env.local
VITE_API_BASE=http://localhost:8000
```

## API 依赖

后端需提供以下接口(详见仓库根 README):

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 健康检查 |
| GET | `/api/statements?stock_code=&year=` | 三大报表 |
| GET | `/api/cross-check?stock_code=&year=` | 勾稽校验 |
| POST | `/api/compare-peers` | 同业对比 |
| GET | `/api/history?stock_code=&years=` | 历史趋势 |

错误响应统一格式:`{"error": "...", "code": "INVALID_INPUT" | "UPSTREAM_ERROR"}`。

## 目录

```
src/
├── api.ts              统一 API 封装 + ApiError
├── types.ts            后端响应 TS 类型
├── App.tsx             顶部 tab 容器
├── components/         复用组件 (Card / KVTable / Form / States / 数字格式)
└── tabs/               4 个 tab 实现
```

## 说明

数据来源为东方财富(akshare),仅供学习研究,不构成投资建议。
