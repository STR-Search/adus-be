"""Shared discussion threads and comments (``discussions`` schema).

Domains link their entities to threads through their own link tables (e.g.
``iron_bank.underwriting_threads``) and talk to this package only through its
service. This package never imports a domain.
"""
