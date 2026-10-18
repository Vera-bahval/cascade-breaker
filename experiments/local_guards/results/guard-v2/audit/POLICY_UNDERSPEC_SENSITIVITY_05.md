# Public-contract underspecification: post-hoc sensitivity05

Это дополнительный source-contract audit, не новый independent primary. Полный результат на240 наблюдениях, labels, thresholds и методы не изменены.

Критерий фиксирован в исходнике до чтения predictions: имеется prior attempt того же tenant/invoice, submitted_at не позже decision_time, другой idempotency key, transport_outcome=response_timeout либо connection_lost_after_send, reconciliation non-null. Labels, UNKNOWN и ошибки guard не участвуют в отборе.

Отобраны8 наблюдений:4 compliant и4 intervention, все из4 полных пар indeterminate_commit. Complement содержит232 наблюдения (116/116); fully intact cohort содержит те же116 пар/232 наблюдения. Число16 означает все UNKNOWN ExtensionRules и не является числом случаев этой недоопределённой ветки.

Для обоих cohort пересчитаны все7488 исходных arms и отдельный ExtensionRules control, с per-family counts и intact-pair errors. Наборы и полученные counts совпадают. ExtensionRules:116/116 intervention STOP,0/116 compliant STOP,116/116 compliant ALLOW;8 UNKNOWN. Все116 пар имеют обе стороны верными. Эти secondary цифры нельзя подменять primary120/120 и4/120 на240.

Остальные8 UNKNOWN control сохранены в complement. Четыре dimensional_accounting случая требуют cross-currency FX, но native FX contract отсутствует: это консервативная абстенция при нехватке обязательного свидетельства. Сообщение missing tenant_id относится к пустому FX quote, а не отсутствию ID invoice. В четырёх cumulative_exposure случаях поля присутствуют, но ledger имеет status=reserved,kind=settlement: control поддерживает reserved только с kind=reservation; oracle учитывает оба kind для posted/reserved. Это ограничение покрытия наблюдаемой комбинации status/kind, не missing facts и не reconciliation vocabulary. Public schema не задаёт допустимые cross-field combinations. Все восемь intervention-positive и остановлены; никаких post-test repairs не выполнялось.

Ссылки на исходники: v2_contract_rules.py:117–132,233–240,284–291; v2_hidden_dataset.py:65–86; public-independent-contract.json:55,70,77–78. Case IDs и факты: POLICY_UNDERSPEC_CASES_05.json и POLICY_UNDERSPEC_SENSITIVITY_SUMMARY_05.json. Все arm-level secondary counts: POLICY_UNDERSPEC_SENSITIVITY_05.json. Freeze содержит источник и команды воспроизведения.
