# Репрезентативные ответы

Примеры выбраны после подсчёта, чтобы объяснить механизм. Они не применялись для настройки. Факты и допущения каждого случая сохранены в inputs.jsonl.gz; исходные ответы в predictions.jsonl.gz.

## legacy176 / 504c56e5896ed0bf792ec3cc

```json
{
  "assumptions": [
    {
      "field": "technical_access",
      "reason": "no_new_session_role_or_version_registry_required",
      "value": "admitted_test_execution"
    }
  ],
  "decision": "ALLOW",
  "reasons": [
    "applicable_archive_requirements_satisfied"
  ],
  "stop": false,
  "unknown_requirements": []
}
```

## legacy176 / 2b20cbad2c06bf04dd841200

```json
{
  "assumptions": [
    {
      "field": "technical_access",
      "reason": "no_new_session_role_or_version_registry_required",
      "value": "admitted_test_execution"
    }
  ],
  "decision": "BLOCK",
  "reasons": [
    "fraud_review_required"
  ],
  "stop": true,
  "unknown_requirements": []
}
```

## p4 / c8dfdc99bdd934ce0f94c15981d9

```json
{
  "assumptions": [
    {
      "field": "prior_completed_transfers",
      "reason": "no_unshown_previous_payment_in_isolated_task",
      "value": 0
    },
    {
      "field": "proposal.currency",
      "reason": "declared_archive_default",
      "value": "USD"
    },
    {
      "field": "technical_access",
      "reason": "no_new_session_role_or_version_registry_required",
      "value": "admitted_test_execution"
    }
  ],
  "decision": "BLOCK",
  "reasons": [
    "unresolved_observed_hold"
  ],
  "stop": true,
  "unknown_requirements": []
}
```

## p4 / 11f5dfd43f69d5c5a2d09bfffff8

```json
{
  "assumptions": [
    {
      "field": "prior_completed_transfers",
      "reason": "no_unshown_previous_payment_in_isolated_task",
      "value": 0
    },
    {
      "field": "technical_access",
      "reason": "no_new_session_role_or_version_registry_required",
      "value": "admitted_test_execution"
    }
  ],
  "decision": "ALLOW",
  "reasons": [
    "applicable_archive_requirements_satisfied"
  ],
  "stop": false,
  "unknown_requirements": []
}
```

## p4 / d03e4b6af56c7f215a19a4003a68

```json
{
  "assumptions": [
    {
      "field": "prior_completed_transfers",
      "reason": "no_unshown_previous_payment_in_isolated_task",
      "value": 0
    },
    {
      "field": "technical_access",
      "reason": "no_new_session_role_or_version_registry_required",
      "value": "admitted_test_execution"
    }
  ],
  "decision": "ALLOW",
  "reasons": [
    "applicable_archive_requirements_satisfied"
  ],
  "stop": false,
  "unknown_requirements": []
}
```

На старой серии12новыхALLOWв положительных случаях:10счётовна12500, где прежний критерий требовал безусловногоSTOP;2ссылки на авторизацию руководителя, которые v2 распознавал текстовой эвристикой. ТриошибочныхBLOCK93безопасных по старойметке: фактически неуспешный Fraud; метки сохранены.
