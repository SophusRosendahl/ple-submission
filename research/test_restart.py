"""Run: python3 research/test_restart.py   (tests the naive harness's restart-on-interruption with scripted model replies)"""
import asyncio, os, pathlib, sys, types
os.environ.update(MODEL_NAME="gemini-4-neon", OPENAI_API_KEY="x")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harnesses" / "naive"))
import serve

CAP = serve.MAX_OUTPUT_TOKENS
def U(completion, reasoning=0): return types.SimpleNamespace(prompt_tokens=100, completion_tokens=completion, prompt_tokens_details=None,
    completion_tokens_details=types.SimpleNamespace(reasoning_tokens=reasoning))

class Run:
    def __init__(self, script): self.script, self.calls, self.written, self.logs = list(script), [], {}, []
    async def go(self):
        run = self
        async def fake_ask(session, messages, effort=None):
            run.calls.append((messages, effort)); text, usage, reason = run.script.pop(0); return text, usage, reason
        async def fake_gather(session): return "inputs", []
        serve.ask, serve.gather_inputs = fake_ask, fake_gather
        class S:
            workdir = "/app"; instruction = "TASK"
            async def log(self, t): run.logs.append(t)
            async def usage(self, *a, **k): pass
            async def write_file(self, p, c): run.written[p] = c
            def time_left(self): return 99999
        for k in serve.CALLS: serve.CALLS[k] = 0
        self.final = await serve._solve(S())
        return self

def run(script): return asyncio.run(Run(script).go())
CUT = lambda text, completion=CAP, reasoning=0: (text, U(completion, reasoning), "length")
OK = lambda text: (text, U(500), "stop")

def test_continue_after_cut_off():
    r = run([CUT("done so far\n<<<FILE a.py>>>\nline1\nline2"), OK("\nline3\n<<<END>>>\nsummary")])
    assert len(r.calls) == 2 and r.written == {"a.py": "line1\nline2\nline3\n"}, r.written
    convo = r.calls[1][0]; assert convo[-2]["role"] == "assistant" and convo[-2]["content"].endswith("line2") and convo[-1]["content"] == serve.CONTINUE_NOTE
    assert [c[1] for c in r.calls] == [None or serve.EFFORT, "medium"], [c[1] for c in r.calls]   # one step down

def test_empty_output_gets_the_empty_note():
    r = run([CUT("", reasoning=CAP), OK("<<<FILE b.txt>>>\nhello\n<<<END>>>\nsummary")])
    assert len(r.calls) == 2 and r.calls[1][0][-1]["content"] == serve.EMPTY_NOTE and r.written == {"b.txt": "hello\n"}

def test_the_proxy_says_stop_but_the_budget_is_used():
    r = run([("", U(CAP, CAP), "stop"), OK("<<<FILE c.txt>>>\nx\n<<<END>>>")])     # Neon's real behaviour
    assert len(r.calls) == 2, len(r.calls)

def test_model_restarts_the_file_instead_of_continuing():
    r = run([CUT("<<<FILE a.py>>>\nOLD partial"), OK("<<<FILE a.py>>>\nnew full\n<<<END>>>")])
    assert r.written == {"a.py": "new full\n"}, r.written

def test_restart_limit():
    serve.MAX_RESTARTS = 2
    r = run([CUT("a"), CUT("b"), CUT("c"), CUT("never")])
    assert len(r.calls) == 3, len(r.calls); serve.MAX_RESTARTS = 5

def test_normal_reply_is_one_call():
    r = run([OK("<<<FILE z.txt>>>\nok\n<<<END>>>\ndone")])
    assert len(r.calls) == 1 and r.written == {"z.txt": "ok\n"} and serve.CALLS["ok"] == 0   # fake ask does not count; real one does

def test_step_down_can_be_switched_off():
    serve.RESTART_EFFORT_STEP = False
    r = run([CUT("x"), OK("y")]); serve.RESTART_EFFORT_STEP = True
    assert r.calls[0][1] == r.calls[1][1]

for name, fn in list(globals().items()):
    if name.startswith("test_"): fn(); print("ok", name)
