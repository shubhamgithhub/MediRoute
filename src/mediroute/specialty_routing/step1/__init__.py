"""Step 1 voting pipeline: patient text -> suggested speciality to search.

Stages: protect -> emergency check -> evidence -> three voters -> majority decision ->
(clarification form) -> output. See docs/api/step1_analyze_api.md.
"""
