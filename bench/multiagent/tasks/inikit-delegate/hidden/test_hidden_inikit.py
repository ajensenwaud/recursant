import unittest
from inikit import parse_ini, coerce, interpolate, load_config


class HiddenParse(unittest.TestCase):
    def test_sections_and_keys(self):
        text = "# comment\n\n[server]\nhost = localhost\n  port=8080  \n; other\n[ paths ]\nroot = /srv\n"
        self.assertEqual(parse_ini(text), {"server": {"host": "localhost", "port": "8080"}, "paths": {"root": "/srv"}})

    def test_top_level_and_empty_section(self):
        self.assertEqual(parse_ini("a = 1\n[s]\n"), {"": {"a": "1"}, "s": {}})
        self.assertEqual(parse_ini("[s]\nb=2"), {"s": {"b": "2"}})
        self.assertEqual(parse_ini(""), {})
        self.assertEqual(list(parse_ini("[z]\n[a]\n[m]\n")), ["z", "a", "m"])

    def test_first_equals_empty_value_no_inline_comments(self):
        got = parse_ini("[q]\nurl = http://h/?a=b&c=d\nempty =\nnote = 1 # x\nsemi = a ; b\n")
        self.assertEqual(got["q"], {"url": "http://h/?a=b&c=d", "empty": "", "note": "1 # x", "semi": "a ; b"})

    def test_duplicates_merge_and_case(self):
        got = parse_ini("[a]\nx = 1\nX = 9\n[b]\ny = 2\n[a]\nx = 3\nz = 4\n")
        self.assertEqual(got, {"a": {"x": "3", "X": "9", "z": "4"}, "b": {"y": "2"}})
        self.assertEqual(list(got), ["a", "b"])

    def test_errors(self):
        for bad in ("just words", "[a]\n= 5", "[]", "[   ]", "[broken", "[a] = b", "[a]\nkey"):
            with self.assertRaises(ValueError, msg=bad):
                parse_ini(bad)


class HiddenCoerce(unittest.TestCase):
    def test_bool_and_none(self):
        for s in ("true", "TRUE", " Yes ", "on"):
            self.assertIs(coerce(s), True, s)
        for s in ("false", "No", " OFF"):
            self.assertIs(coerce(s), False, s)
        for s in ("null", "None", "", "   "):
            self.assertIsNone(coerce(s), s)

    def test_numbers(self):
        for s, want in (("42", 42), ("-0", 0), ("+7", 7), ("007", 7), (" 12 ", 12)):
            got = coerce(s)
            self.assertEqual(got, want, s)
            self.assertIs(type(got), int, s)
        for s, want in (("3.0", 3.0), ("-0.50", -0.5), ("+10.25", 10.25)):
            got = coerce(s)
            self.assertEqual(got, want, s)
            self.assertIs(type(got), float, s)

    def test_stays_string(self):
        for s in ("1_000", "1e3", ".5", "5.", "0x10", "inf", "nan", "-", "1.2.3", "１２", "yes please"):
            self.assertEqual(coerce(s), s, s)
            self.assertIs(type(coerce(s)), str, s)
        self.assertEqual(coerce("  hello world "), "hello world")

    def test_quotes(self):
        self.assertEqual(coerce('"true"'), "true")
        self.assertEqual(coerce("'42'"), "42")
        self.assertEqual(coerce(' " padded " '), " padded ")
        self.assertEqual(coerce('""'), "")
        self.assertEqual(coerce('"'), '"')
        self.assertEqual(coerce("\"mixed'"), "\"mixed'")


class HiddenInterpolate(unittest.TestCase):
    def test_substitution(self):
        self.assertEqual(interpolate("hi ${name}!", {"name": "bob"}), "hi bob!")
        self.assertEqual(interpolate("${a}${b_2}${_c}", {"a": 1, "b_2": None, "_c": 2.5}), "1None2.5")
        self.assertEqual(interpolate("no refs", {}), "no refs")
        self.assertEqual(interpolate("", {}), "")

    def test_dollars(self):
        self.assertEqual(interpolate("cost $5 and $$5", {}), "cost $5 and $5")
        self.assertEqual(interpolate("$${x}", {"x": "no"}), "${x}")
        self.assertEqual(interpolate("$$${x}", {"x": "v"}), "$v")
        self.assertEqual(interpolate("end$", {}), "end$")
        self.assertEqual(interpolate("$x {x}", {"x": "v"}), "$x {x}")
        self.assertEqual(interpolate("${a}-${b}", {"a": "${b}", "b": "$$"}), "${b}-$$")

    def test_errors(self):
        with self.assertRaises(KeyError):
            interpolate("${missing}", {"other": 1})
        for bad in ("${}", "${1a}", "${a b}", "${a", "x ${a-b}"):
            with self.assertRaises(ValueError, msg=bad):
                interpolate(bad, {"a": 1, "b": 2})


class HiddenConfig(unittest.TestCase):
    TEXT = (
        "name = ${app}\n"
        "[server]\n"
        "port = ${port}\n"
        "debug = Yes\n"
        "host = \"${host}\"\n"
        "price = $$5\n"
        "ratio = 0.50\n"
        "workers = 1_000\n"
        "[empty]\n"
    )

    def test_load_config(self):
        got = load_config(self.TEXT, {"app": "demo", "port": 8080, "host": "true"})
        self.assertEqual(list(got), ["", "server", "empty"])
        self.assertEqual(got[""], {"name": "demo"})
        self.assertEqual(got["empty"], {})
        server = got["server"]
        self.assertEqual(server["port"], 8080)
        self.assertIs(type(server["port"]), int)
        self.assertIs(server["debug"], True)
        self.assertEqual(server["host"], "true")
        self.assertEqual(server["price"], "$5")
        self.assertEqual(server["ratio"], 0.5)
        self.assertEqual(server["workers"], "1_000")

    def test_load_config_defaults_and_errors(self):
        self.assertEqual(load_config("[a]\nx = off\ny =\n"), {"a": {"x": False, "y": None}})
        with self.assertRaises(KeyError):
            load_config("x = ${nope}")
        with self.assertRaises(ValueError):
            load_config("[a]\nnot a pair")
