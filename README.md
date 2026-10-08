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
- [ ] Takeoff, circle, and runner-controlled landing flight-tested together

See [documentation/setup.md](documentation/setup.md) for the verified toolchain
and [documentation/architecture.md](documentation/architecture.md) for the
coordinate and component design.

Python source is organized under `src/`: Milestone 1 flight code lives in
`src/flight`, while `src/voice`, `src/cv`, and `src/rl` are empty package
placeholders for later milestones. Tests remain under `tests/`.
