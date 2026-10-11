"""Spotify review insight pipeline (MBA 290T final assignment).

Six stages, each labelled code or model:
  1 ingest  (code)          read CSV, hash rows, profile, deduplicate, queue
  2 enrich  (model + code)  fixed labels per review, validated and saved per review
  3 verify  (model + code)  independent re-label of a declared random sample
  4 group   (code + model)  stable issue membership; a model only names issues
  5 rank    (code)          baseline priority = severity_sum
  6 memo    (model + code)  memo from saved aggregates; code checks every number

Importing this package never makes a network call. Live calls happen only through
`python -m insight run ... --allow-paid` with API keys present.
"""

__version__ = "0.1.0"
