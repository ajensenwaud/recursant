def wrap(text, width):
    if width < 1:
        raise ValueError("width")
    lines, cur = [], ""
    for word in text.split():
        chunks = [word[i:i + width] for i in range(0, len(word), width)]
        for ch in chunks:
            if not cur:
                cur = ch
            elif len(cur) + 1 + len(ch) <= width:
                cur += " " + ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines
