# tests/webapp/test_app.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from autodev.webapp.app import create_app

NOW = datetime(2026, 7, 22, 9, 0, 0)


def _work_item(goal: str = "加限流", repo: str = "demo", state: S = S.INTAKE) -> WorkItem:
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef(repo),
        Requirement(goal, repo, (), goal),
        AutonomyDial.all_human(),
        NOW,
    )
    if state is not S.INTAKE:
        wi.transition_to(S.TRIAGE, "stage ok", NOW)
    if state not in (S.INTAKE, S.TRIAGE):
        wi.transition_to(S.CONTEXT, "stage ok", NOW)
    if state is S.FAILED and wi.state is not S.FAILED:
        wi.transition_to(S.FAILED, "failed: boom", NOW)
    return wi


class FakeConsoleService:
    """结构上匹配 `autodev.webapp.app.ConsoleService`, 但不驱动引擎: 直接持有真实
    WorkItem 实例, 好让路由里调用的真实 `view_summary`/`view_detail` 照常工作。
    """

    def __init__(self, items: list[WorkItem] | None = None) -> None:
        self._items: dict[str, WorkItem] = {wi.id.value: wi for wi in (items or [])}

    def create(self, goal: str, repo: str) -> str:
        if not goal or not goal.strip():
            raise ValueError("goal must not be empty")
        if not repo or not repo.strip():
            raise ValueError("repo must not be empty")
        wi = _work_item(goal, repo)
        self._items[wi.id.value] = wi
        return wi.id.value

    def get(self, work_item_id: str) -> WorkItem | None:
        return self._items.get(work_item_id)

    def list(self) -> list[WorkItem]:
        return list(self._items.values())


def _client(service: FakeConsoleService, projects: list[str] | None = None) -> TestClient:
    app = create_app(service, projects=projects if projects is not None else ["demo", "other"])
    return TestClient(app)


def test_get_projects_returns_configured_list() -> None:
    client = _client(FakeConsoleService(), projects=["alpha", "beta"])

    resp = client.get("/api/projects")

    assert resp.status_code == 200
    assert resp.json() == ["alpha", "beta"]


def test_post_workitems_returns_id() -> None:
    client = _client(FakeConsoleService())

    resp = client.post("/api/workitems", json={"goal": "加限流", "repo": "demo"})

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["id"], str) and body["id"]


def test_post_workitems_rejects_empty_goal_or_repo() -> None:
    client = _client(FakeConsoleService())

    resp = client.post("/api/workitems", json={"goal": "", "repo": "demo"})
    assert resp.status_code == 400

    resp = client.post("/api/workitems", json={"goal": "加限流", "repo": ""})
    assert resp.status_code == 400


def test_list_workitems_returns_summaries() -> None:
    wi = _work_item(state=S.CONTEXT)
    client = _client(FakeConsoleService([wi]))

    resp = client.get("/api/workitems")

    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "id": wi.id.value,
            "goal": "加限流",
            "repo": "demo",
            "type": None,
            "state": "CONTEXT",
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
        }
    ]


def test_get_workitem_detail_shape() -> None:
    wi = _work_item(state=S.CONTEXT)
    client = _client(FakeConsoleService([wi]))

    resp = client.get(f"/api/workitems/{wi.id.value}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == wi.id.value
    assert isinstance(body["stages"], list)
    assert body["stages"][0] == {"key": "INTAKE", "label": "需求录入", "status": "done"}
    assert body["context"] is None
    assert body["failure"] is None


def test_get_workitem_unknown_returns_404() -> None:
    client = _client(FakeConsoleService())

    resp = client.get("/api/workitems/does-not-exist")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "work item not found"}


def test_placeholder_page_when_no_frontend_dist(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(tmp_path / "does-not-exist"))
    client = _client(FakeConsoleService())

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
        client = _client(FakeConsoleService())

        resp = client.get("/")

        assert resp.status_code == 200
        assert resp.text == "<html>INDEX</html>"

    def test_unknown_route_falls_back_to_index(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeConsoleService())

        resp = client.get("/workitems/x")

        assert resp.status_code == 200
        assert resp.text == "<html>INDEX</html>"

    def test_asset_file_served(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeConsoleService())

        resp = client.get("/assets/app.js")

        assert resp.status_code == 200
        assert resp.text == "console.log('app')"

    def test_api_not_shadowed_by_catch_all(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeConsoleService(), projects=["demo"])

        resp = client.get("/api/projects")

        assert resp.status_code == 200
        assert resp.json() == ["demo"]

    def test_path_traversal_never_leaks_outside_file(self, monkeypatch, tmp_path: Path) -> None:
        dist = self._dist(tmp_path)
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP SECRET", encoding="utf-8")
        monkeypatch.setenv("AUTODEV_FRONTEND_DIST", str(dist))
        client = _client(FakeConsoleService())

        for path in ("/../secret.txt", "/..%2Fsecret.txt", "/assets/../../secret.txt"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert resp.text == "<html>INDEX</html>", path
            assert "TOP SECRET" not in resp.text, path
