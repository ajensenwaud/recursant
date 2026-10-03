"""The candidate gate (which lines the name model must read) and post-filters for known model
false alarms on agent text. Designed on the test set from bench/privacy/build.py only; scored
on bench/privacy/holdout_synth.py and bench/privacy/holdout.py without changes.

Gate: a person's name in text almost always shows as two capitalised words together, or a
capitalised word right after a cue (Dear, Hi, holder, customer, "name": ...). Lines without
either cannot hold a name the model would find, so the model reads only the gated lines
(plus one line either side for context). Identifiers and addresses are left to rules."""
import re

NAMEWORD = r"[A-Z](?:'[A-Z])?[a-z]+(?:[A-Z][a-z]+)?"   # Olivia, O'Brien, MacDonald
PAIR = re.compile(r"\b" + NAMEWORD + r"(?:[ \t]+(?:[A-Z]\.?[ \t]+)?|,[ \t]*)" + NAMEWORD + r"(?:-[A-Z][a-z]+)?\b")
CUE = re.compile(r"(?i:\b(?:dear|hi|hello|thanks|regards|name|holder|customer|patient|author|assigned(?:_to)?|"
                 r"contact|member|employee|spoke to|signed|first|last|surname|given)\b)[\"':=\s,]{0,6}[A-Z][a-z]+")
LINE_BREAK = re.compile(r'\n|\\n')   # tool results are often JSON with escaped newlines


def lines(text):
    """(start, end) of each line, splitting on real and escaped newlines."""
    out, pos = [], 0
    for m in LINE_BREAK.finditer(text):
        out.append((pos, m.start())); pos = m.end()
    out.append((pos, len(text)))
    return out


def gate(text, context=1):
    """Character ranges the model must read: gated lines plus `context` lines either side,
    merged. Empty when nothing in the text can be a name."""
    ls = lines(text)
    keep = set()
    for i, (s, e) in enumerate(ls):
        line = text[s:e]
        if PAIR.search(line) or CUE.search(line):
            keep.update(range(max(0, i - context), min(len(ls), i + context + 1)))
    ranges = []
    for i in sorted(keep):
        s, e = ls[i]
        if ranges and i - 1 in keep: ranges[-1] = (ranges[-1][0], e)
        else: ranges.append((s, e))
    return ranges


def gated_lines(text, context=1):
    return '\n'.join(text[s:e] for s, e in gate(text, context))


# Characters that never occur inside a person's name or street address but do in code.
CODEY = re.compile(r'[_/\\:<>{}()\[\]=@#$`|]')


def merge(ents, text):
    """Join entities of the same kind that touch or are separated only by the rest of a word.
    Token models split one word into sub-word pieces and leave some pieces untagged
    ('Lac' + 'an Papado' in 'Lachlan Papadopoulos'); joined, a real name starts on a word
    boundary, while a piece of an identifier ('Tu' from Tuple) stays a fragment."""
    out = []
    for e in sorted(ents, key=lambda e: (e['start'], e['end'])):
        if out and out[-1]['kind'] == e['kind'] and (e['start'] <= out[-1]['end'] or
                                                     re.fullmatch(r"[A-Za-z']{1,6}", text[out[-1]['end']:e['start']])):
            last = out[-1]
            if e['end'] > last['end']:
                last['end'] = e['end']; last['text'] = text[last['start']:last['end']]
            last['score'] = max(last['score'], e['score'])
        else:
            out.append(dict(e))
    return out


NAME_PREFIX = re.compile(r"(?:Mc|Mac|De|Di|Da|Du|La|Le|Van|Von|Fitz|O')[A-Z]")


def drop(kind, ent, text, start, end):
    """Known false alarms on agent text: a fragment of a longer word ('Tu' from Tuple), a
    compound code identifier ('LiamParser'; 'MacDonald' is kept), a name or address with code
    punctuation or glued to code, or one with no letters."""
    if kind not in ('name', 'address'): return False
    while start < end and text[start].isspace(): start += 1
    while end > start and text[end - 1].isspace(): end -= 1
    left = text[start - 1:start] if start else ''
    if left.isalnum(): return True                                            # starts inside a word
    full_end = end
    while full_end < len(text) and (text[full_end].isalnum() or text[full_end] == "'"): full_end += 1
    words = text[start:full_end].split()
    if len(words) == 1 and (end - start) < 0.7 * (full_end - start): return True   # most of one word untagged
    right = text[full_end:full_end + 1]
    span = text[start:full_end]
    if not re.search(r'[A-Za-z]{2}', span): return True                       # digits/punctuation only
    if CODEY.search(span): return True                                        # snake_case, paths, markup
    if any(re.search(r'[a-z][A-Z][a-z]{2}', w) and not NAME_PREFIX.match(w) for w in words): return True   # camelCase
    if left and left in '_./\\@#$`' or right and right in '_/\\(@`': return True   # glued to code
    return False
