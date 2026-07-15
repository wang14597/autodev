from enum import Enum, auto

class TaskType(Enum):
    SMALL_CHANGE = auto()
    MEDIUM_FEATURE = auto()
    COMPLEX_FEATURE = auto()

class WorkflowState(Enum):
    INTAKE = auto()
    TRIAGE = auto()
    CONTEXT = auto()
    DESIGN = auto()
    REVIEW = auto()
    IMPL = auto()
    ACCEPT = auto()
    VERIFY = auto()
    SUBMIT_MR = auto()
    DONE = auto()
    WAIT_HUMAN = auto()
    FAILED = auto()

class WorkspaceMode(Enum):
    REUSE = auto()
    FETCH = auto()
    CREATE = auto()

class GatePoint(Enum):
    REVIEW_GATE = auto()
    MERGE_GATE = auto()

class FailureKind(Enum):
    TRANSIENT = auto()
    LOGIC = auto()
    FATAL = auto()
