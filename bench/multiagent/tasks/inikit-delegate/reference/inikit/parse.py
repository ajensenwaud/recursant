def parse_ini(text):
    result = {}
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            if not line.endswith("]"):
                raise ValueError("bad section header: %r" % raw)
            name = line[1:-1].strip()
            if not name:
                raise ValueError("empty section name")
            current = name
            result.setdefault(current, {})
            continue
        if "=" not in line:
            raise ValueError("expected key = value: %r" % raw)
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("empty key: %r" % raw)
        result.setdefault(current, {})[key] = value.strip()
    return result
