import sys
from decimal import Decimal
from .service import Ledger


def _cents(text):
    return int((Decimal(text) * 100).to_integral_value())


def main(argv=None, path="ledger.json"):
    argv = list(sys.argv[1:] if argv is None else argv)
    led = Ledger(path)
    cmd, *rest = argv
    if cmd == "open":
        led.open_account(rest[0], rest[1] if len(rest) > 1 else "AUD")
    elif cmd == "deposit":
        led.deposit(rest[0], _cents(rest[1]))
    elif cmd == "withdraw":
        led.withdraw(rest[0], _cents(rest[1]))
    elif cmd == "balance":
        c = led.balance(rest[0])
        print("%d.%02d %s" % (c // 100, c % 100, led.currency(rest[0])))
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
