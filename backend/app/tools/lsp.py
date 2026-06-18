from __future__ import annotations

import ast
import concurrent.futures
import fnmatch
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.schemas.tools import (
    LspDefinitionInput,
    LspDefinitionMatch,
    LspDefinitionOutput,
    LspReferenceMatch,
    LspReferencesInput,
    LspReferencesOutput,
)
from app.tools.base import ToolContext

_IGNORE = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}


def lsp_definition(ctx: ToolContext, inp: LspDefinitionInput) -> LspDefinitionOutput:
    base = ctx.resolve_read(inp.path)
    warnings: list[str] = []
    lsp_command = shutil.which("pyright-langserver")
    if lsp_command and inp.from_path and inp.line is not None and inp.column is not None:
        try:
            definitions = _definition_with_pyright_lsp(ctx, lsp_command, inp)
            if definitions:
                return LspDefinitionOutput(
                    query=inp.query,
                    status="resolved",
                    definitions=definitions,
                    engine="pyright_lsp",
                    warnings=warnings,
                )
            warnings.append("pyright-langserver returned no definition; used python AST fallback")
        except Exception as exc:
            warnings.append(f"pyright-langserver failed: {type(exc).__name__}; used python AST fallback")
    elif lsp_command is None:
        warnings.append("pyright-langserver unavailable; used python AST fallback")
    else:
        warnings.append("pyright-langserver requires from_path, line, and column; used python AST fallback")

    definitions = _definition_with_python_ast(ctx, base, inp)
    if definitions:
        return LspDefinitionOutput(
            query=inp.query,
            status="resolved",
            definitions=definitions,
            engine="python_ast_fallback",
            warnings=warnings,
        )
    return LspDefinitionOutput(
        query=inp.query,
        status="missing",
        definitions=[],
        engine="python_ast_fallback",
        warnings=warnings,
    )


def lsp_references(ctx: ToolContext, inp: LspReferencesInput) -> LspReferencesOutput:
    base = ctx.resolve_read(inp.path)
    warnings: list[str] = []
    lsp_command = shutil.which("pyright-langserver")
    if lsp_command and inp.from_path and inp.line is not None and inp.column is not None:
        try:
            references = _references_with_pyright_lsp(ctx, lsp_command, inp)
            if references:
                return LspReferencesOutput(
                    query=inp.query,
                    status="resolved",
                    references=references,
                    engine="pyright_lsp",
                    warnings=warnings,
                )
            warnings.append("pyright-langserver returned no references; used python AST fallback")
        except Exception as exc:
            warnings.append(f"pyright-langserver references failed: {type(exc).__name__}; used python AST fallback")
    elif lsp_command is None:
        warnings.append("pyright-langserver unavailable; used python AST fallback")
    else:
        warnings.append("pyright-langserver references require from_path, line, and column; used python AST fallback")

    references = _references_with_python_ast(ctx, base, inp)
    if references:
        return LspReferencesOutput(
            query=inp.query,
            status="resolved",
            references=references,
            engine="python_ast_fallback",
            warnings=warnings,
        )
    return LspReferencesOutput(
        query=inp.query,
        status="missing",
        references=[],
        engine="python_ast_fallback",
        warnings=warnings,
    )


def _definition_with_pyright_lsp(
    ctx: ToolContext,
    command: str,
    inp: LspDefinitionInput,
) -> list[LspDefinitionMatch]:
    source_file = ctx.resolve_read(inp.from_path or "")
    content = source_file.read_bytes()[: inp.max_file_bytes].decode("utf-8", errors="replace")
    uri = source_file.as_uri()
    proc = subprocess.Popen(
        [command, "--stdio"],
        cwd=ctx.root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline_seconds = max(inp.timeout_ms / 1000, 0.1)
        _send_lsp(proc, 1, "initialize", {"rootUri": ctx.root.as_uri(), "capabilities": {}})
        _read_lsp_response(proc, 1, timeout_seconds=deadline_seconds)
        _send_lsp(proc, None, "initialized", {})
        _send_lsp(
            proc,
            None,
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": content,
                }
            },
        )
        _send_lsp(
            proc,
            2,
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": (inp.line or 1) - 1, "character": inp.column or 0},
            },
        )
        response = _read_lsp_response(proc, 2, timeout_seconds=deadline_seconds)
        result = response.get("result")
        return _lsp_locations_to_matches(ctx, result, inp)
    finally:
        try:
            _send_lsp(proc, 3, "shutdown", None)
            _send_lsp(proc, None, "exit", None)
        except Exception:
            pass
        proc.kill()


