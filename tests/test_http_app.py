"""HTTP API 端到端 — TestClient + 业务函数全部 monkeypatch。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from ashare_mcp import http_app


@pytest.fixture
def client():
    # raise_server_exceptions=False:让我们的 exception_handler 把异常翻成 502 JSON,
    # 而不是 TestClient 直接把原始异常重抛出来。生产里 uvicorn 也是后者行为。
    return TestClient(http_app.app, raise_server_exceptions=False)


# ---------- /healthz ----------

def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body and body["version"]


# ---------- /api/statements ----------

def test_statements_200(client, monkeypatch):
    def fake(symbol, year):
        assert symbol == "SZ000001"
        assert year == 2024
        return {
            "stock_code": symbol,
            "company_name": "平安银行",
            "report_date": f"{year}-12-31",
            "currency": "CNY",
            "unit": "yuan (元)",
            "balance_sheet": {"TOTAL_ASSETS": 1.0},
            "income_statement": {"OPERATE_INCOME": 1.0},
            "cash_flow_statement": {"NETCASH_OPERATE": 1.0},
        }
    monkeypatch.setattr(http_app, "get_annual_statements", fake)

    r = client.get("/api/statements", params={"stock_code": "000001", "year": 2024})
    assert r.status_code == 200
    body = r.json()
    assert body["company_name"] == "平安银行"
    assert body["balance_sheet"]["TOTAL_ASSETS"] == 1.0


def test_statements_422_invalid_code(client, monkeypatch):
    # normalize 会自己抛 ValueError,无需 monkeypatch business fn
    r = client.get("/api/statements", params={"stock_code": "BAD", "year": 2024})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "INVALID_INPUT"
    assert "error" in body


@pytest.mark.parametrize(
    "evil",
    [
        "../etc/passwd",
        "/etc/passwd",
        "000001;rm -rf /",
        "000001';--",
        "<script>",
        "X" * 100,
        "000001 OR 1=1",
    ],
)
def test_statements_422_rejects_injection_attempts(client, evil: str):
    """validate_ticker 必须在业务层前拦下所有注入 / path-traversal 字符。"""
    r = client.get("/api/statements", params={"stock_code": evil, "year": 2024})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "INVALID_INPUT"


def test_statements_422_value_error_from_business(client, monkeypatch):
    def fake(symbol, year):
        raise ValueError("no annual data for 1999")
    monkeypatch.setattr(http_app, "get_annual_statements", fake)

    r = client.get("/api/statements", params={"stock_code": "000001", "year": 1999})
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_INPUT"


def test_statements_502_upstream_error(client, monkeypatch):
    def fake(symbol, year):
        raise RuntimeError("network down")
    monkeypatch.setattr(http_app, "get_annual_statements", fake)

    r = client.get("/api/statements", params={"stock_code": "000001", "year": 2024})
    assert r.status_code == 502
    body = r.json()
    assert body["code"] == "UPSTREAM_ERROR"
    assert "network down" in body["error"]


def test_statements_missing_required_param(client):
    # FastAPI 自己的 422(参数校验),不是我们 envelope 的 422
    r = client.get("/api/statements", params={"stock_code": "000001"})
    assert r.status_code == 422


# ---------- /api/cross-check ----------

def test_cross_check_200(client, monkeypatch):
    def fake_stmts(symbol, year):
        return {
            "stock_code": symbol, "company_name": "X", "report_date": "2024-12-31",
            "balance_sheet": {}, "income_statement": {}, "cash_flow_statement": {},
        }
    def fake_checks(bs, pl, cf):
        return {"checks": [], "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
    monkeypatch.setattr(http_app, "get_annual_statements", fake_stmts)
    monkeypatch.setattr(http_app, "run_all_checks", fake_checks)

    r = client.get("/api/cross-check", params={"stock_code": "000001", "year": 2024})
    assert r.status_code == 200
    body = r.json()
    assert body["stock_code"] == "SZ000001"
    assert body["summary"]["total"] == 0


def test_cross_check_422(client, monkeypatch):
    def fake(symbol, year):
        raise ValueError("no data")
    monkeypatch.setattr(http_app, "get_annual_statements", fake)

    r = client.get("/api/cross-check", params={"stock_code": "000001", "year": 2024})
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_INPUT"


def test_cross_check_502(client, monkeypatch):
    def fake(symbol, year):
        raise ConnectionError("boom")
    monkeypatch.setattr(http_app, "get_annual_statements", fake)

    r = client.get("/api/cross-check", params={"stock_code": "000001", "year": 2024})
    assert r.status_code == 502
    assert r.json()["code"] == "UPSTREAM_ERROR"


# ---------- POST /api/compare-peers ----------

def test_compare_peers_200(client, monkeypatch):
    def fake(stock_codes: List[str], year: int, metrics: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "year": year, "report_date": f"{year}-12-31",
            "metrics": ["TOTAL_ASSETS", "ROE"],
            "companies": [{"stock_code": c, "company_name": c, "values": {}, "ranks": {}, "fallbacks": None} for c in stock_codes],
            "summary": {},
            "errors": [],
        }
    monkeypatch.setattr(http_app, "compare_peers_impl", fake)

    r = client.post(
        "/api/compare-peers",
        json={"stock_codes": ["000001", "600036"], "year": 2024},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["year"] == 2024
    assert len(body["companies"]) == 2


def test_compare_peers_with_metrics(client, monkeypatch):
    seen = {}
    def fake(stock_codes, year, metrics=None):
        seen["metrics"] = metrics
        return {
            "year": year, "report_date": f"{year}-12-31",
            "metrics": (metrics or []) + ["ROE"],
            "companies": [], "summary": {}, "errors": [],
        }
    monkeypatch.setattr(http_app, "compare_peers_impl", fake)

    r = client.post(
        "/api/compare-peers",
        json={"stock_codes": ["000001"], "year": 2024, "metrics": ["TOTAL_ASSETS"]},
    )
    assert r.status_code == 200
    assert seen["metrics"] == ["TOTAL_ASSETS"]


def test_compare_peers_422_empty_list(client):
    # pydantic min_length=1 → FastAPI 自身 422
    r = client.post("/api/compare-peers", json={"stock_codes": [], "year": 2024})
    assert r.status_code == 422


def test_compare_peers_422_value_error(client, monkeypatch):
    def fake(stock_codes, year, metrics=None):
        raise ValueError("invalid metrics")
    monkeypatch.setattr(http_app, "compare_peers_impl", fake)

    r = client.post("/api/compare-peers", json={"stock_codes": ["000001"], "year": 2024})
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_INPUT"


def test_compare_peers_502_upstream(client, monkeypatch):
    def fake(stock_codes, year, metrics=None):
        raise OSError("dns failure")
    monkeypatch.setattr(http_app, "compare_peers_impl", fake)

    r = client.post("/api/compare-peers", json={"stock_codes": ["000001"], "year": 2024})
    assert r.status_code == 502
    assert r.json()["code"] == "UPSTREAM_ERROR"


# ---------- /api/history ----------

def test_history_200_default_years(client, monkeypatch):
    seen = {}
    def fake(stock_code, years, metrics=None):
        seen["years"] = years
        return {
            "stock_code": "SZ000001", "company_name": "X", "industry": "industrial",
            "years": list(range(2024 - years + 1, 2025)),
            "report_dates": [],
            "missing_years": [],
            "series": {}, "fallbacks": {}, "yoy": {}, "cagr": {}, "stats": {}, "anomalies": [],
        }
    monkeypatch.setattr(http_app, "track_company_history_impl", fake)

    r = client.get("/api/history", params={"stock_code": "000001"})
    assert r.status_code == 200
    assert seen["years"] == 5  # default


def test_history_200_custom_years(client, monkeypatch):
    seen = {}
    def fake(stock_code, years, metrics=None):
        seen["years"] = years
        return {
            "stock_code": "SZ000001", "company_name": "X", "industry": "industrial",
            "years": [2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029],
            "report_dates": [], "missing_years": [], "series": {}, "fallbacks": {},
            "yoy": {}, "cagr": {}, "stats": {}, "anomalies": [],
        }
    monkeypatch.setattr(http_app, "track_company_history_impl", fake)

    r = client.get("/api/history", params={"stock_code": "000001", "years": 10})
    assert r.status_code == 200
    assert seen["years"] == 10


def test_history_422(client, monkeypatch):
    def fake(stock_code, years, metrics=None):
        raise ValueError("years must be positive")
    monkeypatch.setattr(http_app, "track_company_history_impl", fake)

    r = client.get("/api/history", params={"stock_code": "000001", "years": 0})
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_INPUT"


def test_history_502(client, monkeypatch):
    def fake(stock_code, years, metrics=None):
        raise TimeoutError("akshare slow")
    monkeypatch.setattr(http_app, "track_company_history_impl", fake)

    r = client.get("/api/history", params={"stock_code": "000001", "years": 5})
    assert r.status_code == 502
    assert r.json()["code"] == "UPSTREAM_ERROR"


# ---------- CORS ----------

def test_cors_headers_present_on_actual_request(client):
    # CORSMiddleware 在请求带 Origin 时回 Access-Control-Allow-Origin
    r = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_cors_preflight(client):
    r = client.options(
        "/api/statements",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # CORSMiddleware 直接处理 preflight,200
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"
