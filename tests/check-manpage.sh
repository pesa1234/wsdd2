#!/bin/sh
#
# Check that every option accepted by getopt() in wsdd2.c is listed in the
# rendered SYNOPSIS of wsdd2.8 and has its own entry in DESCRIPTION.
#
# Usage: tests/check-manpage.sh [wsdd2.c] [wsdd2.8]
#
set -eu

src=${1:-wsdd2.c}
man=${2:-wsdd2.8}

opts=$(sed -n 's/.*getopt(argc, argv, "\([^"]*\)").*/\1/p' "$src" | tr -d ':')
if [ -z "$opts" ]; then
	echo "cannot find the getopt() option string in $src" >&2
	exit 2
fi

# Render without line wrapping or terminal escapes, so the check sees the
# text a reader sees (a stray troff escape can swallow part of a line).
page=$(nroff -man -Tascii -P-c -rLL=500n "$man" 2>/dev/null | col -bx)
synopsis=$(printf '%s\n' "$page" | sed -n '/^SYNOPSIS/,/^DESCRIPTION/p')
description=$(printf '%s\n' "$page" | sed -n '/^DESCRIPTION/,$p')

rc=0
for o in $(printf '%s\n' "$opts" | fold -w1); do
	case "$synopsis" in
	*"[-$o"*) ;;
	*) echo "-$o is missing from the SYNOPSIS of $man" >&2; rc=1 ;;
	esac
	# an entry may list several options, as in "-4 -6"
	if ! printf '%s\n' "$description" | grep -Eq -- "^ *(-[[:alnum:]] +)*-$o( |$)"; then
		echo "-$o has no entry in the DESCRIPTION of $man" >&2
		rc=1
	fi
done

if [ $rc -ne 0 ]; then
	echo "rendered SYNOPSIS:" >&2
	printf '%s\n' "$synopsis" >&2
	exit $rc
fi

echo "all options of $src ($opts) are documented in $man"
