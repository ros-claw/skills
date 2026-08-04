#!/usr/bin/env python3
"""realsense_doctor — one-shot RealSense/USB health diagnosis.

Part of the ros-claw/realsense_ops skill.  Standalone: plain python3;
pyrealsense2 optional (deep tests are skipped without it).  Read-only by
default — with --start-test it opens a depth-only pipeline for 3 s (a
graceful open+stop, the documented-safe device-layer probe).

Usage:
  realsense_doctor.py              # enumerate + topology + dmesg signatures
  realsense_doctor.py --topology   # just the bus -> xHCI controller map
  realsense_doctor.py --start-test [--serial SN]   # 3s depth-only live probe
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

DMESG_SIGNATURES = [
    ("HC_DEAD", re.compile(r"xhci-hcd (\S+):.*?(Host halt failed|not responding, assume dead|HC died)"),
     "host controller DEAD — everything on that bus is offline; replug camera to a DIFFERENT controller, PCI-rebind or reboot for the dead one"),
    ("UVC_WEDGE", re.compile(r"xioctl\(UVCIOC_CTRL_QUERY\) failed.*(timed out|-110)"),
     "UVC control-channel wedge at pipe.start — ONE hardware_reset, then escalate per recovery ladder"),
    ("REENUM_FAIL", re.compile(r"did not re-enumerate", re.I),
     "firmware not coming back — physical replug with 10s power drain"),
    ("FORMAT_NOISE", re.compile(r"Unknown video format 00000050-"),
     "harmless enumeration noise — ignore"),
]


def run(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return -1, f"<{type(exc).__name__}: {exc}>"


def enumerate_rs() -> list[dict]:
    try:
        import pyrealsense2 as rs  # type: ignore
    except Exception:
        return [{"note": "pyrealsense2 not importable in this interpreter"}]
    out = []
    try:
        for d in rs.context().query_devices():
            out.append({
                "name": d.get_info(rs.camera_info.name),
                "serial": d.get_info(rs.camera_info.serial_number),
                "firmware": d.get_info(rs.camera_info.firmware_version),
            })
    except Exception as exc:  # noqa: BLE001
        out.append({"error": f"query_devices failed: {exc}"})
    return out


def topology() -> list[dict]:
    """Map each usb bus to its PCI xHCI controller."""
    rows = []
    for path in sorted(glob.glob("/sys/bus/usb/devices/usb*"), key=lambda p: int(p.rsplit("usb", 1)[1])):
        bus = os.path.basename(path)
        real = os.path.realpath(path)
        m = re.search(r"([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9]|NVDA[0-9]+:[0-9]+)", real)
        ctrl = m.group(1) if m else "?"
        rc, speed = run(["cat", f"{path}/speed"], timeout=3)
        rows.append({"bus": bus, "controller": ctrl, "speed": speed if rc == 0 else "?"})
    return rows


def dmesg_hits() -> list[dict]:
    rc, out = run(["dmesg", "-T"], timeout=15)
    if rc != 0:
        return [{"note": "dmesg unreadable without sudo — rerun with sudo for kernel signatures"}]
    lines = out.splitlines()[-400:]
    hits = []
    for tag, rx, advice in DMESG_SIGNATURES:
        matched = [l for l in lines if rx.search(l)]
        if matched:
            hits.append({"signature": tag, "count": len(matched),
                         "last": matched[-1].strip()[:160], "advice": advice})
    return hits


def start_test(serial: str | None) -> dict:
    try:
        import pyrealsense2 as rs  # type: ignore
    except Exception:
        return {"skipped": "pyrealsense2 not importable"}
    pipe = rs.pipeline()
    cfg = rs.config()
    if serial:
        cfg.enable_device(serial)
    cfg.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    t0 = time.time()
    try:
        pipe.start(cfg)
        fs = pipe.wait_for_frames(3000)
        w = fs.get_depth_frame().get_width()
        return {"ok": True, "elapsed_s": round(time.time() - t0, 2), "depth_width": w,
                "verdict": "device layer HEALTHY — app layer owns any remaining bug"}
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        wedge = "xioctl" in msg or "timed out" in msg or "No device connected" in msg
        return {"ok": False, "error": msg[:200],
                "verdict": ("-110-style wedge — climb the recovery ladder (one hardware_reset, then escalate)"
                            if wedge else "start failed — check config/cable, then ladder")}
    finally:
        try:
            pipe.stop()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topology", action="store_true")
    ap.add_argument("--start-test", action="store_true")
    ap.add_argument("--serial", default=None)
    args = ap.parse_args()

    report: dict = {"tool": "realsense_doctor", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if args.topology:
        report["topology"] = topology()
        print(json.dumps(report["topology"], indent=2))
        return 0

    report["devices"] = enumerate_rs()
    report["topology"] = topology()
    report["dmesg_signatures"] = dmesg_hits()
    if args.start_test:
        report["start_test"] = start_test(args.serial)

    rec = []
    sigs = {h.get("signature") for h in report["dmesg_signatures"]}
    if "HC_DEAD" in sigs:
        rec.append("A host controller is DEAD — do not reset anything; replug the camera to a different controller's port; PCI-rebind the dead controller or reboot.")
    if "UVC_WEDGE" in sigs or "REENUM_FAIL" in sigs:
        rec.append("Wedge signature present — follow prompts/recovery.md ladder; count today's resets first.")
    if not report["devices"] or all("note" in d or "error" in d for d in report["devices"]):
        rec.append("No device via pyrealsense2 — check enumeration (rs-enumerate-devices -s) and dmesg HC_DEAD above.")
    if not rec:
        rec.append("No kernel-level faults detected. If streaming still fails, it is an app-layer bug (collector loop, freshness gate, consumer backup).")
    report["recommendation"] = rec
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
