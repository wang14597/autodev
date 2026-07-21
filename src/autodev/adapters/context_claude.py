from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement, WorkspaceHandle


def _extract_json_objects(text: str) -> list[str]:
    """按出现顺序扫描 text 中所有平衡的顶层 `{...}` 子串。

    模型输出常夹杂散文/代码片段/Markdown 围栏, 例如提示词或示例代码中出现的
    `foo() { return 1; }` 这类花括号。用贪婪正则 `\\{.*\\}` 会从第一个 `{` 直接
    跨到最后一个 `}`, 把这类无关花括号和真正的 JSON 对象一起吞掉, 导致
    json.loads 失败并把一个本来合法的响应误判为"非 JSON"而降级、丢弃
    relevant_files。这里改为逐字符走一遍括号深度(并跳过字符串字面量内的花括号),
    只收集深度归零那一刻对应的完整平衡对象, 交给上层从后往前尝试解析。
    """
    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    objects.append(text[start : i + 1])
                    start = -1
    return objects


class ClaudeContextAdapter:
    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact:
        files, summary = self._collect(requirement, handle)
        files, summary = self._review(files, summary, requirement, handle)
        path = self._persist(handle, files, summary, requirement)
        return ContextArtifact(
            workspace_location=handle.location,
            workspace_label=handle.label,
            context_file=str(path),
        )

    def _collect(
        self, requirement: Requirement, handle: WorkspaceHandle
    ) -> tuple[tuple[str, ...], str]:
        prompt = (
            "你在一个代码仓库工作目录里。只读调查与下述需求相关的代码, "
            '输出 JSON: {"relevant_files":[相对路径...],"summary":"对相关代码的理解摘要"}。'
            "只输出这个 JSON 对象本身, 不要有任何前后说明文字, 也不要用 Markdown 代码围栏包裹。"
            "不要修改任何文件。\n\n需求: " + requirement.goal
        )
        return self._parse(self._runner(prompt, Path(handle.location)))

    def _review(
        self,
        files: tuple[str, ...],
        summary: str,
        requirement: Requirement,
        handle: WorkspaceHandle,
    ) -> tuple[tuple[str, ...], str]:
        return files, summary  # T4 实现真实复核

    def _parse(self, out: str) -> tuple[tuple[str, ...], str]:
        data = self._try_load(out.strip())
        if data is None:
            # 干净的整段 JSON 解析失败(通常因为夹杂了说明文字或代码围栏),
            # 退而扫描所有平衡的顶层 {...} 对象, 从最后一个往前尝试——
            # 模型的最终答案通常是文本里最后出现的那个完整对象。
            for candidate in reversed(_extract_json_objects(out)):
                data = self._try_load(candidate)
                if data is not None:
                    break
        if data is not None:
            files = tuple(str(f) for f in data.get("relevant_files", []))
            return files, str(data.get("summary", ""))
        return (), out  # 降级

    @staticmethod
    def _try_load(candidate: str) -> dict[str, Any] | None:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _persist(
        self,
        handle: WorkspaceHandle,
        files: tuple[str, ...],
        summary: str,
        requirement: Requirement,
    ) -> Path:
        work_item_id = Path(handle.location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"context-{self._id_gen()}.md"
        path.write_text(self._render(files, summary, requirement, handle), encoding="utf-8")
        return path

    def _render(
        self,
        files: tuple[str, ...],
        summary: str,
        requirement: Requirement,
        handle: WorkspaceHandle,
    ) -> str:
        lines = [
            "# 上下文收集结果",
            "",
            f"- 需求: {requirement.goal}",
            f"- 分支: {handle.label}",
            "",
            "## 相关文件",
            "",
        ]
        lines += [f"- `{f}`" for f in files] or ["(无)"]
        lines += ["", "## 摘要", "", summary, ""]
        return "\n".join(lines)
