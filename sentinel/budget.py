"""Shared limits for parent and specialist calls, with cooperative cancellation."""
import json
import threading
import time


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
        size=len(json.dumps([system,context,definitions],ensure_ascii=False).encode())
        if self.calls>=self.c.max_steps or self.input_bytes+size>self.c.max_input_bytes:
            raise RuntimeError('model_budget_exhausted')
        if self.store:
            self.store.reserve_call(self.c.daily_model_calls)
        self.calls+=1
        self.input_bytes+=size
