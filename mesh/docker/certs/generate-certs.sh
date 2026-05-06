#!/usr/bin/env bash
# generate-certs.sh — Generate a dev PKI for mTLS between Recursant sidecars.
#
# Creates:
#   ca.pem / ca-key.pem         — Root CA
#   sidecar-a.pem / sidecar-a-key.pem  — Sidecar A (CN=sidecar-a)
#   sidecar-b.pem / sidecar-b-key.pem  — Sidecar B (CN=sidecar-b)
#
# Usage:
#   ./generate-certs.sh [output_dir]
#
# These certs are for DEVELOPMENT ONLY — do not use in production.

set -euo pipefail

OUTPUT_DIR="${1:-$(dirname "$0")}"
mkdir -p "$OUTPUT_DIR"

DAYS=365
KEY_SIZE=2048

echo "==> Generating dev PKI in $OUTPUT_DIR"

# ---------------------------------------------------------------------------
# 1. Root CA
# ---------------------------------------------------------------------------
echo "  [1/3] Root CA"
openssl req -x509 -new -nodes \
    -newkey rsa:$KEY_SIZE \
    -keyout "$OUTPUT_DIR/ca-key.pem" \
    -out "$OUTPUT_DIR/ca.pem" \
    -days $DAYS \
    -subj "/C=GB/O=Recursant Dev/CN=Recursant Dev CA" \
    2>/dev/null

# ---------------------------------------------------------------------------
# 2. Sidecar A
# ---------------------------------------------------------------------------
echo "  [2/3] Sidecar A (CN=sidecar-a, SAN=localhost,host-a)"

cat > "$OUTPUT_DIR/sidecar-a.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=DNS:localhost,DNS:host-a,DNS:sidecar-a,IP:127.0.0.1
EOF

openssl req -new -nodes \
    -newkey rsa:$KEY_SIZE \
    -keyout "$OUTPUT_DIR/sidecar-a-key.pem" \
    -out "$OUTPUT_DIR/sidecar-a.csr" \
    -subj "/C=GB/O=Recursant Dev/CN=sidecar-a" \
    2>/dev/null

openssl x509 -req \
    -in "$OUTPUT_DIR/sidecar-a.csr" \
    -CA "$OUTPUT_DIR/ca.pem" \
    -CAkey "$OUTPUT_DIR/ca-key.pem" \
    -CAcreateserial \
    -out "$OUTPUT_DIR/sidecar-a.pem" \
    -days $DAYS \
    -extfile "$OUTPUT_DIR/sidecar-a.ext" \
    2>/dev/null

# ---------------------------------------------------------------------------
# 3. Sidecar B
# ---------------------------------------------------------------------------
echo "  [3/3] Sidecar B (CN=sidecar-b, SAN=localhost,host-b)"

cat > "$OUTPUT_DIR/sidecar-b.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=DNS:localhost,DNS:host-b,DNS:sidecar-b,IP:127.0.0.1
EOF

openssl req -new -nodes \
    -newkey rsa:$KEY_SIZE \
    -keyout "$OUTPUT_DIR/sidecar-b-key.pem" \
    -out "$OUTPUT_DIR/sidecar-b.csr" \
    -subj "/C=GB/O=Recursant Dev/CN=sidecar-b" \
    2>/dev/null

openssl x509 -req \
    -in "$OUTPUT_DIR/sidecar-b.csr" \
    -CA "$OUTPUT_DIR/ca.pem" \
    -CAkey "$OUTPUT_DIR/ca-key.pem" \
    -CAcreateserial \
    -out "$OUTPUT_DIR/sidecar-b.pem" \
    -days $DAYS \
    -extfile "$OUTPUT_DIR/sidecar-b.ext" \
    2>/dev/null

# Clean up intermediate files
rm -f "$OUTPUT_DIR"/*.csr "$OUTPUT_DIR"/*.ext "$OUTPUT_DIR"/*.srl

echo ""
echo "==> Dev PKI generated:"
echo "    CA:        $OUTPUT_DIR/ca.pem"
echo "    Sidecar A: $OUTPUT_DIR/sidecar-a.pem (key: sidecar-a-key.pem)"
echo "    Sidecar B: $OUTPUT_DIR/sidecar-b.pem (key: sidecar-b-key.pem)"
echo ""
echo "    These certs are for DEVELOPMENT ONLY."
