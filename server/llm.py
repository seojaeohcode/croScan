"""The one door to the on-premise model (Raon-1 mini on llama.cpp, OpenAI-compatible). Design §1.4 / §9 / §10.

Every call is a typed job: a JSON schema the server checks again, a reasoning budget per call (an unbounded one
was measured at 123 s for nothing), a total token cap that includes the reasoning, the prompt cache, and a deadline
from the moment the job was taken: when it passes, the HTTP request is closed and llama.cpp frees the slot.
A failure is reported as such (ok False + why); the caller falls back to the rules, never to a guess.
"""
import asyncio
import json
import os
import time

import httpx

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8000/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "Raon-1-mini-preview")
# the order of need (design §10.7): 0 a foreman's answer being read while he works on, 1 what a person asked for
# now (the manager's 「왜?」, a note, a pair review, a draft read ahead of the foreman's 보내기), 2 work prepared ahead
# (upload analysis, links, checklist suggestions), 3 warm-ups nobody asked for yet
FG, ASKED, PREPARED, WARM = 0, 1, 2, 3
PREEMPTIBLE = (PREPARED, WARM)


class _Slot:
    """one slot on the CPU server: calls wait here in order of need (then arrival) instead of piling up in
    llama.cpp. A more urgent call cancels a prepared or warm-up call holding the slot; a person's call is never
    cancelled for another."""

    def __init__(self):
        self.busy, self.waiting, self.n = False, [], 0
        self.holder = {"task": None, "pri": None}

    def locked(self):
        return self.busy

    async def acquire(self, pri):
        if self.busy and self.holder["task"] and self.holder["pri"] in PREEMPTIBLE and pri < self.holder["pri"]:
            self.holder["task"].cancel()
        me = asyncio.current_task()
        if not self.busy and not self.waiting:
            self.busy = True
            self.holder.update(task=me, pri=pri)
            return
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        entry = [pri, self.n, fut, me]
        self.waiting.append(entry)
        self.waiting.sort(key=lambda e: (e[0], e[1]))
        try:
            await fut
        except BaseException:
            if entry in self.waiting:
                self.waiting.remove(entry)
            elif fut.done() and not fut.cancelled():
                self.release()                             # granted while being cancelled: pass it on
            raise

    def release(self):
        while self.waiting:
            pri, _, fut, task = self.waiting.pop(0)
            if not fut.done():
                self.holder.update(task=task, pri=pri)     # who holds it is known at once (a FG call arriving now can preempt it)
                fut.set_result(True)                       # the slot goes straight to the next in order
                return
        self.holder.update(task=None, pri=None)
        self.busy = False

    def stats(self):
        return {"busy": self.busy, "holder": self.holder["pri"], "waiting": [e[0] for e in self.waiting]}


_SLOT = _Slot()
_HOLDER = _SLOT.holder


