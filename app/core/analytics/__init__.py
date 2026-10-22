"""Shared, domain-free building blocks for analytics responses.

Response shapes (``schemas``) and ordering rules (``ordering``) that every
domain's analytics service uses, so charts built on one endpoint work on the
next. Like ``app.core.reference_data``, this package never imports a domain:
domain knowledge such as the deal status workflow order is passed in.
"""
