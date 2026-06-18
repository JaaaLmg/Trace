# 工具层对外入口和默认注册表。runtime/strategy 都从这里取工具。
from app.schemas.tools import (
    AnalyzeProjectInput,
    AnalyzeProjectOutput,
    AstGrepSearchInput,
    AstGrepSearchOutput,
    LspDefinitionInput,
    LspDefinitionOutput,
    LspReferencesInput,
    LspReferencesOutput,
    ListFilesInput,
    ListFilesOutput,
    ReadFileInput,
    ReadFileOutput,
    RgSearchInput,
    RgSearchOutput,
    RunPytestInput,
    RunPytestOutput,
    WriteTestFileInput,
    WriteTestFileOutput,
)
from app.tools.analyze import analyze_project
from app.tools.base import ToolContext, ToolRegistry, ToolSpec
from app.tools.fs_tools import list_files, read_file
from app.tools.lsp import lsp_definition, lsp_references
from app.tools.run_pytest import run_pytest
from app.tools.search import ast_grep_search, rg_search
from app.tools.write_test import write_test_file

__all__ = [
    "ToolContext",
    "ToolRegistry",
    "ToolSpec",
    "default_registry",
    "analyze_project",
    "ast_grep_search",
    "list_files",
    "lsp_definition",
    "lsp_references",
    "read_file",
    "rg_search",
    "run_pytest",
    "write_test_file",
]


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec("list_files", ListFilesInput, ListFilesOutput, list_files))
    reg.register(ToolSpec("read_file", ReadFileInput, ReadFileOutput, read_file))
    reg.register(ToolSpec("rg_search", RgSearchInput, RgSearchOutput, rg_search))
    reg.register(ToolSpec("ast_grep_search", AstGrepSearchInput, AstGrepSearchOutput, ast_grep_search))
    reg.register(ToolSpec("lsp_definition", LspDefinitionInput, LspDefinitionOutput, lsp_definition))
    reg.register(ToolSpec("lsp_references", LspReferencesInput, LspReferencesOutput, lsp_references))
    reg.register(ToolSpec("analyze_project", AnalyzeProjectInput, AnalyzeProjectOutput, analyze_project))
    reg.register(ToolSpec("write_test_file", WriteTestFileInput, WriteTestFileOutput, write_test_file))
    reg.register(ToolSpec("run_pytest", RunPytestInput, RunPytestOutput, run_pytest))
    return reg
