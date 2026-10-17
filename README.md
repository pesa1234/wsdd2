# wsdd2 (1.9.2)
WSD/LLMNR Discovery/Name Service Daemon

With Microsoft turning off SMB1 feature completely on Windows 10, any Samba shares on the
local network become invisible to Windows 10 computers. That's due to the fact that SMB1 is
required for Computer Browser service to function.

Newer Windows systems can use WSD (Web Services for Devices) to discover shares hosted on
other Windows computers while Linux systems normally utilize mDNS/DNS-SD for service discovery.
Microsoft is moving to support mDNS/DNS-SD, but not yet there.

The primary purpose of this project is to enable WSD on Samba servers so that network shares
hosted on a Unix box can appear in Windows File Explorer / Network.

NOTE: Make sure there is no firewall rule blocking WSD multicast address
239.255.255.250 and ff02::c, protocol UDP port 3702. Unicast SOAP HTTP
WS-Discovery responder listens on TCP port 3702.

LLMNR responder listens on multicast 224.0.0.252 / ff02::1:3 UDP port 5355.
LLMNR over TCP is not implemented and no TCP port 5355 listener is opened.

The original source code was taken from Netgear ReadyNAS OS v6.9.3 published at
https://kb.netgear.com/2649/NETGEAR-Open-Source-Code-for-Programmers-GPL
https://www.downloads.netgear.com/files/GPL/ReadyNASOS_V6.9.3_WW_src.zip

Consumed by this openwrt package:
https://github.com/openwrt/packages/tree/master/net/wsdd2

Consumed by this archlinux user repository package:
https://aur.archlinux.org/packages/wsdd2/

## Changes in `1.9.x` compared with `master`

This branch is based on `master` commit `b676d8a` and adds the following
functional commits, listed in history order:

### `36269b1` - Fix bounds checks in network packet parsers

