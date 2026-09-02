from __future__ import annotations


class DuplicateJobIdempotencyKeyError(Exception):

    def __init__(self, *, employer_id: str, idempotency_key: str):
        super().__init__(
            f"Duplicate job idempotency key for employer_id={employer_id} idempotency_key={idempotency_key}"
        )
        self.employer_id = employer_id
        self.idempotency_key = idempotency_key


class DuplicateJobPostingError(Exception):

    def __init__(self, *, employer_id: str):
        super().__init__(f"Duplicate job posting for employer_id={employer_id}")
        self.employer_id = employer_id

