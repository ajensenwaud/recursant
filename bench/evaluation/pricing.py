"""Reported-dollar costing, identical for every arm. NOT the admission bound.

Admission (live.admission) reserves a conservative byte-bound liability with
no caching discount; that number is never reported as spend. Reported dollars
per call come from, in order:
  1. provider-reported usage.cost (OpenRouter: USD, includes cache discounts);
  2. provider-reported usage tokens x frozen list price, cached tokens at the
     cached price (docs/evidence/m3-openrouter-price-snapshot.json);
  3. otherwise unknown (None). Unknown is never zero.
Private-trust calls carry no public-provider charge; private resource
economics remain separately unknown.
"""
import math

# USD per million tokens, frozen from the OpenRouter public list snapshot
# (fetched 2026-09-28T20:31:05Z). Only whitelisted admission models.
LIST_PRICES = {
    'openai/gpt-4.1': {'input_per_mtok': 2.0, 'output_per_mtok': 8.0, 'cached_input_per_mtok': 0.5},
    'openai/gpt-4.1-mini': {'input_per_mtok': 0.4, 'output_per_mtok': 1.6, 'cached_input_per_mtok': 0.1},
    # OpenRouter list 2026-10-04 (fallback only: OpenRouter reports usage.cost on every call).
    'anthropic/claude-sonnet-5.5': {'input_per_mtok': 2.0, 'output_per_mtok': 10.0, 'cached_input_per_mtok': 0.2},
}
PRICE_SOURCE = 'docs/evidence/m3-openrouter-price-snapshot.json (via recursant-v4 c2aa46c)'
SOURCES = ('provider_usage_cost', 'list_price_tokens', 'private_trust_no_public_charge', 'unknown')
METHOD = ('per call: provider usage.cost when reported, else provider usage tokens x frozen list '
          'price with cached_tokens at cached price; private-trust calls have no public charge; '
          'identical for every arm; admission liability is a separate conservative bound')


def _count(value):
    return type(value) is int and value >= 0


def list_price_cost(call):
    """Token-derived list-price dollars, or None when usage/price is unknown."""
    price = LIST_PRICES.get(call.get('requested_model'))
    tokens_in, tokens_out = call.get('input_tokens'), call.get('output_tokens')
    semantics = call.get('reasoning_semantics')
    if price is None or not _count(tokens_in) or not _count(tokens_out) or semantics not in ('inclusive', 'additive'):
        return None
    cached = call.get('cached_input_tokens')
    if cached is None: cached = 0  # No cache evidence: full input price.
    if not _count(cached) or cached > tokens_in: return None
    output = tokens_out
    if semantics == 'additive':
        if not _count(call.get('reasoning_tokens')): return None
        output += call['reasoning_tokens']
    return ((tokens_in - cached) * price['input_per_mtok'] + cached * price['cached_input_per_mtok'] +
            output * price['output_per_mtok']) / 1e6


def call_cost(call):
    """Return (usd or None, source label) for one dispatched attempt."""
    endpoint = call.get('endpoint')
    if endpoint == 'private':
        return 0.0, 'private_trust_no_public_charge'
    if endpoint != 'public':
        return None, 'unknown'
    reported = call.get('cost_usd')
    if reported is not None:
        if type(reported) in (int, float) and math.isfinite(reported) and reported >= 0:
            return float(reported), 'provider_usage_cost'
        return None, 'unknown'  # Malformed provider cost is not replaced by a guess.
    listed = list_price_cost(call)
    return (listed, 'list_price_tokens') if listed is not None else (None, 'unknown')