def _references_with_pyright_lsp(
    ctx: ToolContext,
    command: str,
    inp: LspReferencesInput,
) -> list[LspReferenceMatch]:
    source_file = ctx.resolve_read(inp.from_path or "")
    content = source_file.read_bytes()[: inp.max_file_bytes].decode("utf-8", errors="replace")
    uri = source_file.as_uri()
    proc = subprocess.Popen(
        [command, "--stdio"],
        cwd=ctx.root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline_seconds = max(inp.timeout_ms / 1000, 0.1)
        _send_lsp(proc, 1, "initialize", {"rootUri": ctx.root.as_uri(), "capabilities": {}})
        _read_lsp_response(proc, 1, timeout_seconds=deadline_seconds)
        _send_lsp(proc, None, "initialized", {})
        _send_lsp(
            proc,
            None,
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": content,
                }
            },
        )
        _send_lsp(
            proc,
            2,
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": (inp.line or 1) - 1, "character": inp.column or 0},
                "context": {"includeDeclaration": inp.include_declaration},
            },
        )
        response = _read_lsp_response(proc, 2, timeout_seconds=deadline_seconds)
        result = response.get("result")
        return _lsp_reference_locations_to_matches(ctx, result, inp)
    finally:
        try:
            _send_lsp(proc, 3, "shutdown", None)
            _send_lsp(proc, None, "exit", None)
        except Exception:
            pass
        proc.kill()


def _send_lsp(proc: subprocess.Popen, request_id: int | None, method: str, params: object) -> None:
    if proc.stdin is None:
        raise RuntimeError("lsp stdin unavailable")
    payload: dict[str, object] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    proc.stdin.flush()


def _read_lsp_response(proc: subprocess.Popen, request_id: int, *, timeout_seconds: float) -> dict[str, object]:
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_read_lsp_response_blocking, proc, request_id)
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        proc.kill()
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _read_lsp_response_blocking(proc: subprocess.Popen, request_id: int) -> dict[str, object]:
    while True:
        message = _read_lsp_message(proc)
        if message.get("id") == request_id:
            return message


def _read_lsp_message(proc: subprocess.Popen) -> dict[str, object]:
    if proc.stdout is None:
        raise RuntimeError("lsp stdout unavailable")
    headers: dict[str, str] = {}
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("lsp closed stdout")
        if line in {b"\r\n", b"\n"}:
            break
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    raw = proc.stdout.read(length)
    return json.loads(raw.decode("utf-8"))


def _lsp_locations_to_matches(
    ctx: ToolContext,
    result: object,
    inp: LspDefinitionInput,
) -> list[LspDefinitionMatch]:
    raw_locations = result if isinstance(result, list) else [result]
    matches: list[LspDefinitionMatch] = []
    for raw in raw_locations:
        if not isinstance(raw, dict):
            continue
        location = raw.get("targetUri") and {"uri": raw.get("targetUri"), "range": raw.get("targetRange")}
        if location is None:
            location = raw
        uri = location.get("uri")
        range_obj = location.get("range")
        if not isinstance(uri, str) or not isinstance(range_obj, dict):
            continue
        path = _path_from_uri(uri)
        if path is None:
            continue
        source_path = ctx.resolve_read(ctx.relpath(path))
        text = source_path.read_bytes()[: inp.max_file_bytes].decode("utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        start = range_obj.get("start")
        if not isinstance(start, dict):
            continue
        line = int(start.get("line") or 0) + 1
        node = _definition_node_at_line(tree, line)
        if node is None:
            continue
        matches.append(_match(ctx, source_path, text.splitlines(), node, inp.query, symbol=_node_symbol(tree, node), engine="pyright_lsp", confidence=0.9))
        if len(matches) >= inp.max_matches:
            break
    return matches


def _lsp_reference_locations_to_matches(
    ctx: ToolContext,
    result: object,
    inp: LspReferencesInput,
) -> list[LspReferenceMatch]:
    raw_locations = result if isinstance(result, list) else [result]
    matches: list[LspReferenceMatch] = []
    seen: set[tuple[str, int, int, str]] = set()
    for raw in raw_locations:
        if not isinstance(raw, dict):
            continue
        uri = raw.get("uri")
        range_obj = raw.get("range")
        if not isinstance(uri, str) or not isinstance(range_obj, dict):
            continue
        path = _path_from_uri(uri)
        if path is None:
            continue
        try:
            source_path = ctx.resolve_read(ctx.relpath(path))
        except Exception:
            continue
        rel = ctx.relpath(source_path)
        if inp.glob and not (fnmatch.fnmatch(source_path.name, inp.glob) or fnmatch.fnmatch(rel, inp.glob)):
            continue
        text = source_path.read_bytes()[: inp.max_file_bytes].decode("utf-8", errors="replace")
        line_start, line_end = _lsp_range_lines(range_obj)
        match = _reference_match(
            ctx,
            source_path,
            text.splitlines(),
            line_start,
            line_end,
            inp.query,
            symbol=_reference_symbol(inp.query),
            engine="pyright_lsp",
            confidence=0.86,
        )
        key = (match.source_path, match.line_range["start"], match.line_range["end"], match.symbol or "")
        if key in seen:
            continue
        seen.add(key)
        matches.append(match)
        if len(matches) >= inp.max_matches:
            break
    return matches


def _lsp_range_lines(range_obj: dict) -> tuple[int, int]:
    start = range_obj.get("start")
    end = range_obj.get("end")
    start_raw = start.get("line") if isinstance(start, dict) else 0
    end_raw = end.get("line") if isinstance(end, dict) else start_raw
    start_line = int(start_raw if isinstance(start_raw, int) else 0) + 1
    end_line = int(end_raw if isinstance(end_raw, int) else start_line - 1) + 1
    return max(start_line, 1), max(end_line, start_line)


def _path_from_uri(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path)).resolve()


