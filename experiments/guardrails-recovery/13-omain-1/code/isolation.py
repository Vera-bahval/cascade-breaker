"""
Изоляция CascadeLab / Oracle Intervention от серий nano, Flash, PMINI-1 и замороженных данных. Импортируется ПЕРВЫМ.

Гарантии (assert_isolated() перед любым прогоном, включая офлайн-тесты):
  - свой FinBot: iv_lab/finbot-a7f6964-iso (git archive pr-477, коммит a7f6964), не finbot-a7f6964 серий;
  - своя БД: iv_lab/db/pristine_C_iso.db — копия pristine_C_8765.db, webhook хуков → 8775 (не 8765);
  - свой порт приёмника хуков 8775; 8765 (серии nano/Flash/mini) не используется;
  - Redis: адрес недоступен (REDIS_URL=redis://127.0.0.1:1) → шина событий FinBot отключается; общий контейнер
    finbot-redis не используется и не перезапускается;
  - вывод только в iv_lab/runs, iv_lab/logs или во временную папку;
  - запрет записи в замороженные папки; snapshot_frozen() — слепок (путь, размер, mtime) для проверки «до/после».
v2 (22.11.2026): исправлен ROOT (после переноса в CascadeLab/iv_lab); добавлены Flash-230, замены, PMINI-1, манифесты.
"""
from __future__ import annotations

import hashlib
import os
import socket
import sqlite3

LAB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(LAB))          # …/cascade-502
FINBOT_ISO = os.path.join(LAB, "finbot-a7f6964-iso")
DB_ISO = os.path.join(LAB, "db", "pristine_C_iso.db")
RUNS = os.path.join(LAB, "runs")
LOGS = os.path.join(LAB, "logs")
HOOK_PORT_ISO = 8775
FORBIDDEN_PORT = 8765
REDIS_UNREACHABLE = "redis://127.0.0.1:1"
EXPECTED_COMMIT = "a7f6964fbc60da807e2544d826a5b4e20eb0c5dc"
FROZEN_DIRS = [os.path.join(ROOT, p) for p in (
    "code/runs/propagation_main_ab", "code/runs/propagation_flash_ab", "code/runs/propagation_flash_1b",
    "code/runs/propagation_flash_1b_repl", "code/runs/propagation_flash_smoke", "code/runs/propagation_flash_230",
    "code/runs/propagation_mini_ab", "finbot-a7f6964", "code/finbot477/pristine")]
FROZEN_FILES = [os.path.join(ROOT, "code/runs", f) for f in (
    "propagation_candidates.json", "propagation_flash_freeze_manifest.json", "propagation_flash_1b_freeze_manifest.json",
    "propagation_mini_freeze_manifest.json", "PFLASH_provenance.csv", "PFLASH_provenance_230.csv")]


def prepare_iso_db():
    """Однократно: webhook тестовой БД → 8775 (только в копии)."""
    con = sqlite3.connect(DB_ISO)
    con.execute("update labs_guardrail_configs set webhook_url=?", (f"http://127.0.0.1:{HOOK_PORT_ISO}/hook",))
    con.commit()
    con.close()


def _port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def assert_isolated(out_dir=None):
    assert os.path.isdir(os.path.join(ROOT, "code/runs/propagation_main_ab")), f"ROOT указывает не туда: {ROOT}"
    assert open(os.path.join(FINBOT_ISO, "SOURCE_COMMIT.txt")).read().strip() == EXPECTED_COMMIT, "не та копия FinBot"
    urls = [r[0] for r in sqlite3.connect(DB_ISO).execute("select webhook_url from labs_guardrail_configs")]
    assert urls and all(str(HOOK_PORT_ISO) in u and str(FORBIDDEN_PORT) not in u for u in urls), f"webhook тестовой БД: {urls}"
    if out_dir:
        o = os.path.realpath(out_dir)
        assert o.startswith(os.path.realpath(LAB)) or o.startswith(("/private/var", "/var/folders", "/private/tmp", "/tmp")), \
            f"вывод вне iv_lab: {o}"
        assert not any(o.startswith(os.path.realpath(d)) for d in FROZEN_DIRS), f"запись в замороженную папку: {o}"
    assert _port_free(HOOK_PORT_ISO), f"порт {HOOK_PORT_ISO} занят"
    return dict(root=ROOT, finbot=FINBOT_ISO, db=DB_ISO, hook_port=HOOK_PORT_ISO, webhook=urls, redis=REDIS_UNREACHABLE)


def snapshot_frozen():
    """Слепок замороженных папок и файлов: sha от списка (путь, размер, mtime_ns)."""
    h = hashlib.sha256()
    n = 0
    for d in FROZEN_DIRS:
        for dp, dn, fn in os.walk(d):
            dn.sort()
            for f in sorted(fn):
                p = os.path.join(dp, f)
                try:
                    st = os.stat(p)
                except FileNotFoundError:
                    continue
                h.update(f"{p}|{st.st_size}|{st.st_mtime_ns}\n".encode())
                n += 1
    for p in FROZEN_FILES:
        if os.path.exists(p):
            h.update(hashlib.sha256(open(p, "rb").read()).digest())
            n += 1
    return h.hexdigest(), n


def iso_env(extra=None):
    env = dict(os.environ, REDIS_URL=REDIS_UNREACHABLE)
    for k in ("AB_OUT", "AB_DB_FLAG"):
        env.pop(k, None)
    if extra:
        env.update(extra)
    return env
