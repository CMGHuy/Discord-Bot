# V125-3 report
Witness test committed alone first (PASS on unchanged code, ae7d74bd). Then 13 merge tests failed (12 failed + 3 pass), implemented, 35 passed across the 6 suites in the brief.
- entry_context still C (17) (unchanged). Callers of stamp_entry_context: 3, as brief states.
- test_edge_context_structure.py: one assertion updated to FEATURE_KEYS[20:34].
- No-lookahead review: grep for shift(-n)/center=/iloc[t+..] in location.py and context.py is clean; plan_provenance reads no bars; location_features takes only the passed frame. Forming-bar caveat: live snapshot may end on a forming bar (as v121); no consumer may act on these keys.
