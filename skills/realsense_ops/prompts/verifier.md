# Verifier — read the signature, not your assumptions

Diagnosis is pattern matching against **observed evidence** — never infer a
dead camera from a stale timestamp or from `lsusb` alone.

## The evidence ladder (cheap → deep)

1. `rs-enumerate-devices -s` — proves **USB enumeration only**.  A wedged
   camera enumerates fine; enumeration says nothing about the UVC control
   channel.  Do not declare the camera healthy from this alone, and do not
   declare it dead from a failed `pipe.start()` alone.
2. A minimal `pyrealsense2` start (depth-only, 640×480@30, 3 s) — the
   decisive device-layer test.  Succeeds → the device layer is fine; your
   app layer owns the bug.  Fails with the `-110` xioctl timeout → the
   firmware is genuinely wedged.
3. `dmesg -T | tail -100` — the ground truth for everything below the
   device.  Signatures:

   | Signature | Meaning | Action |
   |---|---|---|
   | `uvcvideo ... Unknown video format 00000050-...` | **Harmless** noise on every enumeration | ignore |
   | `get_xu(...). xioctl(UVCIOC_CTRL_QUERY) failed ... Connection timed out` | UVC control-channel wedge at `pipe.start()` | ladder step 3 (one `hardware_reset`) |
   | `xhci-hcd ... not responding to stop endpoint command` → `Host halt failed, -110` → `HC died; cleaning up` | **The host controller is dead**, not the camera — every device on that controller drops off the bus | ladder step 5/6 (replug to a different controller; PCI rebind or reboot for the dead one) |
   | `device did not re-enumerate` after reset | Firmware not coming back on its own | physical replug (10 s power drain) |
   | `usb 2-1: ... PM: ... autosuspend` near a stall | power-management suspend | disable autosuspend on that port |

4. `scripts/realsense_doctor.py` — runs 1–3 and prints the signature table
   entry matched, plus the bus→controller map.

## False-positive patterns (all cost us real incidents)

- **Freshness-gate trips at dispatch moments** with a continuously
  advancing frame counter: that is collector-loop scheduling, not a wedge.
  Verify by waiting 1.5 s — the timestamp advances.  Fix the gate, not the
  camera.
- **Video stalls but depth/telemetry continues**: consumer-side backup
  (video writer on the read thread).  Not a device fault.
- **`No device connected` after heavy reset/stop-start churn**: the
  controller died, see the `HC died` signature.  A new `pipe.start()` will
  keep failing no matter how often you retry — check dmesg before burning
  more resets.

## Success conditions for a healthy session

- one `pipe.start`, zero mid-session restarts, zero `hardware_reset` calls;
- frame timestamp advancing continuously; video consumer lag bounded;
- any staleness events logged as transient with self-recovery evidence.
