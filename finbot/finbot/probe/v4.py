"""Default-off bridge to the repository's deterministic v4 research profile."""
from contextlib import contextmanager
from contextvars import ContextVar
import importlib
import os
from pathlib import Path
import sys

_CURRENT = ContextVar('finbot_v4_runtime', default=None)


class V4Stop(RuntimeError):
    """Whole-execution stop; native recoverable-tool handlers must rethrow it."""
    def __init__(self, decision):
        self.decision = decision
        super().__init__('v4 STOP: ' + decision['decision'] + ': ' + ','.join(decision['reasons']))


def active():
    return _CURRENT.get()


def configured():
    if not os.environ.get('FINBOT_V4_PROFILE'):
        return None
    try:
        root = str(Path(__file__).resolve().parents[3])
        if root not in sys.path:
            sys.path.insert(0, root)
        module = importlib.import_module('experiments.local_guards_v4.runtime')
        return module.Runtime(os.environ['FINBOT_V4_STORE'],
                              profile=os.environ['FINBOT_V4_PROFILE'])
    except V4Stop:
        raise
    except Exception:
        raise V4Stop({'decision': 'UNKNOWN', 'reasons': ['runtime_configuration_unavailable'], 'stop': True}) from None


def raise_if_stopped():
    if runtime := active():
        runtime.raise_if_stopped()


@contextmanager
def agent_entry(agent, task_data):
    runtime = active() or configured()
    if runtime is None:
        yield None
    else:
        with runtime.agent_scope(agent, task_data):
            yield runtime


def wrap_callables(agent, callables):
    runtime = active()
    return runtime.wrap_callables(agent, callables) if runtime else callables


def filter_servers(servers):
    runtime = active()
    if runtime and runtime.profile == 'B' and runtime.origin_portal == 'vendor':
        return {key: value for key, value in servers.items() if key != 'systemutils'}
    return servers


async def invoke_mcp(provider, name, arguments, execute):
    runtime = active()
    if runtime is None:
        return await execute()
    return await runtime.invoke_mcp(provider, name, arguments, execute)


async def execute_background(runtime, execute, **kwargs):
    # Open the captured private execution inside the actual background coroutine.
    with runtime.open():
        return await execute(**kwargs)
