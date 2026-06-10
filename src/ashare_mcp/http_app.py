"""
ashare-mcp HTTP API — FastAPI wrapper over the same business logic the MCP stdio
server exposes. Frontend (web/) talks JSON to these endpoints; nothing here imports
the MCP runtime, so it can run side-by-side with `ashare-mcp` stdio.
"""
from __future__ import annotations

from importlib import metadata as importlib_metadata
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .data_source import get_annual_statements
from .checks import run_all_checks
from .history import track_company_history_impl
from .peer_compare import MAX_STOCK_CODES, compare_peers_impl
from .utils import get_logger, normalize_stock_code

logger = get_logger(__name__)


def _get_version() -> str:
    try:
        return importlib_metadata.version("ashare-mcp")
    except importlib_metadata.PackageNotFoundError:
        return "0.0.0+unknown"


VERSION = _get_version()

app = FastAPI(
    title="ashare-mcp HTTP API",
    version=VERSION,
    description="HTTP wrapper for the ashare-mcp tools (A-share financial statements).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handling — single source of truth for the {error, code} envelope.
# ---------------------------------------------------------------------------

def _err(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message, "code": code})


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    logger.warning(f"422 {request.method} {request.url.path} INVALID_INPUT: {exc}")
    return _err(422, str(exc), "INVALID_INPUT")


@app.exception_handler(Exception)
async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # FastAPI's own HTTPException is handled by Starlette before this runs, so
    # anything reaching here is genuinely unexpected (network, akshare crash, etc.)
    # 详细异常(类型/消息/堆栈)只记服务端日志;对外只回通用信息,
    # 避免向公网客户端泄露内部异常细节、路径或堆栈。
    logger.exception(f"502 {request.method} {request.url.path} UPSTREAM_ERROR: {type(exc).__name__}: {exc}")
    return _err(502, "上游数据获取失败,请稍后重试", "UPSTREAM_ERROR")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ComparePeersRequest(BaseModel):
    # max_length 防请求放大:每家公司 3 次上游抓取,公开部署不设上限会被资源耗尽。
    # compare_peers_impl 内部还有同样的校验(MCP stdio 路径共用)。
    stock_codes: List[str] = Field(..., min_length=1, max_length=MAX_STOCK_CODES)
    year: int
    metrics: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> Dict[str, str]:
    logger.info("GET /healthz")
    return {"status": "ok", "version": VERSION}


@app.get("/api/statements")
def api_statements(
    stock_code: str = Query(..., description="A-share code, any common format"),
    year: int = Query(..., description="Annual report year, e.g. 2024"),
) -> Dict[str, Any]:
    logger.info(f"GET /api/statements stock_code={stock_code!r} year={year}")
    symbol = normalize_stock_code(stock_code)
    result = get_annual_statements(symbol, year)
    logger.info(
        f"GET /api/statements -> 200 company={result.get('company_name')!r} "
        f"bs={len(result.get('balance_sheet') or {})} "
        f"pl={len(result.get('income_statement') or {})} "
        f"cf={len(result.get('cash_flow_statement') or {})}"
    )
    return result


@app.get("/api/cross-check")
def api_cross_check(
    stock_code: str = Query(...),
    year: int = Query(...),
) -> Dict[str, Any]:
    logger.info(f"GET /api/cross-check stock_code={stock_code!r} year={year}")
    symbol = normalize_stock_code(stock_code)
    stmts = get_annual_statements(symbol, year)
    checks = run_all_checks(
        stmts["balance_sheet"],
        stmts["income_statement"],
        stmts["cash_flow_statement"],
    )
    out = {
        "stock_code": symbol,
        "company_name": stmts["company_name"],
        "report_date": stmts["report_date"],
        **checks,
    }
    logger.info(
        f"GET /api/cross-check -> 200 passed={out['summary']['passed']} "
        f"failed={out['summary']['failed']} skipped={out['summary']['skipped']}"
    )
    return out


@app.post("/api/compare-peers")
def api_compare_peers(payload: ComparePeersRequest) -> Dict[str, Any]:
    logger.info(
        f"POST /api/compare-peers stock_codes={payload.stock_codes} "
        f"year={payload.year} metrics={payload.metrics}"
    )
    result = compare_peers_impl(payload.stock_codes, payload.year, payload.metrics)
    logger.info(
        f"POST /api/compare-peers -> 200 companies={len(result['companies'])} "
        f"errors={len(result['errors'])}"
    )
    return result


@app.get("/api/history")
def api_history(
    stock_code: str = Query(...),
    years: int = Query(5, description="Number of years (default 5, max 20)"),
) -> Dict[str, Any]:
    logger.info(f"GET /api/history stock_code={stock_code!r} years={years}")
    result = track_company_history_impl(stock_code, years)
    logger.info(
        f"GET /api/history -> 200 company={result.get('company_name')!r} "
        f"industry={result.get('industry')} years={len(result.get('years', []))} "
        f"anomalies={len(result.get('anomalies', []))}"
    )
    return result


def main() -> None:
    import os
    import uvicorn
    # PaaS (Railway / Render / Fly) 会注入 $PORT;本地不设时默认 8000
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"ashare-mcp HTTP starting on 0.0.0.0:{port} (version={VERSION})")
    uvicorn.run("ashare_mcp.http_app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
