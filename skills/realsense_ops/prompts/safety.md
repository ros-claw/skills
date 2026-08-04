# Safety — the never-do list

Violating any of these has killed hardware state in the field.  Dates are
the incident each rule comes from.

1. **Never `SIGTERM`/`kill` a process owning a streaming pipeline.**
   Firmware is left mid-stream; the next `pipe.start()` wedges (2026-07-14).
   Stop in-process, gracefully.
2. **Never sysfs-reset the device** (`echo > /sys/bus/usb/devices/.../reset`)
   and never driver unbind/bind the *device*.  A sysfs reset of a wedged
   D435i killed a neighbouring xHCI host controller (2026-07).  The only
   sanctioned unbind/rebind is of an **already-dead xHCI controller**, by
   verified PCI address (see recovery.md rung 5).
3. **Never `hardware_reset()` preventively** — not before sessions, not
   between captures, not "because it's been a while".  It is reserved for
   an actually-failed `pipe.start()` (-110 wedge).  ~20 in a day destroyed
   a host controller (2026-08-03).
4. **Never retry `pipe.start()` in a tight loop** after a wedge — each
   attempt pokes the wedged control channel.  Escalate instead (rung 3+).
5. **Never let a freshness gate tighter than the collector's worst-case
   iteration drive hardware recovery.**  Software-scheduling artifacts must
   only ever trigger *logging* and *graceful degradation* (pause new
   dispatches); hardware actions require a genuinely dead frame timestamp
   (> 5 s).
6. **Never share one camera between two processes** streaming concurrently.
7. **Never block safety interlocks on camera health.**  Force watchdogs and
   E-stop paths run on their own channels; a camera incident degrades the
   show, never the interlock.
8. **Never trust `lsusb`/enumeration as health.**  A wedged camera
   enumerates.  Health = frames flowing; wedge = `-110` at start; dead
   controller = `HC died` in dmesg.  Those are three different failures
   with three different recoveries — do not apply one recovery to another.
9. **Gate privileged/persistent actions on explicit confirmation** — sudo,
   udev rule edits, firmware updates, factory resets, PCI rebinds, global
   pip/project-dependency changes.  Non-privileged diagnosis (isolated
   venv, reading logs, rerunning the repro) runs freely.
10. **Never compile librealsense from source** as a fix path — if that
    seems required, the correct move is a support packet, not a toolchain
    adventure on a production rig.
11. **Pin every command to a serial number** on multi-camera rigs; on a
    one-camera rig still record model/serial/firmware/USB-speed at session
    start so later drift is detectable.
