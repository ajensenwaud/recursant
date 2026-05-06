#!/usr/bin/env bash
# generate-certs.sh — Generate dev PKI for mortgage demo sidecars.
#
# Creates 5 sidecar certs (customer, auth, kyc, credit, core-banking)
# using the existing CA from mesh/docker/certs/ if available,
# or generating a new one.
#
# Usage:
#   ./generate-certs.sh [output_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:-$SCRIPT_DIR}"
MESH_CERTS_DIR="$(cd "$SCRIPT_DIR/../../../mesh/docker/certs" 2>/dev/null && pwd || echo "")"

mkdir -p "$OUTPUT_DIR"

DAYS=365
KEY_SIZE=2048

echo "==> Generating mortgage demo PKI in $OUTPUT_DIR"

# ---------------------------------------------------------------------------
# 1. Root CA — reuse from mesh if available, otherwise generate
# ---------------------------------------------------------------------------
if [ -f "$MESH_CERTS_DIR/ca.pem" ] && [ -f "$MESH_CERTS_DIR/ca-key.pem" ]; then
    echo "  [CA] Reusing existing CA from $MESH_CERTS_DIR"
    cp "$MESH_CERTS_DIR/ca.pem" "$OUTPUT_DIR/ca.pem"
    cp "$MESH_CERTS_DIR/ca-key.pem" "$OUTPUT_DIR/ca-key.pem"
else
    echo "  [CA] Generating new Root CA"
    openssl req -x509 -new -nodes \
        -newkey rsa:$KEY_SIZE \
        -keyout "$OUTPUT_DIR/ca-key.pem" \
        -out "$OUTPUT_DIR/ca.pem" \
        -days $DAYS \
        -subj "/C=GB/O=Recursant Dev/CN=Recursant Dev CA" \
        2>/dev/null
fi

# ---------------------------------------------------------------------------
# Generate a sidecar cert
# ---------------------------------------------------------------------------
generate_cert() {
    local name="$1"
    shift
    local sans="$*"

    echo "  [$name] Generating cert (SANs: $sans)"

    cat > "$OUTPUT_DIR/${name}.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=${sans}
EOF

    openssl req -new -nodes \
        -newkey rsa:$KEY_SIZE \
        -keyout "$OUTPUT_DIR/${name}-key.pem" \
        -out "$OUTPUT_DIR/${name}.csr" \
        -subj "/C=GB/O=Recursant Dev/CN=${name}" \
        2>/dev/null

    openssl x509 -req \
        -in "$OUTPUT_DIR/${name}.csr" \
        -CA "$OUTPUT_DIR/ca.pem" \
        -CAkey "$OUTPUT_DIR/ca-key.pem" \
        -CAcreateserial \
        -out "$OUTPUT_DIR/${name}.pem" \
        -days $DAYS \
        -extfile "$OUTPUT_DIR/${name}.ext" \
        2>/dev/null
}

# ---------------------------------------------------------------------------
# 2. Generate 5 sidecar certs
# ---------------------------------------------------------------------------
generate_cert "sidecar-customer" \
    "DNS:localhost,DNS:sidecar-customer,DNS:agents-customer,IP:127.0.0.1"

generate_cert "sidecar-auth" \
    "DNS:localhost,DNS:sidecar-auth,DNS:agents-customer,IP:127.0.0.1"

generate_cert "sidecar-kyc" \
    "DNS:localhost,DNS:sidecar-kyc,DNS:agents-kyc-credit,IP:127.0.0.1"

generate_cert "sidecar-credit" \
    "DNS:localhost,DNS:sidecar-credit,DNS:agents-kyc-credit,IP:127.0.0.1"

generate_cert "sidecar-core-banking" \
    "DNS:localhost,DNS:sidecar-core-banking,DNS:agents-core-banking,IP:127.0.0.1"

# Clean up intermediate files
rm -f "$OUTPUT_DIR"/*.csr "$OUTPUT_DIR"/*.ext "$OUTPUT_DIR"/*.srl

echo ""
echo "==> Mortgage demo PKI generated:"
echo "    CA:             $OUTPUT_DIR/ca.pem"
echo "    Sidecar Customer:     $OUTPUT_DIR/sidecar-customer.pem"
echo "    Sidecar Auth:         $OUTPUT_DIR/sidecar-auth.pem"
echo "    Sidecar KYC:          $OUTPUT_DIR/sidecar-kyc.pem"
echo "    Sidecar Credit:       $OUTPUT_DIR/sidecar-credit.pem"
echo "    Sidecar Core Banking: $OUTPUT_DIR/sidecar-core-banking.pem"
echo ""
echo "    These certs are for DEVELOPMENT ONLY."
