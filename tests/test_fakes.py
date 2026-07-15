# tests/test_fakes.py
from autodev.domain.value_objects import RepoRef, Requirement
from autodev.domain.enums import WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.artifacts import AcceptanceArtifact
from tests.fakes import (
    FakeWorkspace, FakeContext, FakeDesign, FakeReview,
    FakeExecution, FakeVerification, FakeDelivery, RecordingPublisher,
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

def test_recording_publisher_collects():
    pub = RecordingPublisher()
    from autodev.domain.events import WorkItemCreated
    wid = WorkItemId.new()
    pub.publish(WorkItemCreated(wid))
    assert pub.events and pub.events[0].work_item_id == wid
