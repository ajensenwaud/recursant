Build a small `inikit` package in /workspace with three INDEPENDENT modules. They share nothing, so delegate them to
subagents working in parallel (one module each, using your delegate_task tool); then write the integration piece,
review and test everything yourself.

1. `inikit/parse.py`: `parse_ini(text) -> dict[str, dict[str, str]]`
   - Work line by line; strip each line. Blank lines and lines whose first character is `#` or `;` are ignored.
   - A line starting with `[` is a section header: it must end with `]`, and the name between the brackets (stripped
     of surrounding whitespace) must be non-empty, otherwise ValueError. A section appears in the result even if it has
     no keys. A repeated header continues the earlier section (keys are merged into it).
   - Every other line must contain `=`, otherwise ValueError. Split on the FIRST `=` only; strip key and value.
     An empty key raises ValueError; an empty value is allowed (""). A later duplicate key in the same section overwrites.
   - Keys before any header go into the section named "" (empty string); that section exists only if there is at least
     one such key. Names are case-sensitive. There are no inline comments: `a = 1 # x` has the value `1 # x`.
   - All values stay strings. Sections and keys keep first-appearance order.
2. `inikit/coerce.py`: `coerce(value) -> object` (takes one string), rules applied in this order after stripping whitespace:
   - Length >= 2 and starts and ends with the same quote character (`"` or `'`): return the text between the quotes
     unchanged (no stripping, no further coercion; two quotes with nothing between give "").
   - Case-insensitive `true`, `yes`, `on` -> True; `false`, `no`, `off` -> False; `null`, `none` or empty -> None.
   - Optional `+`/`-` sign then one or more ASCII digits 0-9 -> int (leading zeros allowed: `007` is 7).
   - Optional sign, one or more ASCII digits, `.`, one or more ASCII digits -> float.
   - Anything else -> the stripped string. In particular `1_000`, `1e3`, `.5`, `5.`, `0x10`, `inf`, `nan` and
     non-ASCII digits stay strings.
3. `inikit/interp.py`: `interpolate(template, variables) -> str`
   - Scan left to right in a single pass. `$$` produces one literal `$`.
   - `${name}`, where name matches [A-Za-z_][A-Za-z0-9_]*, is replaced by str(variables[name]); a missing name raises
     KeyError. `${` that is not followed by such a name and a closing `}` raises ValueError (e.g. `${}`, `${1a}`,
     `${a b}`, `${a`).
   - Any other `$` is kept literally (e.g. `cost $5`, or a `$` at the very end).
   - Substituted values are never scanned again, even if they contain `$`.

Integration piece (write this yourself after the subagents return):

4. `inikit/config.py`: `load_config(text, variables=None) -> dict[str, dict[str, object]]`
   - parse_ini(text), then replace every value by coerce(interpolate(value, variables)); `variables=None` means {}.
     Section and key structure is unchanged (empty sections stay). Errors from the three modules propagate.
5. `inikit/__init__.py` re-exporting `parse_ini`, `coerce`, `interpolate`, `load_config`.

Also write tests in `tests/` (the directory already exists). Run `python -m unittest discover -s tests` from /workspace.
Use your file tools to create files on disk. Python standard library only.
