"""Entry point for the Recursant Ingress Gateway.

Usage: python -m runtime.gateway [--config path/to/gateway.yaml]
"""

import argparse
import sys

from runtime.gateway.config import GatewayConfig
from runtime.gateway.app import create_gateway_app


def main():
    parser = argparse.ArgumentParser(description="Recursant Ingress Gateway")
    parser.add_argument("--config", help="Path to gateway config YAML")
    parser.add_argument("--port", type=int, help="Override listen port")
    args = parser.parse_args()

    if args.config:
        config = GatewayConfig.from_yaml(args.config)
    else:
        config = GatewayConfig.from_env()

    if args.port:
        config = config.model_copy(update={"port": args.port})

    app = create_gateway_app(config)

    print(f"Starting Recursant Ingress Gateway on port {config.port}")
    app.run(host="0.0.0.0", port=config.port, debug=config.log_level == "debug")


if __name__ == "__main__":
    main()
