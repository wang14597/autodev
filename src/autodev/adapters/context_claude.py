from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.errors import StageError
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
        prompt = (
            "下面是对本仓库的第一遍上下文收集结果。请对照真实代码核对其相关性/完整性/摘要准确性, "
            "补漏、去无关、修正摘要, 输出改进后的 JSON: "
            '{"relevant_files":[...], "summary":"..."}。'
            "只输出这个 JSON 对象本身, 不要有任何前后说明文字, 也不要用 Markdown 代码围栏包裹。"
            "只读, 不要改文件。\n\n"
            f"需求: {requirement.goal}\n第一遍 relevant_files: {list(files)}\n"
            f"第一遍 summary:\n{summary}"
        )
        try:
            out = self._runner(prompt, Path(handle.location))
        except StageError:
            return files, summary  # 复核失败(重试耗尽) → 降级回第一遍
        data = self._parse_strict(out)
        if data is None:
            # 复核调用成功了, 但没产出可用的 JSON(夹杂说明文字却找不到平衡对象、
            # 或对象里缺 relevant_files 字段)。此时决不能像 _collect 那样把整段
            # 原始文本当 summary、把 relevant_files 清空——那会比"什么都不做"更差:
            # 直接丢弃了第一遍已经收集好的结果。应降级回第一遍, 保留其结果。
            return files, summary
        new_files = tuple(str(f) for f in data.get("relevant_files", []))
        return new_files, str(data.get("summary", ""))

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
        return (), out  # 降级(_collect 场景: 没有"第一遍"可退, 只能退到原始文本)

    def _parse_strict(self, out: str) -> dict[str, Any] | None:
        """严格解析: 只有找到"形状匹配预期"的顶层 JSON 对象才返回该 dict, 否则返回
        None, 交给调用方(目前只有 `_review`)决定如何降级。

        与 `_parse` 共用 `_extract_json_objects` 做括号扫描 + `_try_load` 做
        json.loads, 但不像 `_parse` 那样在找不到有效 JSON 时用原始文本/空
        列表兜底——那是 `_collect` "没有第一遍可退"时的降级语义。`_review` 需要
        区分"复核产出了可用的改进结果"与"复核输出无法解析", 后一种情况必须让
        调用方原样保留第一遍结果, 而不是被这里的默认值污染。
        """
        data = self._try_load(out.strip())
        if data is None:
            for candidate in reversed(_extract_json_objects(out)):
                data = self._try_load(candidate)
                if data is not None:
                    break
        if data is None or not isinstance(data.get("relevant_files"), list):
            return None
        return data

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
