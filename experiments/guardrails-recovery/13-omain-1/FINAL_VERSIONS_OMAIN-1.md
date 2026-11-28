# OMAIN-1: финальные версии файлов

22.11.2026. Согласование завершено, статистика пересчитана по окончательным решениям Анастасии.
Пути — от `CascadeLab/iv_lab/analysis/OMAIN-1/`. Любое последующее изменение — новой версией с новой записью здесь.

## Исходные разметки — не менялись

| файл | строк | SHA-256 |
|---|---|---|
| `blind/coder1_payments_FILLED.csv` | 750 | `62381dad56d5156d318d984c66a97c1e34379a81ec657515d17a09519485f537` |
| `blind/coder1_fraud_FILLED.csv` | 100 | `64f842ff2a5239705c73a086c0093116dc5342bb5c2629edd5911d307b3a63c0` |
| `blind/coder2_payments_selfaudit.csv` | 150 | `58ff1b92b31c956a4a5f21873378530231cf7ef21806145799ee596500cf5e81` |
| `blind/coder2_fraud_selfaudit.csv` | 20 | `1b323964da01c6f9b9f2e53d4ebe5134f6d50e16df817e4edf925c40855ffa56` |
| `KEY_CLOSED/key_blind_to_run.csv` | 750 | `23b7f7af4ab9cdf5437d9fd4309ac208eaba04082168c8fbe935a1caaedb5287` |

## Согласованная разметка (финал)

| файл | строк | SHA-256 |
|---|---|---|
| `reconciled/reconciled_payments.csv` | 750 | `de720abe0449f8733b5c1eac786ff24dbebb6718e986d7be22cfb961933c2956` |
| `reconciled/reconciled_fraud.csv` | 100 | `dc21ad8411472378e56ec4a9af075e8e29a77d068043abb6f236dadcde64df10` |
| `reconciled/reconciliation_log.csv` | 127 | `b52112e228ef3142b8ce5da4d36485fd7efb5b930dea57880b6bb61bad87db59` |
| `reconciled/overlap_resolution.csv` | 172 | `763d08c1083aa69ed59ec1a53f183c85ed79bbf92a86619ff29bd562af149c71` |
| `reconciled/reconcile.py` |  | `a3228237b125641bad3edb2514cbe5db558412fc195f4fcb50ac14fd49b78c13` |
| `reconciled/СОГЛАСОВАНИЕ_OMAIN-1.md` |  | `ebed254d8981a44c19c6eb4a814fc1265d34b02140cb6f84c4d5e70bd16afa35` |

## Статистика (финал)

| файл | строк | SHA-256 |
|---|---|---|
| `stats/baseline_comparison.csv` | 16 | `fabe064d55180a156d3e4d5a5513682a22accf4d8c8b428ed1c2220a2938f906` |
| `stats/statistical_tests.csv` | 63 | `c2fc58905ee25dc847e4c7cb819e73eefded761de9f674863293779213f2f04a` |
| `stats/secondary_outcomes.csv` | 14 | `1c34617f1825955684a18b04255414bd8eed886865e451a0bbc83b156c5efca8` |
| `stats/fraud_decisions.csv` | 4 | `a7652b1154987d350d13db6ea0e934d58483c711d7b4f77d4e770870022a381b` |
| `stats/m1_m3_k4e.csv` | 16 | `84e0668e6447cc37d5a2a5744fc7dff01568bf7a77f98d3cd9677bf57fed908a` |
| `stats/sensitivity.csv` | 140 | `7b6e152cc3dae03a73aacdb434789b50aeb1dc27af2af9240843e923c0dd4e27` |
| `stats/sensitivity_secondary.csv` | 14 | `95a0163e27bfd6d397f8d089cf30828cb753c8835ac38e29f4b1e5f9f66fa493` |
| `stats/omain1_stats.py` |  | `aee10bb2cea1e742d796271cc1721c821d166bf3227cda8e658cfd208549b238` |
| `stats/ОМAIN-1_ИТОГОВАЯ_СТАТИСТИКА.md` |  | `4ee2bc091323483b48661ebc54bae75ad2cbe55124dd33fe522b46f1fca0aa6d` |
| `stats/ОМAIN-1_РЕЗУЛЬТАТЫ_ДЛЯ_КУРСОВОГО.md` |  | `5276ffd5f7962c7b9e430f442bce8b6159b16f7e3657c2565c63672fb1eb98c8` |

## Пересчёт

```bash
cd CascadeLab/iv_lab/analysis/OMAIN-1/reconciled && python3 reconcile.py
cd ../stats && python3 omain1_stats.py
```

Оба скрипта только читают исходные файлы. `reconcile.py` проверяет хеши исходных разметок до и после работы.

## Публикационная правка атрибуции (28.11.2026)

В публикуемых копиях двух текстов добавлены только пометки «разметчик 1 — Claude (ИИ)» (шапка и метки у фраз от первого
лица); данные, метки и выводы не менялись. Исходные версии остаются проверяемыми по хешам выше.

| файл | исходный sha256 | публикуемая копия sha256 |
|---|---|---|
| `reconciled/СОГЛАСОВАНИЕ_OMAIN-1.md` | `ebed254d8981a44c19c6eb4a814fc1265d34b02140cb6f84c4d5e70bd16afa35` | `929b9aed0c8712828025fb89a31346826f38e9ff73b516722d370dd114871696` |
| `agreement/СОГЛАСИЕ_и_расхождения_OMAIN-1.md` | `c138d60b42fe18563efaa43f995b7c7fe513a70ce4570470f8a153560a25a195` (вне списка выше) | `54576779ba86b1f1cecc8cba57666365389aead56018435dbd3841d9d87856cb` |
