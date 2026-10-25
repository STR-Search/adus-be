"""Append-only history of status changes (``process_log`` schema).

Any domain can record transitions of a named flow (e.g. an underwriting's
``deal_status``) for any subject, through ``ProcessLogService`` only. Subjects
are referenced logically by ``(subject_type, subject_id)`` with no FK, so the
history outlives the subject. This package never imports a domain. Design:
``docs/features/process_log/process_log.md``.
"""
