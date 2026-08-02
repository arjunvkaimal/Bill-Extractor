"""
Extractors package — one module per LLM provider.

The PROVIDERS dict maps provider name → extract_bill callable,
allowing the CLI runner to iterate providers by name.

Imports are lazy so that `--help` and non-extraction paths work
even when LLM SDKs aren't installed.
"""


def _get_gemini():
    from extractors.gemini import extract_bill
    return extract_bill


def _get_claude():
    from extractors.claude import extract_bill
    return extract_bill


def _get_openai():
    from extractors.openai import extract_bill
    return extract_bill


def _get_groq():
    from extractors.groq import extract_bill
    return extract_bill


class _LazyProviders(dict):
    """Dict that lazily imports provider modules on first access."""

    _loaders = {
        "gemini": _get_gemini,
        "claude": _get_claude,
        "openai": _get_openai,
        "groq": _get_groq,
    }

    def __init__(self):
        super().__init__()
        # Pre-populate keys so iteration/membership checks work
        for key in self._loaders:
            dict.__setitem__(self, key, None)

    def __getitem__(self, key):
        val = dict.__getitem__(self, key)
        if val is None and key in self._loaders:
            val = self._loaders[key]()
            dict.__setitem__(self, key, val)
        return val

    def values(self):
        return [self[k] for k in self._loaders]

    def items(self):
        return [(k, self[k]) for k in self._loaders]


PROVIDERS = _LazyProviders()