Source: [oldium/wsdd2 pull request #2](https://github.com/oldium/wsdd2/pull/2)

- Rejects WSD HTTP requests without a complete request line instead of
  dereferencing a missing line terminator.
- Validates LLMNR label and question boundaries before reading them, preventing
  truncated network packets from causing out-of-bounds reads.

### `9e25b38` - Fix WSD device metadata parsing and response

Source: [oldium/wsdd2 pull request #1](https://github.com/oldium/wsdd2/pull/1)

- Treats only a comma as the separator between `-b` metadata entries, allowing
  URL values to contain colons.
- Removes an off-by-one error that could retain a metadata delimiter.
- Reports the configured device serial number instead of a hard-coded value.
- Documents the accepted metadata format and the relevant DPWS specification.

### `1a326c9` - Avoid misaligned sockaddr union casts

- Reads IPv4 and IPv6 addresses from their native `sockaddr` structures instead
  of casting them to a more strictly aligned union.
- Verifies that interface addresses and netmasks use the expected address
  family. This is especially relevant on strict-alignment router CPUs.

### `45de58c` - Fix fragmented HTTP header buffer compaction

- Resets parser state after every partial read and validates the number of bytes
  consumed before compacting the buffer.
- Prevents a remotely supplied fragmented WSD HTTP header from causing an
  integer underflow, invalid `memmove()`, and process termination.

### `12bb452` - Disable unimplemented LLMNR TCP listeners

- Removes the IPv4 and IPv6 TCP port 5355 listeners because the handler did not
  implement `accept()` or DNS-over-TCP framing.
- LLMNR multicast and unicast replies over UDP port 5355 remain available.

### `0f1d2ff` - Bound nonblocking WSD TCP request handling

- Handles WSD HTTP clients without blocking the main discovery event loop.
- Limits the server to four concurrent clients, 10,000 bytes per request, and a
  two-second total request deadline, with deferred TCP accept where supported.
- A slow, incomplete, or disconnected client is closed locally and no longer
  restarts the complete service or delays WSD/LLMNR UDP processing.

### `9d2b6b4` - Bound LLMNR DNS name parsing

- Replaces repeated heap reallocation with a fixed 256-byte name buffer and
  linear-time parsing.
- Enforces the DNS limits of 63 bytes per label and 255 bytes for the complete
  wire-format name, and rejects embedded NUL bytes and truncated questions.

### `42c3621` - Avoid null optional WSD metadata values

- Uses empty strings for missing optional metadata URLs instead of passing NULL
  pointers to string formatting functions.
- Prevents undefined behavior on router C libraries and avoids exposing the
  literal text `(null)` in WSD metadata returned to Windows.

### `661a775` - Release version 1.9.0

- Updates the project and Debian package version to 1.9.0.
- Exposes the version in `wsdd2 -h` output and in the daemon startup log, making
  it possible to verify the installed build directly on a target device.

### `06af692` - Fix WSD identity, metadata, and fault responses

- Initializes the WSD identity for TCP-only operation, producing valid endpoint
  UUIDs and instance identifiers without requiring a UDP listener.
- Safely parses blank boot metadata lines, trims line endings, and lets explicit
  `-b` values override metadata read from `/proc/sys/dev/boot/info`.
- Sends SOAP fault responses with one consistent HTTP header and the correct
  `Content-Length` value.

### `17e22be` - Release version 1.9.1

- Updates the project and Debian package version to 1.9.1.
- Records the TCP-only identity, boot metadata parsing, and SOAP fault response
  fixes in the Debian changelog.
- Extends these release notes from version 1.9.0 to the complete 1.9.x branch
  and documents the fixes introduced by `06af692`.

### `a2db581` - Merge pull request #1 from heitbaum/port2

Source: [pesa1234/wsdd2 pull request #1](https://github.com/pesa1234/wsdd2/pull/1)
by Rudi Heitbaum, which cherry-picks the commits of
[oldium/wsdd2](https://github.com/oldium/wsdd2) that `master` lacks, keeping
their authorship.

From oldium/wsdd2:

- `77a7597`, `7d69743`, `fe5366b`, `86ce598`, `a976485`: add `-c <file>` to
  read a non-default `smb.conf`, start without `testparm` by deriving the host
  and NetBIOS names from the system host name, accept the empty reply of
  `testparm` for a parameter that is not set, log successful queries, and
  show in `wsdd2 -h` which `smb.conf` is read, or that `testparm` was not
  found.
- `4c078f5`: parses the command line first and fills only the values that are
  still missing, so command-line options take precedence over `smb.conf`.
- `cdaf730`: adds the `-A` and `-B` options for the DNS host aliases and the
  NetBIOS aliases.
- `678e3ce`: accepts a WSD request `Content-Type` followed by parameters, such
  as `application/soap+xml; charset=utf-8`, which was rejected with HTTP 400.
- `ef83cfe`, `cf1ffeb`: fix `size_t`/`ssize_t` format and `socklen_t` pointer
  warnings.

From Rudi Heitbaum:

- `f3a5578`: boot metadata from `/proc/sys/dev/boot/info` only fills the keys
  that are still unset, so `-b` keeps precedence now that the command line is
  parsed first.
- `d853643`, `aa11300`, `a496ddf`, `cdb3e2c`: fix the `calloc()` argument
  order, keep the interface name NUL-terminated, check the `chdir()` result
  when daemonising, and make the locals used after `longjmp()` volatile. The
  code now builds with `-Wall -Wextra -Werror` at every optimisation level.
- `6115c12`: widens the UUID word before the shift in `set_seed()`, removing
  undefined behaviour reported by UBSan.
- `a2ce2c6`, `d334422`: restore `-c`, `-H` and `-A` in the man page synopsis
  and fix spelling.

### `c7f2c51` - Use designated initializers for struct msghdr

- Fixes the build with GCC 14 and later on 64-bit musl, where `struct msghdr`
  has padding members and the positional initializer put a NULL pointer into
  an `int` field.
- Makes the OpenWrt `010-gcc14.patch` unnecessary.

### `95494b7` - Add CI workflow and smoke tests

- Builds with gcc and clang from `-O0` to `-O3` with `-Werror`, and with musl
  on Alpine.
- Runs `tests/smoke.py` under ASan and UBSan: WS-Discovery Probe and
  WS-Transfer Get on the loopback interface, then the same checks after
  netlink-triggered restarts and SIGHUP in a private network namespace.
- Checks with `tests/check-manpage.sh` that every option is documented in
  `wsdd2.8`, and on pull requests that every commit builds.
