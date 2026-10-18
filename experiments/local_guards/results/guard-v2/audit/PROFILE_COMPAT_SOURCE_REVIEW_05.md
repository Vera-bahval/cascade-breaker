# Profile compatibility source review05

PASS_SOURCE_AND_PUBLIC_FIXTURE_ONLY. Caller binds __main__.Model to the canonical frozen evaluator class and restores prior binding in finally. Frozen profile sampling/timing/inputs/models stay unchanged; original completion/source/model gates and absolute deadline remain.

Source object graph has only Model as custom serialized root. RuleMap is ephemeral; estimators use sklearn/CatBoost modules. No other analogous custom class references found in source. Actual joblib artifacts were not opened.

Public owner E2E uses real joblib load and frozen profiler against176synthetic rows without fitting. Independent public checks additionally cover prior canonical alias restoration after exception and collision rejection. Actual profiling is root-only.
