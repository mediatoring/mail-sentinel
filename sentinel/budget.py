"""Shared limits for parent and specialist calls, with cooperative cancellation."""
import json
import threading
import time


def check_context(config, system, context, definitions):
    """Conservative estimate, not a model-specific tokenizer or server discovery."""
    size=len(json.dumps([system,context,definitions],ensure_ascii=False).encode('utf-8'))
    estimated=(size+2)//3+512
    if estimated+config.max_output_tokens>config.context_tokens:
        from .providers import ProviderError, ERROR_MESSAGES
        raise ProviderError(ERROR_MESSAGES['context_limit'],'context_limit')
    return estimated


class Cancelled(Exception):
    pass


class RunBudget:
    def __init__(self, config, cancel=None, store=None):
        self.c=config
        self.cancel=cancel or threading.Event()
        self.store=store
        self.started=time.monotonic()
        self.calls=0
        self.input_bytes=0

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()
        if time.monotonic()-self.started>=self.c.max_seconds:
            raise TimeoutError('time_limit')

    def consume(self, system, context, definitions):
        self.check()
        check_context(self.c,system,context,definitions)
        size=len(json.dumps([system,context,definitions],ensure_ascii=False).encode())
        if self.calls>=self.c.max_steps or self.input_bytes+size>self.c.max_input_bytes:
            raise RuntimeError('model_budget_exhausted')
        if self.store:
            self.store.reserve_call(self.c.daily_model_calls)
        self.calls+=1
        self.input_bytes+=size
