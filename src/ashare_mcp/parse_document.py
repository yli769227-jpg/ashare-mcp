"""
parse_document: 用 opendatalab/MinerU 把 PDF / DOCX / PPTX / 图片 等非结构化文件转成
LLM-ready 的 markdown(+ 可选 content_list JSON)。

设计:
- 复用 MinerU 的 `mineru.cli.common.do_parse` 同步入口 + `read_fn` 读字节。
- 用临时目录接 MinerU 落盘的产物,再把 markdown(必产)/ content_list.json(可选)读回内存。
- 关键路径全部 `[parse_document]` 前缀日志。

环境变量:
- `MINERU_PARSE_BACKEND` 可覆盖默认后端,默认 `pipeline`。

依赖说明(重要):
- 裸 `pip install mineru` 只装 office 路径(docx / pptx / xlsx),纯 CPU 完全离线即可跑。
- PDF / 图片走 pipeline 后端时,**必须**额外装 `pip install "mineru[pipeline]"`(会拉
  torch + torchvision + transformers + onnxruntime,数 GB 体积,首次还要下模型权重)。
- 没装 pipeline 依赖时调 PDF 会以 ModuleNotFoundError('torch') 失败,本模块捕获后通过
  RuntimeError 友好抛出。office 路径不受影响。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from .utils import get_logger

logger = get_logger(__name__)

LOG_PREFIX = "[parse_document]"

OutputFormat = Literal["markdown", "json", "both"]

# MinerU 支持的扩展名(对齐 mineru.utils.enum_class)
_PDF_SUFFIXES = {".pdf"}
_OFFICE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_SUPPORTED_SUFFIXES = _PDF_SUFFIXES | _OFFICE_SUFFIXES | _IMAGE_SUFFIXES


def _validate_path(file_path: str) -> Path:
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError(f"invalid file_path: {file_path!r}")
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")
    if not p.is_file():
        raise ValueError(f"not a regular file: {p}")
    suffix = p.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise ValueError(
            f"unsupported file suffix {suffix!r}; supported: "
            f"{sorted(_SUPPORTED_SUFFIXES)}"
        )
    return p


def _resolve_subdir(parent: Path, file_stem: str) -> Path:
    """
    MinerU 落盘到 output_dir/<stem>/<mode>/。<mode> 取决于后端 + 文件类型:
      - pipeline + PDF/image: "auto" (或 ocr/txt,这里默认 auto)
      - office (docx/pptx/xlsx): "office"
      - hybrid backend: "hybrid_<parse_method>"
    我们不强假设,直接在 stem 目录下找包含 .md 的那一层。
    """
    stem_dir = parent / file_stem
    if not stem_dir.exists():
        raise FileNotFoundError(f"mineru output dir not found: {stem_dir}")
    # 优先一层
    for sub in stem_dir.iterdir():
        if sub.is_dir() and any(f.suffix == ".md" for f in sub.iterdir()):
            return sub
    # fallback: 递归找
    for md in stem_dir.rglob("*.md"):
        return md.parent
    raise FileNotFoundError(f"no .md produced under {stem_dir}")


def parse_document_impl(
    file_path: str,
    output_format: OutputFormat = "markdown",
    lang: str = "ch",
) -> dict:
    """
    主实现。返回:
      {
        "content": "<markdown 字符串>",
        "metadata": {
          "engine": "mineru",
          "backend": "<pipeline|vlm-...|office>",
          "source_file": "<absolute path>",
          "file_suffix": ".pdf",
          "lang": "ch",
          "pages": <int>,                # 页数 / 中间表元素数(office 无明确页码)
          "markdown_chars": <int>,
          "has_json": <bool>,
        },
        "content_list": [...]            # 仅 output_format in {"json","both"} 才会出现
      }
    """
    src = _validate_path(file_path)
    suffix = src.suffix.lower()
    backend = os.environ.get("MINERU_PARSE_BACKEND", "pipeline")

    logger.info(
        f"{LOG_PREFIX} start file={str(src)!r} suffix={suffix} "
        f"output_format={output_format} lang={lang!r} backend={backend!r}"
    )

    if output_format not in ("markdown", "json", "both"):
        raise ValueError(
            f"invalid output_format: {output_format!r}; "
            "must be one of 'markdown','json','both'"
        )

    # 延迟 import,避免没装 mineru 时 server import 直接挂
    try:
        from mineru.cli.common import do_parse, read_fn  # type: ignore
    except ImportError as e:
        logger.error(f"{LOG_PREFIX} mineru not installed: {e}")
        raise RuntimeError(
            "mineru not installed. Run: pip install mineru"
        ) from e

    file_bytes = read_fn(src)
    logger.info(
        f"{LOG_PREFIX} loaded bytes={len(file_bytes)} from {src.name}"
    )

    file_stem = src.stem
    want_json = output_format in ("json", "both")

    with tempfile.TemporaryDirectory(prefix="ashare_mineru_") as tmp_dir:
        logger.info(f"{LOG_PREFIX} mineru work dir={tmp_dir}")
        try:
            do_parse(
                output_dir=tmp_dir,
                pdf_file_names=[file_stem],
                pdf_bytes_list=[file_bytes],
                p_lang_list=[lang],
                backend=backend,
                parse_method="auto",
                # 不需要画 bbox / dump 中间产物,加速 + 减磁盘
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_dump_md=True,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_dump_content_list=want_json,
            )
        except ModuleNotFoundError as e:
            # PDF / image 路径需要 torch + transformers,常见漏装情况
            logger.error(
                f"{LOG_PREFIX} mineru pipeline backend missing dep: {e.name!r}. "
                "Install pipeline extras: pip install 'mineru[pipeline]'"
            )
            raise RuntimeError(
                f"mineru pipeline backend missing dependency {e.name!r}. "
                "PDF / image parsing requires: pip install 'mineru[pipeline]'"
            ) from e
        except Exception as e:
            logger.exception(
                f"{LOG_PREFIX} mineru do_parse failed: {type(e).__name__}: {e}"
            )
            raise

        try:
            sub = _resolve_subdir(Path(tmp_dir), file_stem)
        except FileNotFoundError:
            logger.error(
                f"{LOG_PREFIX} mineru produced no markdown for {src.name}; "
                f"workdir tree: {[str(p.relative_to(tmp_dir)) for p in Path(tmp_dir).rglob('*')]}"
            )
            raise

        md_path = sub / f"{file_stem}.md"
        if not md_path.exists():
            # 兜底:取目录里第一个 .md
            md_files = list(sub.glob("*.md"))
            if not md_files:
                raise FileNotFoundError(f"no .md in {sub}")
            md_path = md_files[0]

        markdown = md_path.read_text(encoding="utf-8")
        logger.info(
            f"{LOG_PREFIX} markdown bytes={len(markdown)} from {md_path.name}"
        )

        content_list = None
        if want_json:
            json_path = sub / f"{file_stem}_content_list.json"
            if json_path.exists():
                try:
                    content_list = json.loads(json_path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.error(
                        f"{LOG_PREFIX} content_list.json parse failed: {e}"
                    )
                    content_list = None
            else:
                logger.error(
                    f"{LOG_PREFIX} content_list.json not produced at {json_path}"
                )

        # 估页数:content_list 里 page_idx 最大值 +1;否则按 markdown 中 ---- 分页符兜底
        pages = None
        if isinstance(content_list, list) and content_list:
            try:
                pages = max(
                    (int(it.get("page_idx", 0)) for it in content_list if isinstance(it, dict)),
                    default=0,
                ) + 1
            except Exception:
                pages = None

        result: dict = {
            "content": markdown if output_format != "json" else "",
            "metadata": {
                "engine": "mineru",
                "backend": backend,
                "source_file": str(src),
                "file_suffix": suffix,
                "lang": lang,
                "pages": pages,
                "markdown_chars": len(markdown),
                "has_json": content_list is not None,
            },
        }
        if want_json:
            result["content_list"] = content_list

        logger.info(
            f"{LOG_PREFIX} done file={src.name} pages={pages} "
            f"md_chars={len(markdown)} has_json={content_list is not None}"
        )
        # tempdir 在 with 退出时清理,前面已经把 markdown / json 读进内存
        return result
