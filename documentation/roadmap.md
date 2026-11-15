# Roadmap

## Milestone 1: deterministic SITL flight

- Verify the Windows/WSL2, PX4, Gazebo, and MAVSDK toolchain.
- Implement independently testable takeoff and circle trajectories.
- Isolate PX4/MAVSDK integration behind one adapter.
- Verify takeoff, airborne circle, and runner-controlled landing in SITL.
- Record and analyze commanded and measured telemetry.

## Shared keyboard and speech control

- [x] Add structured commands and one deterministic parser for keyboard text
  and speech transcripts.
- [x] Keep one PX4 SITL flight session open for takeoff, circle, and land.
- [x] Verify keyboard confirmation, microphone transcription, and a spoken
  takeoff, circle, and land sequence in SITL.
- [x] Add continuous listening with Silero speech detection and phrase-level
  transcription.
- [x] Verify the continuous listening loop in a live microphone/SITL sequence.

## Later milestones

1. Define simulation safety criteria before any real Pixhawk support.
2. Scope computer vision, learning-based control, ROS 2, and broader autonomy
   separately.
