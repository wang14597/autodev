# tests/webapp/test_app.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from autodev.domain.enums import GatePoint
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import ProjectId, WorkItemId
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from autodev.webapp.app import create_app

NOW = datetime(2026, 7, 24, 9, 0, 0)


def _project(name: str = "demo", repo_source: str | None = None) -> Project:
    p = Project.create(ProjectId.new(), name, repo_source or f"git@host:team/{name}.git", "", NOW)
    p.mark_prepared("main", NOW)
    return p


def _work_item(project: Project, goal: str = "加限流", state: S = S.INTAKE) -> WorkItem:
    """构造合法转移到 `state` 的工作项(与 tests/webapp/test_views.py 的同名 helper 同风格)。

    覆盖 TRIAGE/CONTEXT/DESIGN/REVIEW/WAIT_HUMAN/DONE/FAILED——早前版本在 CONTEXT
    之后静默截断, 请求 DESIGN/DONE 的调用方会拿到一个 CONTEXT 工作项而不自知。
    """
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef(project.name),
        Requirement(goal, project.name, (), goal),
        AutonomyDial.all_human(),
        NOW,
        project_id=project.id,
    )
    if state is not S.INTAKE:
        wi.transition_to(S.TRIAGE, "stage ok", NOW)
    if state not in (S.INTAKE, S.TRIAGE):
        wi.transition_to(S.CONTEXT, "stage ok", NOW)
    if state not in (S.INTAKE, S.TRIAGE, S.CONTEXT, S.WAIT_HUMAN, S.DONE):
        wi.transition_to(S.DESIGN, "stage ok", NOW)
    if state is S.REVIEW:
        wi.transition_to(S.REVIEW, "stage ok", NOW)
    if state is S.WAIT_HUMAN:
        wi.suspend(GatePoint.CONTEXT_GATE, "context", NOW)
    if state is S.DONE:
        wi.transition_to(S.DONE, "collect only", NOW)
    if state is S.FAILED and wi.state is not S.FAILED:
        wi.transition_to(S.FAILED, "failed: boom", NOW)
    return wi


class FakeProjectConsoleService:
    """结构上匹配 `autodev.webapp.app.ConsoleService`, 但不驱动引擎: 直接持有真实
    Project/WorkItem 实例, 好让路由里调用的真实 view_project/view_project_detail/
    view_detail 照常工作。
    """

    def __init__(
        self,
        projects: list[Project] | None = None,
        workitems: list[WorkItem] | None = None,
        advance_raises: bool = False,
        implemented_stages: frozenset[S] | None = None,
    ) -> None:
        self._projects: dict[str, Project] = {p.id.value: p for p in (projects or [])}
        self._workitems: dict[str, WorkItem] = {wi.id.value: wi for wi in (workitems or [])}
        self.advance_raises = advance_raises
        self._implemented_stages = implemented_stages

    def _count(self, project_id: str) -> int:
        return sum(
            1
            for wi in self._workitems.values()
            if wi.project_id is not None and wi.project_id.value == project_id
        )

    def create_project(self, name: str, repo_input: str, branch: str = "") -> str:
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        if not repo_input or not repo_input.strip():
            raise ValueError("repo_input must not be empty")
        if any(p.name == name for p in self._projects.values()):
            raise ValueError("项目名已存在")
        p = _project(name, repo_input)
        if branch:
            p.mark_prepared(branch, NOW)
        self._projects[p.id.value] = p
        return p.id.value

    def list_projects(self) -> list[tuple[Project, int]]:
        return [(p, self._count(p.id.value)) for p in self._projects.values()]

    def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def refresh_project(self, project_id: str) -> str:
        p = self._projects.get(project_id)
        if p is None:
            raise LookupError(project_id)
        p.mark_prepared("develop", NOW)
        return "develop"

    def list_branches(self, project_id: str) -> list[str]:
        p = self._projects.get(project_id)
        if p is None:
            raise LookupError(project_id)
        return ["main", "develop"]

    def set_project_branch(self, project_id: str, branch: str) -> str:
        p = self._projects.get(project_id)
        if p is None:
            raise LookupError(project_id)
        if branch not in ("main", "develop"):
            raise ValueError(f"分支不存在: {branch}")
        p.mark_prepared(branch, NOW)
        return branch

    def delete_project(self, project_id: str) -> bool:
        p = self._projects.pop(project_id, None)
        if p is None:
            return False
        for wid in [
            wid
            for wid, wi in self._workitems.items()
            if wi.project_id is not None and wi.project_id.value == project_id
        ]:
            del self._workitems[wid]
        return True

    def create_workitem(self, project_id: str, goal: str, autonomy_enabled: bool = False) -> str:
        if not goal or not goal.strip():
            raise ValueError("goal must not be empty")
        p = self._projects.get(project_id)
        if p is None:
            raise LookupError(project_id)
        wi = _work_item(p, goal)
        self._workitems[wi.id.value] = wi
        return wi.id.value

    def list_workitems(self, project_id: str) -> list[WorkItem]:
        return [
            wi
            for wi in self._workitems.values()
            if wi.project_id is not None and wi.project_id.value == project_id
        ]

    def get_workitem(self, work_item_id: str) -> WorkItem | None:
        return self._workitems.get(work_item_id)

    def approve_workitem(self, work_item_id: str, approved: bool = True) -> WorkItem | None:
        return self._workitems.get(work_item_id)

    def decide_workitem(self, work_item_id: str, decision: str) -> WorkItem | None:
        return self._workitems.get(work_item_id)

    def advance_workitem(self, work_item_id: str) -> WorkItem | None:
        if self.advance_raises and work_item_id in self._workitems:
            from autodev.domain.errors import InvariantError

            raise InvariantError("cannot advance work item stopped by TERMINAL")
        return self._workitems.get(work_item_id)

    @property
    def implemented_stages(self) -> frozenset[S]:
        if self._implemented_stages is not None:
            return self._implemented_stages
        from autodev.webapp.drive import IMPLEMENTED_STAGES

        return IMPLEMENTED_STAGES


