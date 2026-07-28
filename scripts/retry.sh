#!/usr/bin/env bash
# Retry a command with linear backoff. Usage: retry.sh <max_attempts> <cmd...>
#
# Exists because the Pages deploy's network steps (MLBMA slate sync, Odds API
# fetches) occasionally fail on a transient blip — a single flaky fetch was
# enough to fail the whole build and freeze the live site on a stale slate.
# Wrapping the fatal network calls in a few retries turns a transient hiccup
# into a short delay instead of a failed deploy.
set -u
max="$1"; shift
attempt=1
until "$@"; do
  if [ "$attempt" -ge "$max" ]; then
    echo "retry: '$*' failed after $attempt attempt(s)" >&2
    exit 1
  fi
  wait=$((attempt * 15))
  echo "retry: attempt $attempt of '$*' failed; retrying in ${wait}s..." >&2
  sleep "$wait"
  attempt=$((attempt + 1))
done
