# Roadmap

## Milestone 1: deterministic SITL flight

- Verify the Windows/WSL2, PX4, Gazebo, and MAVSDK toolchain.
- Implement independently testable takeoff and circle trajectories.
- Isolate PX4/MAVSDK integration behind one adapter.
- Verify takeoff, airborne circle, and runner-controlled landing in SITL.
- Record and analyze commanded and measured telemetry.

## Later milestones

1. Map voice phrases to established flight behaviors.
2. Add real Pixhawk support after simulation safety criteria are defined.
3. Add computer vision, learning-based control, ROS 2, and broader autonomy
   only as separately scoped work.
