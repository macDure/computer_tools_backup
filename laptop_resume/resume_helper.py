#!/usr/bin/env python3
"""Collect resume evidence or wake an existing GNOME/X11 session without logout."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


def run(args, env=None, seconds=8):
    try:
        result = subprocess.run(
            args, env=env, text=True, errors="replace", stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=seconds, check=False,
        )
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        return 124, "Diagnostic command timed out; desktop processes were left running.\n"
    except OSError as error:
        return 127, str(error) + "\n"


def desktop_context():
    candidates = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            if (process / "comm").read_text().strip() != "gnome-shell":
                continue
            entries = (process / "environ").read_bytes().split(b"\0")
            values = dict(entry.split(b"=", 1) for entry in entries if b"=" in entry)
            candidates.append((process.name, {
                key.decode(): value.decode(errors="replace")
                for key, value in values.items()
                if key in (b"DISPLAY", b"XAUTHORITY", b"XDG_SESSION_TYPE",
                           b"XDG_RUNTIME_DIR", b"DBUS_SESSION_BUS_ADDRESS")
            }))
        except (OSError, ProcessLookupError):
            continue
    if len(candidates) != 1:
        raise RuntimeError("Expected one GNOME session owned by this user; refusing to guess.")
    pid, values = candidates[0]
    if values.get("XDG_SESSION_TYPE") != "x11":
        raise RuntimeError("This helper supports GNOME on X11 only.")
    if not values.get("DISPLAY") or not values.get("XAUTHORITY"):
        raise RuntimeError("The original desktop has no usable DISPLAY/XAUTHORITY context.")
    authority = Path(values["XAUTHORITY"])
    if authority.stat().st_uid != os.getuid() or not os.access(authority, os.R_OK):
        raise RuntimeError("The original desktop authentication file is not accessible.")
    env = os.environ.copy()
    env.update(values)
    return pid, env


def desktop_session(env):
    code, output = run(["loginctl", "list-sessions", "--no-legend", "--no-pager"], env)
    if code:
        raise RuntimeError("Cannot query logind: " + output.strip())
    candidates = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != str(os.getuid()):
            continue
        session = parts[0]
        code, properties = run([
            "loginctl", "show-session", session, "-p", "Type", "-p", "VTNr",
            "-p", "State", "-p", "Remote",
        ], env)
        values = dict(line.split("=", 1) for line in properties.splitlines() if "=" in line)
        if (not code and values.get("Type") == "x11" and values.get("Remote") == "no"
                and values.get("State") != "closing" and values.get("VTNr", "0") != "0"):
            candidates.append((session, values["VTNr"]))
    if len(candidates) != 1:
        raise RuntimeError("Cannot identify a unique existing local X11 session.")
    return candidates[0]


def desktop_process_ids():
    result = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            if (process.stat().st_uid == os.getuid()
                    and (process / "comm").read_text().strip() in {"Xorg", "gnome-shell"}):
                result.append(process.name)
        except OSError:
            continue
    return sorted(result, key=int)


def transition_state(pids):
    result = {
        "time": datetime.datetime.now().astimezone().isoformat(),
        "monotonic_seconds": round(time.monotonic(), 3),
        "boottime_seconds": round(time.clock_gettime(time.CLOCK_BOOTTIME), 3),
        "processes": [],
    }
    try:
        result["active_vt"] = Path("/sys/class/tty/tty0/active").read_text().strip()
    except OSError as error:
        result["active_vt_error"] = str(error)
    for pid in pids:
        path = Path("/proc") / pid
        try:
            result["processes"].append({
                "pid": int(pid), "name": (path / "comm").read_text().strip(),
                "state": (path / "stat").read_text().rsplit(")", 1)[1].split()[0],
                "wait_channel": (path / "wchan").read_text().strip(),
            })
        except OSError as error:
            result["processes"].append({"pid": int(pid), "error": str(error)})
    return result


def checks(env):
    return {
        "memory": ["free", "-h"],
        "processes": ["ps", "-u", str(os.getuid()), "-o", "pid,comm,stat,wchan:32,rss"],
        "session": ["loginctl", "list-sessions", "--no-legend", "--no-pager"],
        "seat": ["loginctl", "show-seat", "seat0", "-p", "ActiveSession",
                 "-p", "CanGraphical", "-p", "CanTTY"],
        "sleep-services": ["systemctl", "is-enabled", "nvidia-suspend.service",
                           "nvidia-resume.service", "nvidia-hibernate.service"],
        "gnome-response": ["gdbus", "call", "--session", "--dest", "org.gnome.Shell",
                           "--object-path", "/org/gnome/Shell", "--method",
                           "org.freedesktop.DBus.Peer.Ping"],
        "lock-response": ["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
                          "--object-path", "/org/gnome/ScreenSaver", "--method",
                          "org.gnome.ScreenSaver.GetActive"],
        "display": ["xrandr", "--current"],
        "screen-power": ["xset", "q"],
        "gpu": ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used",
                "--format=csv,noheader"],
    }


def collect(env, destination):
    if destination:
        directory = Path(destination).expanduser()
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    else:
        directory = Path(tempfile.mkdtemp(prefix="laptop-resume-"))
    (directory / ".laptop-resume-snapshot").write_text("1\n")
    desktop_pids = desktop_process_ids()
    (directory / "transition-state.json").write_text(
        json.dumps(transition_state(desktop_pids), indent=2) + "\n")
    commands = {
        "kernel": ["journalctl", "-b", "-k", "--since", "3 days ago", "--no-pager",
                   "-o", "short-iso", "-n", "250", "--grep",
                   r"NVRM:|i915.*(ERROR|error|failed)|PM: suspend|allocation failure|GPU HANG"],
        "acpi-journal": ["journalctl", "-b", "-k", "--since", "3 days ago", "--no-pager",
                         "-o", "short-iso", "-n", "90", "--grep",
                         r"AE_AML_PACKAGE_LIMIT|ACPI BIOS Error|EC\.(BRNS|ERNS)|EC\._Q2[67]"],
        "sleep-journal": ["journalctl", "-b", "--since", "3 days ago", "--no-pager",
                          "-o", "short-iso", "-n", "180", "-u", "systemd-logind",
                          "-u", "systemd-suspend", "-u", "nvidia-suspend",
                          "-u", "nvidia-resume", "--grep", r"Lid |suspend|resume|Failed"],
        "desktop-journal": ["journalctl", "-b", "--since", "3 days ago", "--no-pager",
                            "-o", "short-iso", "-n", "80", "_COMM=gnome-shell", "--grep",
                            r"JS ERROR|[Tt]imeout|[Ff]ailed|[Cc]rashed|[Ll]ock|[Ss]creen"],
    }
    commands.update(checks(env))
    if desktop_pids:
        commands = {"desktop-threads": ["ps", "-L", "-p", ",".join(desktop_pids),
                                       "-o", "pid,tid,comm,stat,wchan:40"], **commands}
    details = ["Collected: " + datetime.datetime.now().astimezone().isoformat()]
    for path in [Path("/sys/power/mem_sleep"), Path("/proc/driver/nvidia/params"),
                 Path("/sys/power/suspend_stats/success"), Path("/sys/power/suspend_stats/fail"),
                 Path("/proc/buddyinfo"), Path("/proc/meminfo"), Path("/proc/pressure/memory"),
                 Path("/sys/class/tty/tty0/active"),
                 Path("/sys/class/backlight/intel_backlight/brightness"),
                 Path("/sys/class/backlight/intel_backlight/actual_brightness"),
                 Path("/proc/sys/kernel/random/boot_id"), Path("/proc/uptime")]:
        try:
            details.append(str(path) + "\n" + path.read_text())
        except OSError as error:
            details.append(str(path) + ": " + str(error))
    (directory / "power-state.txt").write_text("\n".join(details))
    xorg_logs = list((Path.home() / ".local/share/xorg").glob("Xorg.*.log"))
    if xorg_logs:
        latest_log = max(xorg_logs, key=lambda path: path.stat().st_mtime)
        commands = {"xorg-tail": ["tail", "-n", "180", str(latest_log)], **commands}
    # Write kernel/process evidence before queries that might stall in the GPU driver.
    for name, command in commands.items():
        code, output = run(command, env)
        (directory / (name + ".txt")).write_text(
            "Command: " + " ".join(command) + "\nExit: " + str(code) + "\n" + output)
    print("Evidence saved to " + str(directory.resolve()), flush=True)
    return directory


def monitor():
    # Subscribe to logind, independently of GNOME's ability to draw the lock screen.
    from gi.repository import Gio, GLib

    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "laptop-resume"
    snapshots = state / "snapshots"
    snapshots.mkdir(mode=0o700, parents=True, exist_ok=True)
    children = []
    generation = 0
    events = state / "events.jsonl"
    trace = state / "transition-trace.jsonl"
    trace_remaining = 0
    trace_timer = None
    trace_pids = []

    def record(event):
        entry = {"time": datetime.datetime.now().astimezone().isoformat(), "event": event}
        if events.exists() and events.stat().st_size > 262144:
            events.replace(state / "events.previous.jsonl")
        with events.open("a") as stream:
            stream.write(json.dumps(entry) + "\n")
        print(json.dumps(entry), flush=True)

    def snapshot(label, expected_generation):
        if expected_generation != generation:
            return GLib.SOURCE_REMOVE
        children[:] = [child for child in children if child.poll() is None]
        if len(children) >= 2:
            record("snapshot skipped: two diagnostic collectors are still running")
            return GLib.SOURCE_REMOVE
        previous = sorted(
            path for path in snapshots.iterdir()
            if re.fullmatch(r"snapshot-\d{8}T\d{12}-[a-z0-9-]+", path.name)
            and not path.is_symlink() and path.is_dir()
            and (path / ".laptop-resume-snapshot").is_file()
        )
        for path in previous[:-11]:
            shutil.rmtree(path)
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
        destination = snapshots / ("snapshot-" + stamp + "-" + label)
        child = subprocess.Popen([
            sys.executable, "-B", str(Path(__file__).resolve()), "collect",
            "--output", str(destination),
        ])
        children.append(child)
        record("snapshot started: " + destination.name)
        return GLib.SOURCE_REMOVE

    def trace_sample():
        nonlocal trace_remaining, trace_timer
        if trace.exists() and trace.stat().st_size > 524288:
            trace.replace(state / "transition-trace.previous.jsonl")
        with trace.open("a") as stream:
            stream.write(json.dumps(transition_state(trace_pids)) + "\n")
        trace_remaining -= 1
        if trace_remaining <= 0:
            trace_timer = None
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def start_trace():
        nonlocal trace_remaining, trace_timer, trace_pids
        trace_remaining = 180
        trace_pids = desktop_process_ids()
        if trace_timer is None:
            trace_timer = GLib.timeout_add_seconds(1, trace_sample)
        trace_sample()

    def sleep_signal(connection, sender, object_path, interface, name, parameters, user_data=None):
        nonlocal generation
        sleeping, = parameters.unpack()
        generation += 1
        record("PrepareForSleep(" + str(sleeping).lower() + ")")
        # Start before suspend; resumed sampling does not depend on receiving false.
        start_trace()
        if sleeping:
            GLib.timeout_add_seconds(10, snapshot, "sleep-transition", generation)
        else:
            GLib.timeout_add_seconds(3, snapshot, "resume-3s", generation)
            GLib.timeout_add_seconds(45, snapshot, "resume-45s", generation)

    connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    connection.signal_subscribe(
        "org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
        "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE, sleep_signal, None,
    )
    record("Listening for logind sleep/resume events; snapshots retain the latest 12 sets")
    start_trace()
    GLib.timeout_add_seconds(1, snapshot, "startup-baseline", generation)
    GLib.MainLoop().run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "collect", "wake", "monitor"])
    parser.add_argument("--output", help="New evidence directory; default is a private /tmp directory")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as the desktop user, without sudo.")
    os.umask(0o077)
    try:
        if args.action == "monitor":
            monitor()
            return 0
        try:
            pid, env = desktop_context()
            print("Existing GNOME PID: " + pid + "; DISPLAY=" + env["DISPLAY"], flush=True)
        except (RuntimeError, OSError):
            if args.action != "collect":
                raise
            # A crashed desktop is itself evidence: retain kernel/process logs.
            env = os.environ.copy()
            print("Desktop context unavailable; collecting system evidence anyway.", flush=True)
        if args.action == "check":
            session, vt = desktop_session(env)
            print("Original session: " + session + "; VT: " + vt, flush=True)
            for name, command in checks(env).items():
                code, output = run(command, env)
                print("\n[" + name + "] exit=" + str(code) + "\n" + output, end="", flush=True)
            return 0
        if args.action == "collect":
            collect(env, args.output)
            return 0
        session, vt = desktop_session(env)
        print("Saving evidence before attempting screen recovery.", flush=True)
        collect(env, args.output)
        failures = []
        for command in [["xset", "dpms", "force", "on"], ["xset", "s", "reset"],
                        ["loginctl", "activate", session]]:
            code, output = run(command, env)
            print(" ".join(command) + ": exit=" + str(code) + "\n" + output, end="", flush=True)
            if code:
                failures.append(command[0])
        print("Recovery commands finished. Original desktop is on VT " + vt +
              ". The screen must still be checked visually; its lock was not removed.", flush=True)
        return 1 if failures else 0
    except (RuntimeError, OSError) as error:
        print("Stopped without restarting the desktop: " + str(error), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
