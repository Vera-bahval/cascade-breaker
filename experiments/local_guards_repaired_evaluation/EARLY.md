# Ранние действия

128 действий:107 ALLOW,3 BLOCK,18 INSUFFICIENT. Историческая политика определяет допустимость действия; новые B-требования отдельно меняют контракт.

| Конфигурация | Режим | Верно ALLOW / BLOCK | Ошибка ALLOW / BLOCK | UNKNOWN | Неполная разметка ALLOW / BLOCK |
|---|---|---:|---:|---:|---:|
| v4.2\|rule\|A | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4.2\|rule\|A | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|A+B01 | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4.2\|rule\|A+B01 | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|A+B02 | conditional | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|A+B02 | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|A+B03 | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4.2\|rule\|A+B03 | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|B | conditional | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|B | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.2\|rule\|early | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4.2\|rule\|early | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4.3\|rule\|A | conditional | 16 / 1 | 0 / 6 | 104 | 0 / 1 |
| v4.3\|rule\|A | historical | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|A+B01 | conditional | 16 / 1 | 0 / 6 | 104 | 0 / 1 |
| v4.3\|rule\|A+B01 | historical | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|A+B02 | conditional | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|A+B02 | historical | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|A+B03 | conditional | 16 / 1 | 0 / 6 | 104 | 0 / 1 |
| v4.3\|rule\|A+B03 | historical | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|B | conditional | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|B | historical | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4.3\|rule\|early | conditional | 16 / 1 | 0 / 6 | 104 | 0 / 1 |
| v4.3\|rule\|early | historical | 0 / 1 | 0 / 6 | 120 | 0 / 1 |
| v4\|rule\|A | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4\|rule\|A | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|A+B01 | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4\|rule\|A+B01 | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|A+B02 | conditional | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|A+B02 | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|A+B03 | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4\|rule\|A+B03 | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|B | conditional | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|B | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |
| v4\|rule\|early | conditional | 15 / 1 | 0 / 2 | 110 | 0 / 0 |
| v4\|rule\|early | historical | 0 / 1 | 0 / 2 | 125 | 0 / 0 |

## Первая остановка

| Конфигурация | Режим | Политика STOP | Первая BLOCK | Первая UNKNOWN | Без наблюдаемых точек | Достигнуто / пропущено точек |
|---|---|---|---:|---:|---:|---:|
| v4.2\|rule\|A | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.2\|rule\|A | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|A+B01 | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A+B01 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.2\|rule\|A+B01 | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A+B01 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|A+B02 | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A+B02 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|A+B02 | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A+B02 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|A+B03 | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A+B03 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.2\|rule\|A+B03 | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|A+B03 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|B | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|B | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|B | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|B | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.2\|rule\|early | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|early | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.2\|rule\|early | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4.2\|rule\|early | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|A | conditional | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.3\|rule\|A | historical | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|A+B01 | conditional | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A+B01 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.3\|rule\|A+B01 | historical | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A+B01 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|A+B02 | conditional | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A+B02 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|A+B02 | historical | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A+B02 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|A+B03 | conditional | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A+B03 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.3\|rule\|A+B03 | historical | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|A+B03 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|B | conditional | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|B | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|B | historical | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|B | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4.3\|rule\|early | conditional | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|early | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4.3\|rule\|early | historical | BLOCK_ONLY | 377 | 0 | 1 | 14840 / 3836 |
| v4.3\|rule\|early | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|A | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4\|rule\|A | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|A+B01 | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A+B01 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4\|rule\|A+B01 | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A+B01 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|A+B02 | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A+B02 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|A+B02 | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A+B02 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|A+B03 | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A+B03 | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4\|rule\|A+B03 | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|A+B03 | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|B | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|B | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|B | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|B | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
| v4\|rule\|early | conditional | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|early | conditional | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 847 / 17829 |
| v4\|rule\|early | historical | BLOCK_ONLY | 108 | 0 | 1 | 17788 / 888 |
| v4\|rule\|early | historical | BLOCK_OR_UNKNOWN | 0 | 753 | 1 | 753 / 17923 |
