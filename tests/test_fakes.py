# tests/test_fakes.py
from autodev.domain.artifacts import AcceptanceArtifact
from autodev.domain.enums import WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef, Requirement
from tests.fakes import (
    FakeContext,
    FakeDelivery,
    FakeDesign,
    FakeExecution,
    FakeReview,
    FakeVerification,
    FakeWorkspace,
    RecordingPublisher,
)


def test_fakes_satisfy_ports():
    ws = FakeWorkspace(local=True)
    st = ws.repo_status(RepoRef("repo-a"))
    assert st.exists_local
    h = ws.provision(WorkItemId.new(), RepoRef("repo-a"), WorkspaceMode.REUSE, "br")
    assert h.label == "br"
    ctx = FakeContext().gather(Requirement("g", "repo-a", (), "r"), h)
    d = FakeDesign().propose(Requirement("g", "repo-a", (), "r"), ctx)
    assert FakeReview(approved=True).review(d, ctx).approved
    impl = FakeExecution(test_passed=True).implement(d, h)
    assert impl.test_passed
    ver = FakeVerification(passed=True).verify(AcceptanceArtifact(("c",)), h)
    assert ver.verdict.passed
    dv = FakeDelivery().submit(Requirement("g", "repo-a", (), "r"), d, h)
    assert dv.change_request_url


def test_fake_review_rejection_comment_uses_production_blocking_prefix():
    """FakeReview 打回时的意见须带 `- blocking: ` 前缀，与生产解析约定（`review_claude.py`
    的 `_COMMENT_PREFIXES`）一致，否则依赖假件跑判回退分支的测试会掩盖真实前缀缺失的问题。
    """
    ws = FakeWorkspace(local=True)
    h = ws.provision(WorkItemId.new(), RepoRef("repo-a"), WorkspaceMode.REUSE, "br")
    ctx = FakeContext().gather(Requirement("g", "repo-a", (), "r"), h)
    d = FakeDesign().propose(Requirement("g", "repo-a", (), "r"), ctx)
    art = FakeReview(approved=False).review(d, ctx)
    assert art.approved is False
    assert art.comments
    assert all(c.startswith("- blocking: ") for c in art.comments)


def test_recording_publisher_collects():
    pub = RecordingPublisher()
    from autodev.domain.events import WorkItemCreated

    wid = WorkItemId.new()
    pub.publish(WorkItemCreated(wid))
    assert pub.events and pub.events[0].work_item_id == wid
