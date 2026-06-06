from app.schemas.tools import AnalyzeProjectInput
from app.tools import analyze_project
from app.tools.base import ToolContext

SAMPLE = '''
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class UserCreate(BaseModel):
    name: str


@router.get("/users/{uid}")
def get_user(uid: int):
    return {"id": uid}


@router.post("/users")
def create_user(body: UserCreate):
    return body
'''

# 带 prefix 的 router + path= keyword 写法
PREFIX_SAMPLE = '''
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/items")
def list_items():
    return []


@router.get(path="/items/{iid}")
def get_item(iid: int):
    return iid
'''

INCLUDE_SAMPLE = '''
from fastapi import FastAPI

from .items import router

app = FastAPI()
app.include_router(router, prefix="/svc")
'''


def _ctx(tmp_path):
    return ToolContext(root=tmp_path, test_write_dir=tmp_path / "tests")


def test_analyze_routes_models_functions(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "users.py").write_text(SAMPLE, encoding="utf-8")
    out = analyze_project(_ctx(tmp_path), AnalyzeProjectInput())

    routes = {(r.method, r.path) for r in out.routes}
    assert ("GET", "/users/{uid}") in routes
    assert ("POST", "/users") in routes
    assert any(m.name == "UserCreate" for m in out.models)
    assert any(f.name == "get_user" for f in out.functions)


def test_analyze_router_prefix_and_path_kw(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "items.py").write_text(PREFIX_SAMPLE, encoding="utf-8")
    out = analyze_project(_ctx(tmp_path), AnalyzeProjectInput())

    routes = {(r.method, r.path) for r in out.routes}
    assert ("GET", "/api/v1/items") in routes  # APIRouter(prefix=) 合并
    assert ("GET", "/api/v1/items/{iid}") in routes  # path= keyword + prefix


def test_analyze_include_router_warns(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(INCLUDE_SAMPLE, encoding="utf-8")
    out = analyze_project(_ctx(tmp_path), AnalyzeProjectInput())
    # 跨文件 prefix 没合并这件事必须诚实暴露
    assert any("include_router" in w for w in out.warnings)


def test_analyze_existing_tests_nodeid(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_foo():\n    assert True\n", encoding="utf-8"
    )
    out = analyze_project(_ctx(tmp_path), AnalyzeProjectInput())
    assert out.existing_tests
    nodeids = [t.estimated_nodeid for t in out.existing_tests[0].test_functions]
    assert "tests/test_x.py::test_foo" in nodeids


def test_analyze_warns_on_syntax_error(tmp_path):
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    out = analyze_project(_ctx(tmp_path), AnalyzeProjectInput())
    assert any("broken.py" in w for w in out.warnings)
