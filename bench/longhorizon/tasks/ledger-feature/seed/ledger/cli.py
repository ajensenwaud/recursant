import sys
from .service import Ledger


def main(argv=None, path="ledger.json"):
    argv = list(sys.argv[1:] if argv is None else argv)
    led = Ledger(path)
    cmd, *rest = argv
    if cmd == "open":
        led.open_account(rest[0])
    elif cmd == "deposit":
        led.deposit(rest[0], float(rest[1]))
    elif cmd == "withdraw":
        led.withdraw(rest[0], float(rest[1]))
    elif cmd == "balance":
        print("%.2f" % led.balance(rest[0]))
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
