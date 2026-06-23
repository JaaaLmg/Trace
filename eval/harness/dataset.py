# 数据集加载 + 变体物化。污染隔离的物理基础：
# - 干净副本与每个变体各自落在独立目录，互不可见；
# - 变体 = 干净快照 + 单点 patch（canonical 是 patch，snapshot 只是派生缓存）；
# - 物化时强校验 patch 命中唯一片段，命不中直接报错，杜绝「惰性 bug」混进数据集。
from __future__ import annotations

import os
import shutil
import stat
import time
from pathlib import Path

from eval.demo.bugs import BUGS, SeededBug

_DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
CLEAN_ROOT = _DEMO_DIR / "clean"
_GENERATED_ARTIFACT_NAMES = {".trace_artifacts", ".trace_junit.xml", ".trace_pytest_report.json"}


def load_bugs() -> list[SeededBug]:
    return list(BUGS)


def get_bug(bug_id: str) -> SeededBug:
    for b in BUGS:
        if b.id == bug_id:
            return b
    raise KeyError(f"未知 bug id：{bug_id}")


def _safe_dest(dest: Path) -> Path:
    # rmtree 防呆：dest 绝不能等于/包含 CLEAN_ROOT 或是文件系统根，否则会端掉源数据/仓库。
    dest = Path(dest).resolve()
    clean = CLEAN_ROOT.resolve()
    if dest == clean or dest in clean.parents or clean in dest.parents or dest == dest.parent:
        raise ValueError(f"危险的物化目标 dest={dest}：不能等于、包含或落在 CLEAN_ROOT 内，也不能是根目录")
    return dest


def _robust_rmtree(path: Path) -> None:
    # Windows 删除刚跑完 pytest 的目录常踩两个坑：① 只读文件 ② 目录句柄延迟释放（杀软/索引）
    # 造成的瞬时 access denied。onerror 给只读文件补写权限再删；外层重试扛瞬时竞态。
    # 真锁住（如前次崩溃残留的句柄）则重试耗尽后如实抛出，不静默吞掉。
    def _on_error(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for i in range(4):
        try:
            shutil.rmtree(path, onerror=_on_error)
            return
        except OSError:
            if i == 3:
                raise
            time.sleep(0.2 * (i + 1))


def materialize_clean(dest: Path) -> Path:
    """把干净 demo 拷到 dest（隔离目录）。返回项目根。"""
    dest = _safe_dest(dest)
    if dest.exists():
        _robust_rmtree(dest)
    shutil.copytree(CLEAN_ROOT, dest, ignore=lambda _src, names: [name for name in names if name in _GENERATED_ARTIFACT_NAMES])
    return dest


def apply_patch(root: Path, bug: SeededBug) -> None:
    """在已物化的项目根上应用单点 patch。命不中唯一片段就抛错。"""
    target = Path(root) / bug.file
    text = target.read_text(encoding="utf-8")
    count = text.count(bug.old)
    if count != 1:
        raise ValueError(f"bug {bug.id} 的 old 片段在 {bug.file} 中命中 {count} 次（要求恰好 1 次）")
    target.write_text(text.replace(bug.old, bug.new, 1), encoding="utf-8")


def materialize_variant(bug: SeededBug, dest: Path) -> Path:
    """把干净 demo 拷到 dest 并应用该 bug 的 patch，得到变体快照。返回项目根。"""
    root = materialize_clean(dest)
    apply_patch(root, bug)
    return root
