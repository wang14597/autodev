from autodev.domain.enums import WorkspaceMode
from autodev.domain.policies import workspace_mode_for
from autodev.domain.value_objects import RepoStatus


def test_workspace_mode_for():
    assert workspace_mode_for(RepoStatus(True, True)) is WorkspaceMode.REUSE
    assert workspace_mode_for(RepoStatus(False, True)) is WorkspaceMode.FETCH
    assert workspace_mode_for(RepoStatus(False, False)) is WorkspaceMode.CREATE
