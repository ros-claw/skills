# Planner — when you reach for this skill

Use this skill whenever code you are writing or reviewing **owns a RealSense
pipeline for longer than a single capture** — streaming apps, telemetry
collectors, video recorders, multi-hour test rigs, and any recovery logic.

## Decide your streaming architecture first

1. **One pipeline per session, not per capture.**  `pipe.start()` once at
   session start; `pipe.stop()` once at shutdown.  Per-capture stop/start is
   the #1 wedge producer (UVC control-channel state degrades across
   restarts; ~30 restarts/day is a proven kill pattern).
2. **Decouple slow consumers from the read loop.**  A video writer, an
   uploader, or a heavy per-frame computation on the same thread as
   `wait_for_frames()` backs the loop up to seconds per iteration.  Put
   writers on their own thread with a bounded queue (drop frames when full —
   never block the reader).
3. **Size freshness/staleness gates to the loop, not to the frame rate.**
   Measure the worst-case iteration of your collector under load (dispatch
   bursts, serial contention).  The gate must be ≥ 3× that.  A gate tuned
   to the nominal frame interval false-fires under load and starts the
   reset cascade this skill exists to prevent.
4. **Keep interlocks independent.**  Safety interlocks (force watchdogs,
   E-stop paths) must not depend on the camera being healthy, and camera
   recovery must never interlock motion by reflex — degrade gracefully
   (pause new dispatches), don't reflexively reset hardware.

## If you are here because something already broke

Go straight to `prompts/verifier.md` (read the dmesg/error signature) and
then `prompts/recovery.md` (the ladder).  Do not improvise resets.

## If you are provisioning a new rig

- Map the USB topology BEFORE placing devices: put the camera and any
  high-traffic serial adapters on **different xHCI controllers** where
  possible (`scripts/realsense_doctor.py --topology`), and confirm the
  camera lands on a SuperSpeed (5000/10000 M) bus — a 480 M (USB2) bus is
  a silent bandwidth trap, not a fault.
- Raise `usbfs_memory_mb` to 1024 (community-proven mitigation for D435i
  dropouts: `sudo sh -c 'echo 1024 > /sys/module/usbcore/parameters/usbfs_memory_mb'`).
- Disable USB autosuspend for the camera port.
- For D435i IMU freezes on Jetson JetPack 6.x, firmware 5.13.0.50 is the
  community-verified workaround (flash via RealSense Viewer on a PC).
- Record model/serial/firmware/USB-speed once at first verification and
  pin all later commands to that serial — on multi-camera rigs, confirm
  WHICH physical camera before streaming anything.
