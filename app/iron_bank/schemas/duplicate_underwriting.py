from uuid import UUID

from pydantic import BaseModel


class DuplicateUnderwritingResult(BaseModel):
    """Identity of the newly created copy.

    The client redirects to ``underwriting_id``; ``series_id``/``version`` let it
    label the copy without a follow-up read.
    """

    underwriting_id: int
    series_id: UUID
    version: int
    copied_from_id: int
