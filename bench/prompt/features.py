"""Prompt-classifier features, mirroring core/src/context/prompt.c byte for byte
(bench/prompt/parity.py checks it against the C build). Work on UTF-8 bytes."""
import math

DENSE = ['bias', 'log_chars', 'log_lines', 'log_tokens', 'code_frac', 'digit_frac', 'ops_frac', 'question']
TEXT_MAX, TOKEN_MAX = 65536, 32
CODE = set(b'{}[]()=;_`\\#<>')
OPS = set(b'+-*/^%')


def _alnum(b):
    return 48 <= b <= 57 or 65 <= b <= 90 or 97 <= b <= 122


def tokens(data):
    out, i, n = [], 0, len(data)
    while i < n:
        if not _alnum(data[i]): i += 1; continue
        j = i
        while j < n and _alnum(data[j]): j += 1
        out.append(data[i:j]); i = j
    return out


def features(text):
    """(dense dict, set of vocabulary-eligible tokens) for a message text."""
    data = text.encode('utf-8')[:TEXT_MAX]
    n = len(data); toks = tokens(data)
    d = {'bias': 1.0, 'log_chars': math.log1p(n), 'log_lines': math.log1p(data.count(b'\n')),
         'log_tokens': math.log1p(len(toks)),
         'code_frac': sum(b in CODE for b in data) / n if n else 0.0,
         'digit_frac': sum(48 <= b <= 57 for b in data) / n if n else 0.0,
         'ops_frac': sum(b in OPS for b in data) / n if n else 0.0,
         'question': 1.0 if b'?' in data else 0.0}
    vocab = {t.lower().decode('ascii') for t in toks if len(t) <= TOKEN_MAX}
    return d, vocab


def message_text(body):
    """The newest message's text if it is a user message (as rc_prompt_score), else None."""
    msgs = body.get('messages') or []
    if not msgs or msgs[-1].get('role') != 'user': return None
    c = msgs[-1].get('content')
    if isinstance(c, str): return c
    if not isinstance(c, list): return None
    parts = [p['text'] for p in c if isinstance(p, dict) and p.get('type') == 'text' and isinstance(p.get('text'), str)]
    return '\n'.join(parts) if parts else None


def score(model, text):
    d, toks = features(text)
    z = sum(model['weights'].get(k, 0.0) * v for k, v in d.items())
    z += sum(model['vocab'].get(t, 0.0) for t in toks)
    return 1 / (1 + math.exp(-max(-500.0, min(500.0, z))))
