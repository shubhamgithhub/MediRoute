"""Contracts shared by both pipeline steps.

`MedicalContext` is the hand-off object from Step 1 (specialty_routing)
to Step 2 (hospital_recommendation). The two step packages must not import
each other; they may only depend on `mediroute.common` and `mediroute.utils`.
"""
