"""Service-level errors. Callers map them to HTTP statuses."""


class ProcessLogError(Exception):
    """Base class for errors raised by ``ProcessLogService``."""


class ConcurrentTransitionError(ProcessLogError):
    """Another transaction extended the same chain first (→ 409).

    Raised when an insert hits ``uq_transitions_previous`` (two rows following
    the same tail) or ``uq_transitions_head`` (two heads for one flow). The
    session's transaction is aborted; the caller must roll back.
    """

    def __init__(self, subject_type: str, subject_id: int, flow: str):
        super().__init__(
            f"Concurrent {flow} transition for {subject_type} {subject_id}"
        )
        self.subject_type = subject_type
        self.subject_id = subject_id
        self.flow = flow
