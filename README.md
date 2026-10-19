# cascade-breaker

Исследование контроля каскадов ошибок в мультиагентной системе FinBot.

[Основные результаты и выводы](docs/cheap-guards/README.md) - цифры, сравнение rules, SecJev, CatBoost, Prompt Guard, NLI, MiniCheck и LLM-защитников.

[Позднее сравнение SecJev 4B и 9B](docs/cheap-guards/LARGE-MODELS.md) - архив, шесть новых семейств, задержка и границы вывода о переносе.

- [Как устроены эксперименты](docs/cheap-guards/PROTOCOL.md)
- [История запусков и исправлений](docs/cheap-guards/EXPERIMENTS.md)
- [Что изучили и что осталось проверить](docs/cheap-guards/RESEARCH.md)
- [Артефакты и воспроизведение](docs/cheap-guards/REPRODUCIBILITY.md)
- [Исходники экспериментального стенда](experiments/local_guards/)

Эта ветка публикует результаты дешёвых защитников как продолжение архивных экспериментов коллег. Исходная ветка `research/first-prototype` и ветка `research/control-placement` сохраняются отдельно.
