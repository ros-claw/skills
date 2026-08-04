# RealSense Ops

Operational discipline for Intel RealSense D400 cameras on production rigs:
keep the pipeline alive for whole sessions, never kill the USB host
controller with recovery churn, and climb a fixed escalation ladder when
the bus wedges anyway.

## What it does

- Five iron rules for camera lifecycle (graceful stop only; `hardware_reset`
  reserved for actual `pipe.start()` failure; one long-lived pipeline per
  session; freshness gates sized >=3x worst-case collector iteration;
  escalation-ordered recovery).
- `scripts/realsense_doctor.py` — one-shot diagnosis: device enumeration,
  USB bus → xHCI controller topology map, dmesg wedge-signature scan, and
  an optional 3 s depth-only live probe (`--start-test`).
- Prompts for planner/executor/verifier/recovery/safety encoding the full
  runbook, grounded in field incidents (2026-07-14 .. 2026-08-03) and
  community knowledge (librealsense #3263, usbfs_memory_mb, firmware notes,
  PCI rebind recovery).

## Supported robots

- `realsense_d435i`, `realsense_d405`, or any rig carrying a D400 camera
  (perception-only or alongside actuated bodies).

## Required sensors

- `depth_camera` (`color_camera` optional)

## Safety constraints

- See `safety.yaml` and `prompts/safety.md`.
- Default runtime mode: `real_ok` — the skill reads USB/kernel state and
  only performs documented-safe recovery steps on explicit request.

## How to run

```bash
python3 scripts/realsense_doctor.py                 # diagnosis report
python3 scripts/realsense_doctor.py --topology      # bus → controller map
python3 scripts/realsense_doctor.py --start-test    # 3s depth-only probe
```

## Required providers

- None beyond `pyrealsense2` (optional) and standard Linux USB tooling.

## Version history

- 1.0.0 (2026-08-04): initial release.

## Known limitations

- `realsense_doctor.py` reads dmesg best-effort; without sudo the kernel
  signature section reports "unreadable" instead of signatures.
- PCI unbind/rebind recovery (rung 5) is documented, not automated — it
  requires operator confirmation and a verified PCI address.
- Firmware flashing (IMU freeze workaround) is out of scope; use RealSense
  Viewer on a PC.

## Evaluation evidence

- Field incidents and fixes: ROSClaw TwinTouch rig, 2026-07-14 .. 2026-08-03.
