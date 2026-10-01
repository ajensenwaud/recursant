import re

_REF = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate(template, variables):
    out = []
    i, n = 0, len(template)
    while i < n:
        ch = template[i]
        if ch != "$":
            out.append(ch)
            i += 1
            continue
        nxt = template[i + 1] if i + 1 < n else ""
        if nxt == "$":
            out.append("$")
            i += 2
        elif nxt == "{":
            m = _REF.match(template, i + 1)
            if not m:
                raise ValueError("bad reference at offset %d" % i)
            name = m.group(1)
            if name not in variables:
                raise KeyError(name)
            out.append(str(variables[name]))
            i = m.end()
        else:
            out.append("$")
            i += 1
    return "".join(out)