def _definition_with_python_ast(
    ctx: ToolContext,
    base: Path,
    inp: LspDefinitionInput,
) -> list[LspDefinitionMatch]:
    matches: list[LspDefinitionMatch] = []
    for path in _iter_files(base):
        rel = ctx.relpath(path)
        if inp.glob and not (fnmatch.fnmatch(path.name, inp.glob) or fnmatch.fnmatch(rel, inp.glob)):
            continue
        text = path.read_bytes()[: inp.max_file_bytes].decode("utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            symbol = _node_symbol(tree, node)
            if inp.query not in {node.name, symbol}:
                continue
            matches.append(
                _match(
                    ctx,
                    path,
                    lines,
                    node,
                    inp.query,
                    symbol=symbol,
                    engine="python_ast_fallback",
                    confidence=0.72,
                )
            )
            if len(matches) >= inp.max_matches:
                return matches
    return matches


def _references_with_python_ast(
    ctx: ToolContext,
    base: Path,
    inp: LspReferencesInput,
) -> list[LspReferenceMatch]:
    token = _reference_symbol(inp.query)
    matches: list[LspReferenceMatch] = []
    seen: set[tuple[str, int, int, str]] = set()
    for path in _iter_files(base):
        rel = ctx.relpath(path)
        if inp.glob and not (fnmatch.fnmatch(path.name, inp.glob) or fnmatch.fnmatch(rel, inp.glob)):
            continue
        text = path.read_bytes()[: inp.max_file_bytes].decode("utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not _is_reference_node(node, token):
                continue
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            match = _reference_match(
                ctx,
                path,
                lines,
                start,
                end,
                inp.query,
                symbol=token,
                engine="python_ast_fallback",
                confidence=0.62,
            )
            key = (match.source_path, match.line_range["start"], match.line_range["end"], match.symbol or "")
            if key in seen:
                continue
            seen.add(key)
            matches.append(match)
            if len(matches) >= inp.max_matches:
                return matches
    return matches


def _reference_symbol(query: str) -> str:
    return query.rsplit(".", 1)[-1]


def _is_reference_node(node: ast.AST, token: str) -> bool:
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Load) and node.id == token
    if isinstance(node, ast.Attribute):
        return isinstance(node.ctx, ast.Load) and node.attr == token
    return False


def _node_symbol(tree: ast.AST, target: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if item is target and isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return f"{node.name}.{item.name}"
    return getattr(target, "name", "")


def _definition_node_at_line(tree: ast.AST, line: int) -> ast.AST | None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start)
        if start <= line <= end:
            return node
    return None


def _match(
    ctx: ToolContext,
    path: Path,
    lines: list[str],
    node: ast.AST,
    query: str,
    *,
    symbol: str,
    engine: str,
    confidence: float,
) -> LspDefinitionMatch:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    decorators = getattr(node, "decorator_list", [])
    if decorators:
        start = min(start, min(decorator.lineno for decorator in decorators))
    segment = "\n".join(lines[start - 1 : end])
    source_path = ctx.relpath(path)
    content_hash = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    return LspDefinitionMatch(
        source_path=source_path,
        line_range={"start": start, "end": end},
        matched_text=segment,
        symbol=symbol,
        content_hash=content_hash,
        trace_id=_trace_id(query, source_path, symbol, start, end, content_hash),
        confidence=confidence,
        engine=engine,  # type: ignore[arg-type]
        metadata={} if engine == "pyright_lsp" else {"fallback_reason": "lsp_unavailable"},
    )


def _reference_match(
    ctx: ToolContext,
    path: Path,
    lines: list[str],
    start: int,
    end: int,
    query: str,
    *,
    symbol: str,
    engine: str,
    confidence: float,
) -> LspReferenceMatch:
    start = max(start, 1)
    end = max(end, start)
    segment = "\n".join(lines[start - 1 : end])
    source_path = ctx.relpath(path)
    content_hash = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    return LspReferenceMatch(
        source_path=source_path,
        line_range={"start": start, "end": end},
        matched_text=segment,
        symbol=symbol,
        content_hash=content_hash,
        trace_id=_reference_trace_id(query, source_path, symbol, start, end, content_hash),
        confidence=confidence,
        engine=engine,  # type: ignore[arg-type]
        metadata={} if engine == "pyright_lsp" else {"fallback_reason": "lsp_unavailable"},
    )


def _iter_files(base: Path) -> list[Path]:
    if base.is_file():
        return [base]
    files: list[Path] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _IGNORE for part in path.parts):
            continue
        files.append(path)
    return files


def _trace_id(*parts: object) -> str:
    raw = "\0".join(str(part) for part in parts)
    return "lsp-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _reference_trace_id(*parts: object) -> str:
    raw = "\0".join(str(part) for part in parts)
    return "lsp-ref-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
