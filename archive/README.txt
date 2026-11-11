MediRoute archive
=================

Archived on 11 Nov 2026 (branch pravin-data-unify) when Step 1 and Step 2 were moved onto one
shared set of data files. Nothing in this folder is read by the app, the tests or the build
scripts. The files are kept, with their git history (git mv), so earlier work can be traced.

Why
---
The project had grown five hospital lists and three speciality lists. Step 1 and Step 2 read
different ones, so they disagreed:
  * Step 2 searched a 150-hospital sheet in which every hospital was marked "Verified", while the
    verified 100-hospital master (NABH / JCI / website checks) was not used by the app.
  * Step 2's speciality name table had no row for 13 of Step 1's 26 specialities, so for example
    "Neurosciences" (124 hospitals) never reached Neurology, which found 2 hospitals.
  * Field formats differed (evidence quality 2/3 vs High/Medium/Low, NABH Verified vs Accredited),
    and the patient page's "Delhi NCR" choice silently searched all of India.
The comparison behind this is summarised in the README, section "How hospital data is extracted",
and in docs/PROJECT_TRACKER.md.


What was archived, and what replaces it
---------------------------------------
archive/data/processed/hospitals_master.csv
archive/data/processed/hospitals_master_backup.csv
archive/data/raw/SampleData.csv
    Old 25-hospital prototype list (SampleData.csv was tab-separated text in one column).
    REPLACED BY data/processed/hospitals.csv (the one hospital table both steps read),
    built from data/processed/master-hospital-data.csv (verified rows).

archive/data/processed/hospital_verification.csv
    Manual verification sheet for the 25-hospital prototype.
    REPLACED BY the automatic NABH / JCI / website checks in
    src/mediroute/data_generator/build_hospital_master.py; the evidence for every hospital is in
    the nabh_*, jci_*, website_status and source columns of master-hospital-data.csv.

archive/data/medical_taxonomy/specialty_vocabulary.csv
    88 raw speciality labels from the 150-hospital sheet, used only by the old
    SpecialtyRAGRouter (router.py, no longer on the live path).
    REPLACED BY data/medical_taxonomy/specialties.csv (the 26 Step 1 specialities) and
    data/medical_taxonomy/specialty_normalization.csv (every hospital label -> those 26 names,
    including sub-specialities; NONE = not a routing speciality).

archive/code/data_generator/create_master_dataset.py
archive/code/data_generator/create_verification_sheet.py
archive/code/data_generator/merge_verified_hospitals.py
archive/code/data_generator/check_verification_progress.py
    Scripts of the 25-hospital prototype pipeline; they only read the files above.
    REPLACED BY build_hospital_master.py -> merge_master.py -> build_hospitals_table.py.

archive/code/data_generator/build_specialty_vocabulary.py
    Built specialty_vocabulary.csv. REPLACED BY specialty_normalization.csv (maintained by hand,
    draft rows marked draft_rule for doctor review).


Files reused across Step 1 and Step 2 (the current data)
--------------------------------------------------------
data/processed/hospitals.csv              ONE hospital table: Step 2 search index, the /api/cities
                                          list, and Step 1's "do we have hospitals for this
                                          speciality" flag all come from it.
data/processed/master-hospital-data.csv   verified rows it is built from (NABH / JCI / website).
data/processed/hospital_id_links.csv      master id <-> team 150 sheet id (reviewed matches).
data/processed/hospital.schema.csv        column rules for both files above.
data/medical_taxonomy/specialties.csv     the 26 specialities (Step 1 output = Step 2 input).
data/medical_taxonomy/specialty_normalization.csv   hospital labels -> those 26 names.
data/reference/cities.csv                 cities, state, tier and search area (Delhi NCR...).

Kept where they are, on purpose:
data/raw/NewMediRoute_Hospital_Dataset_150.xlsx
    Team 150-hospital sheet. Now an INPUT ONLY: build_hospitals_table.py takes sub-specialities,
    procedures, facilities, languages and cost band from it, marked "team 150 sheet (not
    verified)". Its accreditation and "Verified" values are no longer used. Its hospitals that
    were not in the master were verified with the same pipeline (candidates in
    data/raw/data_generator/candidates_team150/, results in data/interim/master_team150/).
data/medical_taxonomy/icd10_specialty_mapping.csv
    Still serves the /api/icd10/* endpoints (icd10_mapper.py). Step 1 itself uses
    icd10_block_specialty.csv. Candidate for the next clean-up.
data/raw/data_generator/Hosp_Data_Final.xlsx
    CGHS procedure list (Step 1 lookup list) and the team's per-person hospital sheets.