def _client(service: FakeProjectConsoleService) -> TestClient:
    app = create_app(service)
    return TestClient(app)


def test_get_projects_returns_list_with_counts() -> None:
    p1 = _project("demo1")
    p2 = _project("demo2")
    wi = _work_item(p1)
    client = _client(FakeProjectConsoleService([p1, p2], [wi]))

    resp = client.get("/api/projects")

    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "id": p1.id.value,
            "name": "demo1",
            "repo_source": "git@host:team/demo1.git",
            "branch": "main",
            "workitem_count": 1,
            "created_at": NOW.isoformat(),
        },
        {
            "id": p2.id.value,
            "name": "demo2",
            "repo_source": "git@host:team/demo2.git",
            "branch": "main",
            "workitem_count": 0,
            "created_at": NOW.isoformat(),
        },
    ]


def test_post_projects_returns_id() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.post("/api/projects", json={"name": "demo", "repo": "git@host:team/demo.git"})

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["id"], str) and body["id"]


def test_post_projects_accepts_explicit_branch() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.post(
        "/api/projects",
        json={"name": "demo", "repo": "git@host:team/demo.git", "branch": "feature/x"},
    )

    assert resp.status_code == 200
    project_id = resp.json()["id"]
    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["branch"] == "feature/x"


def test_post_projects_rejects_empty_name_or_repo() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.post("/api/projects", json={"name": "", "repo": "git@host:team/demo.git"})
    assert resp.status_code == 400

    resp = client.post("/api/projects", json={"name": "demo", "repo": ""})
    assert resp.status_code == 400


def test_post_projects_rejects_duplicate_name() -> None:
    client = _client(FakeProjectConsoleService([_project("demo")]))

    resp = client.post("/api/projects", json={"name": "demo", "repo": "git@host:team/demo.git"})

    assert resp.status_code == 400


def test_get_project_detail_shape() -> None:
    p = _project("demo")
    wi = _work_item(p, state=S.CONTEXT)
    client = _client(FakeProjectConsoleService([p], [wi]))

    resp = client.get(f"/api/projects/{p.id.value}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == p.id.value
    assert body["name"] == "demo"
    assert body["branch"] == "main"
    assert body["workitem_count"] == 1
    assert isinstance(body["workitems"], list)
    assert body["workitems"][0]["id"] == wi.id.value


def test_get_project_unknown_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.get("/api/projects/does-not-exist")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "project not found"}


def test_post_project_refresh_returns_branch() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.post(f"/api/projects/{p.id.value}/refresh")

    assert resp.status_code == 200
    assert resp.json() == {"branch": "develop"}


def test_post_project_refresh_unknown_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.post("/api/projects/does-not-exist/refresh")

    assert resp.status_code == 404


def test_get_project_branches_returns_list() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.get(f"/api/projects/{p.id.value}/branches")

    assert resp.status_code == 200
    assert resp.json() == ["main", "develop"]


def test_get_project_branches_unknown_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.get("/api/projects/does-not-exist/branches")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "project not found"}


def test_post_project_branch_switches_and_returns_branch() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.post(f"/api/projects/{p.id.value}/branch", json={"branch": "develop"})

    assert resp.status_code == 200
    assert resp.json() == {"branch": "develop"}


def test_post_project_branch_rejects_unknown_branch() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.post(f"/api/projects/{p.id.value}/branch", json={"branch": "no-such-branch"})

    assert resp.status_code == 400


def test_post_project_branch_unknown_project_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.post("/api/projects/does-not-exist/branch", json={"branch": "develop"})

    assert resp.status_code == 404


def test_delete_project_returns_deleted_true() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.delete(f"/api/projects/{p.id.value}")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}


