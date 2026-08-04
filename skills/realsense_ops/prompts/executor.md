# Executor — the lifecycle protocol

Everything here has a field date.  Follow the protocol, do not improvise.

## Session protocol

1. **Start once.**  `pipe.start(cfg)` at session start.  If it succeeds,
   the camera is yours until shutdown — do not touch it again.
2. **Read continuously, never block the reader.**  `wait_for_frames()` on a
   dedicated thread; consumers (video writer, upload, heavy per-frame math)
   on other threads fed by bounded queues that DROP on overflow.
3. **Gate staleness to reality.**  Freshness/stale thresholds ≥ 3× the
   measured worst-case collector iteration under dispatch/serial bursts
   (field: a 500 ms gate false-fired at every dispatch on a loop that
   needs 1–3 s in bursts; 3 s works — 2026-08-03).
4. **Treat "stale" as a scheduling symptom first.**  When a freshness gate
   trips: wait ~1.5 s and re-read the frame timestamp.  If it advanced,
   the pipeline is alive — log "transient stall" and CONTINUE.  Only a
   timestamp that stays dead for > 5 s is a real stall.
5. **Stop once, gracefully.**  On shutdown: stop consumers, then
   `pipe.stop()` in-process.  Never `SIGTERM`/`kill -9` a process that owns
   a streaming pipeline (the firmware is left mid-stream; the next start
   wedges — 2026-07-14).  Never touch `/sys/.../reset` or driver
   unbind/bind on the *device* (a sysfs device reset killed a neighbouring
   xHCI controller — 2026-07).

## hardware_reset() — the last resort

Issue `dev.hardware_reset()` **only** when `pipe.start()` itself fails
with the UVC control-channel timeout (`get_xu(...). xioctl(UVCIOC_CTRL_QUERY)
failed ... Connection timed out`, i.e. the `-110` wedge).  Then:

- wait for re-enumeration (~5–8 s) and start ONCE;
- if start fails again, do NOT reset again — escalate (see recovery.md);
- log every reset with timestamp and reason.  If you are resetting more
  than ~2×/day, your lifecycle code is the bug — fix it, not the camera.

`hardware_reset()` is a full USB device reset that re-enumerates.  Each one
is a stress event for the host controller.  **~20 resets + ~30 stop/start
cycles in a single day killed the xHCI host controller** (dmesg: `xhci-hcd
NVDA8000:00: Host halt failed, -110 → HC died`, 2026-08-03) — every device
on that controller fell off the bus.  That outcome is unrecoverable in
software except by PCI rebind of the dead controller or reboot, and the
camera's original port stays dead until then.

## Multi-device rigs

- Put the camera and high-traffic serial adapters on **different xHCI
  controllers** (verify with `scripts/realsense_doctor.py --topology`).
- One process owns the camera.  Two processes streaming the same device
  (or a daemon + ad-hoc scripts) is a wedge generator; if you must share,
  route every frame consumer through the owning process.
