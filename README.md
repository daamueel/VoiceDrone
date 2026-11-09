# VoiceDrone

VoiceDrone is an incremental autonomous-flight project built around PX4 SITL and
MAVSDK. Milestone 1 is deliberately limited to deterministic takeoff and circle
behaviors; voice recognition, natural-language parsing, computer vision, PPO,
ROS 2, and real hardware are later work.

## Milestone 1 status

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

See [documentation/setup.md](documentation/setup.md) for the verified toolchain
and [documentation/architecture.md](documentation/architecture.md) for the
coordinate and component design.

Python source is organized under `src/`: Milestone 1 flight code lives in
`src/flight`, while `src/voice`, `src/cv`, and `src/rl` are empty package
placeholders for later milestones. Tests remain under `tests/`.

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
