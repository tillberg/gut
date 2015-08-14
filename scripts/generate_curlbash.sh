#!/usr/bin/env bash
: ${GUT_SH_PATH?"Need to set GUT_SH_PATH"}
CHECKSUM=$(shasum -a256 "$GUT_SH_PATH" | tr -s ' ' ' ' | cut -f 1 -d ' ')
echo bash -c \''S="'$CHECKSUM'";T="/tmp/gut.sh";set -e;wget -qO- https://www.tillberg.us/gut.sh>$T; echo "$S  $T"|shasum -a256 -c-;bash $T;rm $T'\'
