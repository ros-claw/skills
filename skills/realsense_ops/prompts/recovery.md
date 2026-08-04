# Recovery — the escalation ladder

Climb in order.  Never skip rungs, never loop a rung that already failed,
and log every step (timestamp, rung, observed result) — the log is what
lets the next agent avoid re-walking the ladder blind.

## Rung 1 — wait + re-check (seconds, zero risk)

Staleness at dispatch/burst moments is usually collector scheduling.
Wait 1.5 s, re-read the frame timestamp.  Advanced → continue normally,
note "transient stall".  Dead > 5 s → rung 2.

## Rung 2 — graceful pipeline restart (seconds, low risk)

In-process: `pipe.stop()` (graceful, must not throw — suppress and
continue), then `pipe.start(cfg)` once — **plainly, without a reset**
(the canonical `D435iCapture.start` implements exactly this ladder since
ros-claw/rosclaw PR #218).  If start succeeds and frames
flow, done.  If start throws the `-110` xioctl timeout → rung 3.  Do not
loop this rung: one restart per incident.

## Rung 3 — ONE hardware_reset (tens of seconds, stress event)

`dev.hardware_reset()`, wait for re-enumeration (poll
`rs.context().query_devices()` up to ~10 s), then `pipe.start()` once.
Frames → done.  Start fails again, or the device does not re-enumerate →
rung 4.  **Never issue a second reset for the same incident.**

## Rung 4 — physical replug (operator action, minutes)

Ask the operator to unplug the camera, wait 10 s (power drain), and plug
it into a **different physical port on a healthy controller** — not the
port it came from if that port's controller ever logged `HC died`
(check `dmesg`; map ports with `realsense_doctor.py --topology`).
Then rung 2 (plain start, no reset).

## Rung 5 — dead-controller recovery (root, minutes)

Only when dmesg shows `xhci-hcd <CTRL>: ... HC died` for the controller
behind the camera's bus.  The community-standard no-reboot recovery is a
PCI unbind/rebind **of the dead controller only**:

```bash
# find the dead controller's PCI address (e.g. from the dmesg line or
# readlink -f /sys/bus/usb/devices/usbN | grep -oE '[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9]')
echo -n "0000:XX:YY.Z" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind
sleep 2
echo -n "0000:XX:YY.Z" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind
```

CAUTION: unbind drops EVERY device on that controller.  Verify by PCI
address, never by guess; on Jetson boards a mis-targeted sysfs USB
operation has killed a *healthy* neighbouring controller (2026-07 field
note).  If any doubt: reboot instead — it is slower and strictly safer.

## Rung 6 — reboot / hardware support

Controller still dead after rebind, or camera still absent after replug:
reboot the rig.  If it recurs across reboots with light usage, write a
support packet (dmesg log, topology map, firmware version, cable/port
used) for https://github.com/realsenseai/librealsense/issues — include
the reset/restart counts from your log; they are the smoking gun.

## Preventive configuration (apply once per rig, not per incident)

- `sudo sh -c 'echo 1024 > /sys/module/usbcore/parameters/usbfs_memory_mb'`
  (D435i dropout mitigation, community-proven).
- Disable USB autosuspend for the camera port.
- D435i IMU freezes on Jetson JetPack 6.x → firmware 5.13.0.50.
- Persistent udev rule naming the camera by serial, so the topology map
  survives replugs.
