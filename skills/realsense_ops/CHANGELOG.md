# Changelog

## [1.1.0] - 2026-08-04

### Changed
- Rule 2/3 sharpened: `hardware_reset` is never a `start()` DEFAULT either —
  the 2026-07 "reset-first" lesson is retired (plain start first; reset only
  on failure).  Trigger: the rig's own `D435iCapture.start` reset-first on
  every start and killed NVDA8000:00 a SECOND time (2026-08-04); the
  canonical class is fixed to the ladder (ros-claw/rosclaw PR #218).
- New mandatory rule: camera reads and safety telemetry/watchdog on
  DIFFERENT threads — a hung `wait_for_frames()` (mid-stream stall blocks
  PAST its timeout) froze telemetry+watchdog and cascaded four aborted
  runs (2026-08-04).  Both gates tripping together = app threading bug.
- Gate sizing generalised: EVERY freshness gate sized to the producer it
  watches (camera 500ms→3s, telemetry 1.0s→3s; `cap.read`'s 2s blocking
  timeout sets the loop's worst-case iteration).
- Startup/burst staleness protocol: wait 1.2–1.5s + retry the dispatch
  ONCE — clears without any hardware action.

## [1.0.0] - 2026-08-04

### Added
- Initial release: lifecycle discipline, wedge recovery ladder, freshness
  gating rule, USB topology diagnosis (`scripts/realsense_doctor.py`).
- Grounded in TwinTouch-rig field incidents (2026-07-14 UVC wedge after
  SIGTERM; 2026-07 sysfs reset killing xHCI; 2026-08-03 freshness-gate
  false-stale cascade -> ~20 hardware_resets/day -> NVDA8000:00 HC died)
  and community knowledge (librealsense #3263, usbfs_memory_mb=1024,
  D435i IMU firmware 5.13.0.50, PCI unbind/rebind recovery).
