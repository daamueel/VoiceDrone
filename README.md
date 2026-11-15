# VoiceDrone

VoiceDrone runs deterministic takeoff, circle, relative move, and land commands in PX4 SITL
through a persistent MAVSDK session. Keyboard text and local speech use the
same validated command parser and flight session. Real hardware control is not
implemented.

## Project status

- [x] WSL2 with Ubuntu 24.04 verified
- [x] WSL network, DNS, HTTPS, Git, and GitHub access verified
- [x] PX4 v1.17.0 and recursive submodules verified
- [x] Gazebo Harmonic and PX4 simulation assets verified
- [x] Windows Python 3.11 and MAVSDK environment verified
- [x] PX4 SITL and the Gazebo x500 verified together
- [x] Windows-to-WSL telemetry verified
- [x] Independent takeoff behavior implemented and flight-tested
- [x] Independent side, centered center-facing (`circle_centripetal`), and
      centered fixed-yaw (`circle`) behaviors implemented and flight-tested
- [x] Takeoff, circle, and runner-controlled landing flight-tested together
- [x] Persistent keyboard control, safe landing, and connection-loss behavior
      tested in PX4 SITL
- [x] Local microphone transcription and confirmed spoken takeoff, circle,
      and land tested in PX4 SITL
- [x] Continuous Silero VAD listening verified with spoken takeoff, circle,
      and land in visible Gazebo SITL

See [documentation/setup.md](documentation/setup.md) for the verified toolchain
and [documentation/architecture.md](documentation/architecture.md) for the
coordinate and component design.

Python source lives under `src/flight`, `src/control`, and `src/voice`. The
`src/cv` and `src/rl` packages remain placeholders. Tests are under `tests/`.

## Command control

Run keyboard commands without PX4 to inspect parsing and state transitions:

```powershell
voicedrone-control
```

With PX4 v1.17.0 and Gazebo x500 running and routed to Windows, the SITL
controllers are:

```powershell
voicedrone-control --sitl
voicedrone-voice --sitl --device 1
```

The voice controller asks for Enter once, then listens continuously. It waits
for a completed phrase, shows the transcript and interpreted action, and
requires `Y` or `y` before execution. `N` or `n` skips the command. Press `Q`
while listening to end the session; press `L` during a maneuver to land
immediately. The speech controller is limited to the verified PX4/Gazebo SITL
setup. See [voice control](documentation/voice_control.md) for microphone
options and [setup](documentation/setup.md) for the MAVLink route.

`circle` and `circle radius 5` point the drone toward the center throughout
the circle; `fixed yaw circle radius 5` holds its starting heading. `up`,
`down`, `forward`, and `backward` default to 0.5 m. For example, `up five
meters` and `forward 2 meters` select explicit distances. Forward and backward
use the nose heading measured at the start of each move and hold that heading.
Down is rejected if its requested distance would leave less than 0.25 m above
the takeoff plane, based on current position telemetry; use `land` for the
final descent. These movements have no obstacle avoidance and are currently
limited to verified Gazebo x500 SITL.

## Keyboard SITL failsafe

`voicedrone-control --sitl` configures and reads back PX4's offboard-loss
(`COM_OBL_RC_ACT=4`) and data-link-loss (`NAV_DLL_ACT=3`) Land actions before
arming. If the controller loses its connection, it attempts a landing command,
records when landing cannot be confirmed, and exits. PX4 must perform the
landing independently when the connection is gone.

The live connection-loss check on PX4 v1.17.0/Gazebo x500 succeeded when the
controller's MAVSDK server was stopped while PX4's MAVLink module kept running:
PX4 entered Land mode, descended, and disarmed. Stopping PX4's MAVLink module
itself is a different test; in this environment that left the vehicle hovering
in Land mode until PX4's flight mode manager was restarted. Keep the PX4
MAVLink module running when testing loss of the controller connection.
