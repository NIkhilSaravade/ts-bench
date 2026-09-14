"""Shared by pipeline/validate.py and harness/eval_runner.py: resolving a
target test_id against a real {test_id: pass_bool} results dict.

Exists because JUnit5 parameterized tests report each parameter as its own
"methodName(ParamTypes)[n]" entry, never the bare "methodName" -- a name
that's the only thing derivable ahead of time from a diff (T14's
compile-failure-as-fails-at-base salvage path), and also just a real shape
any Java TaskInstance's fail_to_pass/pass_to_pass can legitimately have
whether or not it went through that salvage path at all. Without this,
harness/eval_runner.py's own resolved-scoring lookup silently returns False
for every parameterized target regardless of whether the fix actually
works -- a correctness bug in the benchmark's actual scoring path, not just
the validator.
"""


def resolve_test_outcome(results: dict[str, bool], test_id: str) -> bool:
    if test_id in results:
        return results[test_id]
    variants = [v for k, v in results.items() if k.startswith(f"{test_id}(")]
    return all(variants) if variants else False
