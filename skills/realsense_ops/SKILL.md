# SKILL.md

## Skill ID

`ros-claw/realsense_ops`

## Intent

Keep an Intel RealSense D400 camera streaming for hours without wedging the
device **or the USB host controller**, and recover in the correct escalation
order when the bus wedges anyway.  This is the operations companion to
`realsense_capture_rgbd` (which captures) — it exists because every one of
the failure modes below was produced in the field by *well-intentioned
camera management code*, not by the camera.

## The five iron rules (all field-proven, dates attached)

1. **Graceful lifecycle only.**  Never `SIGTERM`/`kill` a process that owns
   a streaming pipeline; never `echo > /sys/.../reset` the device (a sysfs
   reset of a wedged D435i killed the neighbouring xHCI controller on a
   Jetson, 2026-07).  Always `pipeline.stop()` in-process.
2. **`hardware_reset()` is the LAST resort, never maintenance — and never
   a `start()` default.**  Issue it only when `pipe.start()` has actually
   failed (UVC `GET_CUR` `-110` timeout).  ~20 resets in one day plus ~30
   pipeline stop/start cycles killed xHCI host controller `NVDA8000:00`
   (dmesg: `Host halt failed, -110 → HC died`, 2026-08-03) — and the same
   controller died AGAIN the next morning (2026-08-04) because the rig's
   own capture class (`D435iCapture.start`) reset-first on EVERY start.
   The 2026-07 "reset-first avoids wedges" lesson is only half the truth:
   on firmware 5.17.x each reset is itself the stressor.  The canonical
   `start()` is now the ladder: plain start → one reset only on failure
   (ros-claw/rosclaw PR #218).  Never reset "preventively" between
   captures or cells.
3. **One long-lived pipeline per session.**  Do not stop/start the pipeline
   per capture.  Start once, keep streaming, stop once at shutdown.
4. **Freshness gates must exceed worst-case collector latency.**  A 500 ms
   freshness gate against a serial collector loop (telemetry → blocking
   frame read → inline video write ≈ 1–3 s at dispatch bursts) false-fired
   "camera stale" on every dispatch and triggered rule-2 violations on a
   healthy camera.  Gate ≥ 3 s, and treat the force/interlock path as
   independent of the camera path.
5. **Recovery is an escalation ladder, not a reflex.**  wait 1.5 s +
   re-check → restart pipeline → `hardware_reset()` → physical replug into
   a port on a **different** xHCI controller → (for a dead controller) PCI
   unbind/rebind or reboot.  See `prompts/recovery.md`.

## Preconditions

- A RealSense D400-series device (D405/D415/D435/D435i/D455/D457).
- `pyrealsense2` for live checks; `scripts/realsense_doctor.py` degrades to
  lsusb/sysfs/dmesg when it is absent.

## Effects

- Pipelines stay up for full sessions; resets happen only on real start
  failures; wedges are diagnosed by dmesg signature, not by guess.

## Runtime Contract

- Input: a RealSense device (optionally a serial number to bind).
- Output: a `doctor_report` (enumeration, bus→controller map, dmesg
  signatures, recommended next action) and, when recovery was needed, a
  `recovery_log` of the ladder steps actually taken.

## Safety Envelope

- `real_ok` — this skill only reads USB/kernel state and (on explicit
  request) performs the documented-safe recovery steps.  It never resets
  anything by default.

## Evidence

- Field incidents and fixes: ROSClaw rig, 2026-07-14 .. 2026-08-04
  (incl. both xHCI controller deaths, 2026-08-03 and 2026-08-04).
- Community grounding: librealsense issue #3263 (xHCI halt with D435i),
  Jetson xusb/SMMU crash reports, `usbfs_memory_mb=1024` mitigation,
  firmware 5.13.0.50 for IMU-related freezes, PCI unbind/rebind recovery.
