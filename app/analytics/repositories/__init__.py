"""Read-only queries that must join tables across domain schemas.

Reserved for metrics a single SQL join answers far better than stitching two
domain results together in Python (e.g. a zillow listing -> underwriting
funnel). Everything else goes through the owning domain's analytics service.
"""