class LlmFail(Exception):
    def __init__(self, code, detail="", meta=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail, self.meta = code, detail, meta or {}


def _payload(messages, schema, think, max_tokens, temperature):
    body = {"model": LLM_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.95,
            "cache_prompt": True, "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}}
    if think:
        body["reasoning_budget"] = think                       # held for a short reply; not for a long one (608 tokens, 2026-10-31)
    else:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    return body


async def call_json(kind, messages, schema, think=128, out_tokens=256, deadline=60.0, temperature=0.0, sid=None, background=False, pri=None):
    # temperature 0 by default: the same request gives the same output on this build (not a guarantee that a reading is
    # right; the server's checks and the foreman's confirmation are)
    """-> (data, meta). data is the parsed JSON object; meta has ms, tokens, waited. Raises LlmFail.
    sid: the review the call is for — counted against its model budget before it runs (store.LLM_CALLS).
    pri: its place in the order of need (FG … WARM); background=True is PREPARED, else FG."""
    pri = pri if pri is not None else PREPARED if background else FG
    t0 = time.monotonic()
    if sid:
        from . import store
        try:
            store.charge_llm(sid)
        except store.StoreError as e:
            raise LlmFail("budget", e.detail)
    body = _payload(messages, schema, think, (think or 0) + out_tokens, temperature)
    try:
        await asyncio.wait_for(_SLOT.acquire(pri), timeout=max(0.1, deadline - 1))
    except asyncio.TimeoutError:
        raise LlmFail("busy", "모델이 다른 일을 하고 있어 기한 안에 시작하지 못함")
    waited = time.monotonic() - t0
    try:
        left = deadline - waited
        if left < 3:
            raise LlmFail("timeout", "기한이 지남")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(left, connect=5)) as cl:
                r = await asyncio.wait_for(cl.post(LLM_URL, json=body), timeout=left)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            raise LlmFail("timeout", f"{deadline:.0f}초 안에 끝나지 않음")     # the closed request frees the model's slot
        except httpx.HTTPError as e:
            raise LlmFail("down", e.__class__.__name__)
        if r.status_code >= 400:
            raise LlmFail("http", f"{r.status_code} {r.text[:160]}")
        j = r.json()
        ch = (j.get("choices") or [{}])[0]
        txt = ((ch.get("message") or {}).get("content") or "").strip()
        tm = j.get("timings") or {}
        meta = {"kind": kind, "ms": round((time.monotonic() - t0) * 1000), "waited_ms": round(waited * 1000),
                "prompt_n": tm.get("prompt_n"), "gen_n": tm.get("predicted_n"), "finish": ch.get("finish_reason"),
                "cache_n": tm.get("cache_n"), "prompt_ms": tm.get("prompt_ms"), "gen_ms": tm.get("predicted_ms")}
        if ch.get("finish_reason") == "length" or not txt:
            raise LlmFail("length", "답을 다 쓰기 전에 끝남", meta)
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            raise LlmFail("json", txt[:120], meta)
        if not isinstance(data, dict):
            raise LlmFail("json", "객체가 아님")
        return data, meta
    finally:
        _SLOT.release()


async def prefill(kind, messages, deadline=60.0, pri=ASKED):
    """read messages into the model's prompt cache and write nothing (design §10.7): a later call that starts with the
    same messages reads only what follows. -> meta, or raises LlmFail. No answer comes of it, so nothing is checked
    or kept; it is counted on its own (store.warm), not as a reading."""
    t0 = time.monotonic()
    body = {"model": LLM_MODEL, "messages": messages, "max_tokens": 1, "temperature": 0.0, "cache_prompt": True, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}}
    try:
        await asyncio.wait_for(_SLOT.acquire(pri), timeout=max(0.1, deadline - 1))
    except asyncio.TimeoutError:
        raise LlmFail("busy", "모델이 다른 일을 하고 있어 기한 안에 시작하지 못함")
    try:
        left = deadline - (time.monotonic() - t0)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(max(3, left), connect=5)) as cl:
                r = await asyncio.wait_for(cl.post(LLM_URL, json=body), timeout=max(3, left))
        except (asyncio.TimeoutError, httpx.TimeoutException):
            raise LlmFail("timeout", f"{deadline:.0f}초 안에 끝나지 않음")
        except httpx.HTTPError as e:
            raise LlmFail("down", e.__class__.__name__)
        if r.status_code >= 400:
            raise LlmFail("http", f"{r.status_code} {r.text[:160]}")
        tm = r.json().get("timings") or {}
        return {"kind": kind, "ms": round((time.monotonic() - t0) * 1000), "prompt_n": tm.get("prompt_n"), "cache_n": tm.get("cache_n"),
                "prompt_ms": tm.get("prompt_ms")}
    finally:
        _SLOT.release()


async def status():
    base = LLM_URL.split("/v1/")[0]
    try:
        async with httpx.AsyncClient(timeout=3) as cl:
            h = await cl.get(base + "/health")
        return {"ok": h.status_code == 200, "model": LLM_MODEL}
    except httpx.HTTPError as e:
        return {"ok": False, "model": LLM_MODEL, "why": e.__class__.__name__}
