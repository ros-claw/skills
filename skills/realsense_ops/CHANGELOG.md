# Changelog

## [1.0.0] - 2026-08-04

### Added
- Initial release: lifecycle discipline, wedge recovery ladder, freshness
  gating rule, USB topology diagnosis (`scripts/realsense_doctor.py`).
- Grounded in TwinTouch-rig field incidents (2026-07-14 UVC wedge after
  SIGTERM; 2026-07 sysfs reset killing xHCI; 2026-08-03 freshness-gate
  false-stale cascade -> ~20 hardware_resets/day -> NVDA8000:00 HC died)
  and community knowledge (librealsense #3263, usbfs_memory_mb=1024,
  D435i IMU firmware 5.13.0.50, PCI unbind/rebind recovery).
