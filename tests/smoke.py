#!/usr/bin/env python3
"""
WSD smoke test for wsdd2.

Starts wsdd2 on the loopback interface, sends a WS-Discovery Probe and
WS-Transfer Get requests and checks the replies, then stops it and checks
that it exited cleanly with no sanitizer report in its output.

With --restart it must run as root in a network namespace of its own
(sudo unshare -n tests/smoke.py --restart ./wsdd2): it then also adds and
removes an address on lo, which makes wsdd2 restart through longjmp(), sends
SIGHUP, and checks that the daemon still answers after each restart.

Usage: tests/smoke.py [--restart] [--log FILE] ./wsdd2
"""

import argparse
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

HOST = "127.0.0.1"
PORT = 3702
SANITIZER_RE = re.compile(r"runtime error:|ERROR: AddressSanitizer|ERROR: LeakSanitizer")

PROBE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" \
xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" \
xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery" \
xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof">
<soap:Header><wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
<wsa:MessageID>urn:uuid:{msgid}</wsa:MessageID></soap:Header>
<soap:Body><wsd:Probe><wsd:Types>wsdp:Device</wsd:Types></wsd:Probe></soap:Body>
</soap:Envelope>"""

GET = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" \
xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
<soap:Header><wsa:To>urn:uuid:{endpoint}</wsa:To>
<wsa:Action>http://schemas.xmlsoap.org/ws/2004/09/transfer/Get</wsa:Action>
<wsa:MessageID>urn:uuid:{msgid}</wsa:MessageID>
<wsa:ReplyTo><wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous\
</wsa:Address></wsa:ReplyTo></soap:Header><soap:Body/></soap:Envelope>"""

# Content-Type value -> expected HTTP status
CONTENT_TYPES = [
    ("application/soap+xml", 200),
    ("application/soap+xml; charset=utf-8", 200),
    ("application/soap+xml;charset=utf-8", 200),
    ("application/soap+xmlfoo", 400),
    ("text/xml", 400),
]

failures = []


def check(ok, what):
    print(("ok    " if ok else "FAIL  ") + what, flush=True)
    if not ok:
        failures.append(what)
    return ok


def probe(timeout=1.0):
    """Send a Probe; return the endpoint UUID from the ProbeMatches XAddrs."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(PROBE.format(msgid=uuid.uuid4()).encode(), (HOST, PORT))
        try:
            data = s.recv(65535).decode(errors="replace")
        except socket.timeout:
            return None
    if "/discovery/ProbeMatches<" not in data:
        return None
    m = re.search(r"<wsd:XAddrs>http://[^/<]+/([0-9a-f-]{36})</wsd:XAddrs>", data)
    return m.group(1) if m else None


def wait_probe(seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        endpoint = probe()
        if endpoint:
            return endpoint
        time.sleep(0.2)
    return None


def http_get(endpoint, ctype):
    """Send a WS-Transfer Get; return (status, body)."""
    body = GET.format(endpoint=endpoint, msgid=uuid.uuid4()).encode()
    head = (f"POST /{endpoint} HTTP/1.1\r\n"
            f"Host: {HOST}:{PORT}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode()
    resp = b""
    with socket.create_connection((HOST, PORT), timeout=3) as s:
        s.sendall(head + body)
        try:
            while chunk := s.recv(65535):  # the server sends "Connection: close"
                resp += chunk
        except socket.timeout:
            pass
    m = re.match(rb"HTTP/1\.[01] (\d{3})", resp)
    return (int(m.group(1)) if m else None), resp.decode(errors="replace")


def log_count(log, text):
    log.flush()
    log.seek(0)
    return log.read().count(text)


def wait_log(log, text, count, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if log_count(log, text) >= count:
            return True
        time.sleep(0.1)
    return False


def check_answers(label):
    endpoint = wait_probe()
    if not check(endpoint is not None, f"{label}: Probe gets ProbeMatches"):
        return
    for ctype, expected in CONTENT_TYPES:
        status, body = http_get(endpoint, ctype)
        check(status == expected,
              f"{label}: Get with Content-Type '{ctype}' -> {status} (want {expected})")
        if ctype == "application/soap+xml" and status == 200:
            check("<wsdp:ThisDevice>" in body and "<wsdp:Relationship " in body,
                  f"{label}: Get response carries the device metadata")


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("wsdd2", help="path to the wsdd2 binary")
    ap.add_argument("--restart", action="store_true",
                    help="also test restarts (root in its own network namespace)")
    ap.add_argument("--log", help="also copy the daemon output to this file")
    args = ap.parse_args()

    if args.restart:
        subprocess.run(["ip", "link", "set", "lo", "up"], check=True)

    log = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen([args.wsdd2, "-w", "-4", "-i", "lo", "-W"],
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        check_answers("start")

        if args.restart:
            subprocess.run(["ip", "addr", "add", "127.0.0.2/8", "dev", "lo"], check=True)
            check(wait_log(log, "restarting service", 1),
                  "address added: netlink restart (longjmp) happened")
            check_answers("after netlink restart")

            subprocess.run(["ip", "addr", "del", "127.0.0.2/8", "dev", "lo"], check=True)
            check(wait_log(log, "restarting service", 2),
                  "address removed: netlink restart (longjmp) happened")
            check_answers("after second netlink restart")

            proc.send_signal(signal.SIGHUP)
            check(wait_log(log, "'Hangup' signal received", 1), "SIGHUP received")
            check_answers("after SIGHUP")

        check(proc.poll() is None, "daemon still running")
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()

    check(rc == 0, f"daemon exit status {rc} (want 0)")
    log.seek(0)
    output = log.read()
    check(not SANITIZER_RE.search(output), "no sanitizer report in the daemon output")

    if args.log:
        with open(args.log, "w") as f:
            f.write(output)
    if failures:
        print("\n--- daemon output ---\n" + output[-20000:], file=sys.stderr)
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
