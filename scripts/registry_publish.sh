#!/usr/bin/env bash
# Publish mcp_server/server.json to the official MCP Registry.
#
#   ./mcp_server/scripts/registry_publish.sh
#
# The registry only stores metadata. It proves you own what the metadata points
# at by re-reading the artifacts, so BOTH must already be published at the exact
# version in server.json before this will succeed:
#
#   - PyPI `mundane-mcp` whose README contains `mcp-name: market.mundane/mundane`
#   - ghcr.io/sttruji/mundane-mcp:<version> carrying the
#     io.modelcontextprotocol.server.name label
#
# Ownership of the `market.mundane` namespace is proved by a DNS TXT record on
# the APEX of mundane.market (not a subdomain, not a selector):
#
#   v=MCPv1; k=ecdsap384; p=<base64 compressed public key>
#
# Regenerate that record's value at any time with:
#   openssl ec -in ~/.mundane/mcp-registry-key.pem -text -noout -conv_form compressed \
#     | grep -A4 "pub:" | tail -n +2 | tr -d ' :\n' | xxd -r -p | base64
set -euo pipefail

DOMAIN="mundane.market"
KEY_FILE="${MUNDANE_REGISTRY_KEY:-$HOME/.mundane/mcp-registry-key.pem}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v mcp-publisher >/dev/null 2>&1 || {
  echo "mcp-publisher not on PATH. Install it with:" >&2
  echo '  brew install mcp-publisher' >&2
  echo "or grab the release binary from" >&2
  echo "  https://github.com/modelcontextprotocol/registry/releases/latest" >&2
  exit 1
}

[ -f "$KEY_FILE" ] || {
  echo "No signing key at $KEY_FILE." >&2
  echo "Losing this key means rotating the DNS TXT record before you can" >&2
  echo "publish again. Restore it from backup rather than regenerating." >&2
  exit 1
}

VERSION="$(python3 -c "import json,sys; print(json.load(open('$HERE/server.json'))['version'])")"
echo "Publishing market.mundane/mundane version $VERSION"

# Fail early with a clear message rather than an opaque ownership error from the
# registry: check the artifacts this metadata points at actually exist.
echo -n "  PyPI mundane-mcp==$VERSION ... "
if curl -sf "https://pypi.org/pypi/mundane-mcp/$VERSION/json" >/dev/null; then
  echo "found"
else
  echo "MISSING"
  echo "Release the package first (bump pyproject.toml, then tag mcp-v$VERSION" >&2
  echo "in the sttruji/mundane-mcp mirror to trigger the publish workflow)." >&2
  exit 1
fi

echo -n "  ghcr.io/sttruji/mundane-mcp:$VERSION ... "
GHCR_TOKEN="$(curl -s "https://ghcr.io/token?scope=repository:sttruji/mundane-mcp:pull&service=ghcr.io" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('token',''))")"
if curl -sf -o /dev/null \
  -H "Authorization: Bearer $GHCR_TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://ghcr.io/v2/sttruji/mundane-mcp/manifests/$VERSION"; then
  echo "found"
else
  echo "MISSING"
  echo "The image build workflow has not pushed this tag yet." >&2
  exit 1
fi

PRIVATE_KEY="$(openssl ec -in "$KEY_FILE" -noout -text 2>/dev/null \
  | grep -A4 "priv:" | tail -n +2 | tr -d ' :\n')"

echo "Authenticating against $DOMAIN via DNS..."
# --algorithm is not optional here. The CLI defaults to ed25519 and will try to
# read our 48-byte P-384 key as a 32-byte ed25519 seed, failing with
# "invalid seed length: expected 32 bytes, got 48". The algorithm must also match
# the `k=` field of the TXT record on the apex.
mcp-publisher login dns \
  --domain "$DOMAIN" \
  --algorithm ecdsap384 \
  --private-key "$PRIVATE_KEY"

cd "$HERE"
mcp-publisher publish

echo
echo "Published. Verify with:"
echo "  curl -s 'https://registry.modelcontextprotocol.io/v0/servers?search=mundane' | python3 -m json.tool"