def test_delete_project_unknown_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.delete("/api/projects/does-not-exist")

    assert resp.status_code == 404


def test_post_project_workitems_returns_id() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.post(f"/api/projects/{p.id.value}/workitems", json={"goal": "加限流"})

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["id"], str) and body["id"]


def test_post_project_workitems_rejects_empty_goal() -> None:
    p = _project("demo")
    client = _client(FakeProjectConsoleService([p]))

    resp = client.post(f"/api/projects/{p.id.value}/workitems", json={"goal": ""})

    assert resp.status_code == 400


def test_post_project_workitems_unknown_project_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.post("/api/projects/does-not-exist/workitems", json={"goal": "加限流"})

    assert resp.status_code == 404


def test_get_workitem_detail_shape() -> None:
    p = _project("demo")
    wi = _work_item(p, state=S.CONTEXT)
    client = _client(FakeProjectConsoleService([p], [wi]))

    resp = client.get(f"/api/workitems/{wi.id.value}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == wi.id.value
    assert isinstance(body["stages"], list)
    assert body["stages"][0] == {"key": "INTAKE", "label": "需求录入", "status": "done"}
    assert body["context"] is None
    assert body["failure"] is None


def test_get_workitem_unknown_returns_404() -> None:
    client = _client(FakeProjectConsoleService())

    resp = client.get("/api/workitems/does-not-exist")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "work item not found"}


def test_placeholder_page_when_no_frontend_dist(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(tmp_path / "does-not-exist"))
    client = _client(FakeProjectConsoleService())

    resp = client.get("/")

    assert resp.status_code == 200
    assert "前端尚未构建" in resp.text


class TestSpaHosting:
    def _dist(self, tmp_path: Path) -> Path:
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
        return dist

    def test_root_serves_index(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeProjectConsoleService())

        resp = client.get("/")

        assert resp.status_code == 200
        assert resp.text == "<html>INDEX</html>"

    def test_unknown_route_falls_back_to_index(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeProjectConsoleService())

        resp = client.get("/projects/x")

        assert resp.status_code == 200
        assert resp.text == "<html>INDEX</html>"

    def test_asset_file_served(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeProjectConsoleService())

        resp = client.get("/assets/app.js")

        assert resp.status_code == 200
        assert resp.text == "console.log('app')"

    def test_api_not_shadowed_by_catch_all(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeProjectConsoleService([_project("demo")]))

        resp = client.get("/api/projects")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_path_traversal_never_leaks_outside_file(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET", encoding="utf-8")
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeProjectConsoleService())

        for path in ("/../secret.txt", "/..%2Fsecret.txt", "/assets/../../secret.txt"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert resp.text == "<html>INDEX</html>", path
            assert "TOP SECRET" not in resp.text, path


def test_advance_endpoint_returns_detail() -> None:
    project = _project()
    wi = _work_item(project, state=S.DESIGN)
    client = _client(FakeProjectConsoleService([project], [wi]))

    response = client.post(f"/api/workitems/{wi.id.value}/advance")

    assert response.status_code == 200
    # DESIGN ∈ 生产默认能力集合，手动挡（默认 autonomy_enabled=False）下的搁浅态 →
    # next_action 必须精确是 "advance"，而不是"四态之一"这种恒真断言。
    assert response.json()["next_action"] == "advance"


def test_advance_endpoint_threads_service_capability_set() -> None:
    """`/advance` 必须用 `service.implemented_stages`，不能悄悄退回生产默认集合。

    fake 的能力集合特意排除 DESIGN（生产默认 IMPLEMENTED_STAGES 是包含的），工作项
    停在 DESIGN。若路由把 `service.implemented_stages` 传参丢了、view_detail 退回
    默认集合，DESIGN 就会被当作"已建设"从而判成 advance —— 断言必须精确到
    "blocked"/"方案"，而不是宽松的集合成员判断，才能捕获这类回归。
    """
    project = _project()
    wi = _work_item(project, state=S.DESIGN)
    restricted = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT})
    client = _client(FakeProjectConsoleService([project], [wi], implemented_stages=restricted))

    response = client.post(f"/api/workitems/{wi.id.value}/advance")

    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "blocked"
    assert body["next_stage"] == "方案"


def test_advance_endpoint_404_when_missing() -> None:
    client = _client(FakeProjectConsoleService())
    assert client.post("/api/workitems/nope/advance").status_code == 404


def test_advance_endpoint_409_when_illegal_state() -> None:
    """非法态（终态 / 待门禁 / 未建设）→ 409，而非 400/500，也绝不静默 200。"""
    project = _project()
    wi = _work_item(project, state=S.DONE)
    client = _client(FakeProjectConsoleService([project], [wi], advance_raises=True))

    assert client.post(f"/api/workitems/{wi.id.value}/advance").status_code == 409
