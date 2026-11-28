# Обезличенные копии

В публикуемых копиях этих файлов заменены абсолютные пути и упоминания среды запуска; остальные файлы скопированы побитно. Код OMAIN-1 и раннер CP3 не обезличивались — их sha256 зафиксированы манифестом и хешами одобрения.

| файл | sha256 исходника | sha256 копии |
|---|---|---|
| `11-cp3-full227/reports/CP3_FULL227_STOP3.md` | `1a96d361f0bd5e739852faf37ff46e9659b1a69da17d08f60ae4b1a1c63f46ee` | `77f1cd7c8dde04d10ffcde27eb034184d09e5f53a22e1e262e63cb0fccf91c4b` |
| `11-cp3-full227/code/full227_finalize_seg03.py` | `c9cc819de8b57201756336faeac23b1e375d21a89deb06043b407d9e5f625035` | `21e36fb8e28fe78df71afeb35f001055e8282d9cc198757ded23940f640e1e26` |
| `11-cp3-full227/code/launch_full227_nohup.sh` | `b07d6c8d9afd1d23f45121f76eea4bb8296f99149b064c5ea91f339e775c679c` | `2c23c04ba0b6b2c9821e6162148dc74db02c829f79995a6fa8b19ef80322b717` |
| `09-decision-integrity-cp3/code/CP3_OPENROUTER_401_DIAG.patch` | `12ac20bd073173033cd21d091409feaaba58ead7ca8fa57cf7a61b6604b8c543` | `8ce14f2578c4b29411862a305f0f037c3405dc154d022cb888701476cb6df188` |
| `13-omain-1/manifests/OMAIN-1.json` | `fa9038d5c60f32d11440d5938048e848e6b91132260404af7f006a2d6b41976e` | `60dae71607adf3f45760507d62076b609663220016c77a40cb0c047e0c01fd3c` |
| `11-cp3-full227/reports/CP3_FULL227_RESUME1_READY.md` | `c1bff199baf320e1dff08e19259817a3e284f0d74ee848deb104c489debb86c8` | `b557ea4bbd88f45dcb66cf3b58b9e03f1917ec9b9089b37dfb509c16b293b187` |
| `11-cp3-full227/reports/CP3_FULL227_RESUME_STATUS_20261127.md` | `ce9870d1e6af317c03d4b0006f457da6e75403a2c52efd9a7df4ae73adf52fc5` | `922209ee7f627268348c6dcad17df616cb2406374ad27d68c26175ab711ee4fc` |
| `11-cp3-full227/reports/CP3_FULL227_STOP1.md` | `5ec97ae5b769df644eec2ef6ec2cc352a4f2fcb56664c91bdc874e3d343b0912` | `8c57b88fca9778bc1566195f5dad2a34438daa8d927eb0ad6a352f1a85516fa2` |
| `11-cp3-full227/reports/CP3_FULL227_STOP2.md` | `c4acd70cf6524d103f6e173a306eeefe1fb8d0bfba0c6d9f84add6865dcc430a` | `7e2a9b3c7857d9890c661af529263d65e9fd6a858e36c62429eff881603907c9` |
| `13-omain-1/АУДИТ_OMAIN-1.md` | `2c5b956a3619d3ca82651ef9c37a31f9f4c28d15b807e28a2259c60f655461b4` | `5a14d85be24938e3afc8fa240ef350a7cc374a69cebeb392285a8084b562a5e1` |

## Оставлено побитно (исключения)

- `13-omain-1/code/isolation.py:22` — комментарий `# …/cascade-502` (имя папки). Код зафиксирован sha256 в `manifests/OMAIN-1.json`; правка сломала бы проверку.
- `11-cp3-full227/results/rows.jsonl:275` — поле `interrupted_detail` TH696-A: «runner killed with the Claude Code session…». Данные серии, sha256 `ae130e3d…` зафиксирован в отчётах и raw-манифесте.
- `13-omain-1/stats/*.md` — зафиксированы sha256 в `FINAL_VERSIONS_OMAIN-1.md`.
