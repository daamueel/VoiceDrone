# Development setup

VoiceDrone uses two separate environments:

- Windows runs the project code, tests, MAVSDK client, logging, and analysis.
- WSL2 Ubuntu runs PX4 SITL and Gazebo Harmonic.

Do not install PX4's Linux build dependencies into the Windows `voicedrone`
environment.

## Verified Windows environment

The existing Conda environment is located at
`D:\Anaconda3\envs\voicedrone` and currently contains:

- Conda 26.5.3
- 64-bit CPython 3.11.15
- MAVSDK 3.17.2, including MAVSDK Server v3.17.2
- grpcio 1.83.0
- protobuf 7.35.1
- pymavlink 2.4.49
- pytest 9.1.1

From an Anaconda-enabled shell:

```powershell
conda activate voicedrone
python -m pip install -r documentation\requirements.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
python -m pytest
```

From an ordinary PowerShell, where `conda` may not be on `PATH`:

```powershell
D:\Anaconda3\Scripts\conda.exe run -n voicedrone python -m pip install -r documentation\requirements.txt
D:\Anaconda3\envs\voicedrone\python.exe -m pip install --no-deps --no-build-isolation -e .
D:\Anaconda3\Scripts\conda.exe run -n voicedrone python -m pytest
```

The editable install registers the packages under `src/` without copying the
source. It also provides `voicedrone-sitl` and `voicedrone-analyze` while the
Conda environment is active. Re-run the editable install only if packaging
metadata changes; ordinary source edits are picked up immediately.

An unactivated shell may resolve `python` to MSYS2 Python 3.12, so always
activate the environment or use `conda run` explicitly.

## Verified WSL/PX4 environment

- Distribution: Ubuntu 24.04.4 LTS under WSL2
- PX4: v1.17.0 at `~/PX4-Autopilot`
- PX4 commit: `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`
- Gazebo: Harmonic / Gazebo Sim 8.15.0
- PX4 Gazebo models submodule:
  `b6127f4ec20de867e215fb5f78ae88b80f371909`

The checkout can be reproduced with:

```bash
git clone --branch v1.17.0 --recurse-submodules \
  https://github.com/PX4/PX4-Autopilot.git ~/PX4-Autopilot
cd ~/PX4-Autopilot
bash Tools/setup/ubuntu.sh --no-nuttx
```

Use the distribution explicitly from Windows because another WSL distribution
is configured as the default:

```powershell
wsl.exe -d Ubuntu-24.04
```

## Verified PX4/Gazebo launch

From Ubuntu 24.04:

```bash
cd ~/PX4-Autopilot
make px4_sitl gz_x500
```

The first build is substantial. A successful launch reaches the `pxh>` prompt,
prints `Startup script returned successfully`, reports Gazebo world `default`
as ready, and connects `gz_bridge` to model `x500_0`. The model can be checked
from a second Ubuntu shell with:

```bash
gz model --list
```

The verified result contains `ground_plane` and `x500_0`. Warnings about the
model's `gz_frame_id` elements are non-fatal with the verified Gazebo version.

For a controlled shutdown:

1. Enter `shutdown` at the PX4 `pxh>` prompt and wait for `Exiting NOW.`
2. Press `Ctrl+C` once in the original launch terminal to stop the remaining
   Gazebo server and GUI processes owned by `make`.

Afterward, the following command should produce no simulator processes:

```bash
pgrep -a -f 'build/px4_sitl_default/bin/px4|gz sim --verbose=1|gz sim -g'
```

## Verified Windows-to-WSL telemetry

This machine uses WSL2's default NAT networking. There is no `.wslconfig`, and
no Windows firewall or port-proxy change was required. PX4 initially sends its
onboard MAVLink stream only to WSL localhost, which a Windows MAVSDK process
cannot receive. Retarget that stream to the Windows-side WSL gateway after PX4
has reached the `pxh>` prompt.

First, find the current gateway in a separate Ubuntu 24.04 shell:

```bash
ip route show default
```

The verified run reported WSL address `172.26.184.85` and gateway
`172.26.176.1`. These NAT addresses can change after WSL restarts, so use the
gateway printed on the current system rather than copying the verified value.

At the PX4 `pxh>` prompt, replace `<windows-wsl-gateway>` with that gateway:

```text
mavlink stop -u 14580
mavlink start -x -f -u 14580 -r 4000000 -m onboard -o 14540 -t <windows-wsl-gateway>
mavlink status
```

This is a runtime-only change; it does not modify PX4 parameters or
`.wslconfig` and must be repeated after each fresh SITL launch. The relevant
ports and addresses are:

- PX4/WSL source and receive port: UDP `14580`
- MAVSDK/Windows receive port: UDP `14540`
- MAVSDK connection URL: `udpin://0.0.0.0:14540`

The Python connection boundary is:

```python
from mavsdk import System

drone = System()
await drone.connect(system_address="udpin://0.0.0.0:14540")
```

The verified Windows process used
`D:\Anaconda3\envs\voicedrone\python.exe` and MAVSDK Server v3.17.2. It
discovered PX4 system ID 1 at `172.26.184.85:14580` and received live local
NED position and velocity, Euler attitude, flight mode, armed state, and health
telemetry. One observed stationary sample was:

```text
POSITION_NED_M north=0.037 east=0.024 down=0.001
VELOCITY_NED_M_S north=-0.007 east=0.011 down=-0.001
ATTITUDE_DEG roll=-0.012 pitch=-0.012 yaw=96.000
FLIGHT_MODE=HOLD ARMED=False
HEALTH global=True local=True home=True
```

PX4's subsequent `mavlink status` reported six received messages from MAVSDK
system ID 245/component ID 190, zero lost messages, and a 0--4 ms ping range.
This confirms bidirectional communication. Closing the short-lived client
causes PX4 to report that its ground-station connection was lost; that is
expected for this probe.

## Verified takeoff run

Keep PX4/Gazebo running and apply the Windows-side WSL gateway routing described
above. In a Windows PowerShell at the repository root, activate the verified
environment and run the independent takeoff test:

```powershell
conda activate voicedrone
python -m pytest -q
python -m flight.run_sitl takeoff --target-altitude 5.0
```

The behavior generates a one metre-per-second vertical position ramp from its
measured starting NED position. North, east, and yaw remain fixed. The target
is `start_down - target_altitude` because upward motion is negative NED down.
The pure behavior's completion band remains 0.25 m, but the runner no longer
accepts one qualifying sample. It waits until nominal trajectory duration has
elapsed, altitude is within 0.25 m, absolute vertical speed is at most 0.2 m/s,
and those conditions persist for one continuous second. PX4 local-position
health and an actual finite NED sample are required before flight. After this
settled completion, the runner—not `Takeoff`—uses the separate MAVSDK land
action and waits for disarm.

Every run writes a UTC-named CSV under `logs/`. Analyze the path printed by the
runner to calculate takeoff metrics and create the matching top-down plot:

```powershell
python -m flight.analyze_sitl logs\sitl_<UTC-timestamp>_takeoff.csv
```

The strengthened completion rule was verified with:

```text
logs\sitl_20261008T075314Z_takeoff.csv
logs\sitl_20261008T075314Z_takeoff_ne.png
```

The verified CSV contains commanded and measured local-NED position and
velocity, yaw, yaw rate, UTC timestamp, trajectory time, execution phase,
flight mode, and armed state. Its observed results were:

```text
unit tests:                  78 passed
commanded altitude gain:    5.000 m
measured altitude gain:     4.874 m
final vertical error:       0.127 m
final vertical speed:       0.065 m/s
maximum lateral drift:      0.036 m
peak vertical speed:        2.191 m/s
absolute yaw change:        0.000 rad
takeoff samples:            184
final armed state:          false
```

The run completed in offboard mode, changed to land mode for the runner action,
and disarmed near its starting altitude. The generated artifacts are ignored by
Git. Preserve a required artifact outside `logs/` before repository cleanup.

After the runner reports `Landing complete: vehicle disarmed`, shut PX4 and
Gazebo down using the controlled procedure in **Verified PX4/Gazebo launch**.
The independent circle procedure is documented below; the combined sequence
remains unverified until Step 10.

## Verified independent circle runs

Keep PX4/Gazebo running and apply the Windows-side WSL gateway routing described
above. From a Windows PowerShell at the repository root:

```powershell
conda activate voicedrone
python -m pytest -q
python -m flight.run_sitl circle_side --radius 10.0 --speed 1.0 --angular-velocity 0.1
python -m flight.run_sitl circle_centripetal --radius 5.0 --speed 1.0 --angular-velocity 0.2
python -m flight.run_sitl circle --radius 5.0 --speed 1.0 --angular-velocity 0.2
```

Run one command per flight. For each independent test, the runner uses PX4's
action takeoff to establish a settled airborne state at approximately 5 m.
That setup is not part of a circle behavior. The runner exits offboard mode,
invokes its separate landing action, waits for disarm, and closes MAVSDK.

`circle_side` holds the measured airborne position while aligning the nose on
its offset centre, then starts circular-motion time. `circle_centripetal` and
`circle` both treat the measured airborne position as their centre, perform a
separately timed radial entry behind the initial heading, settle on the
circumference, and then start circular-motion time. `circle_centripetal` faces
the centre throughout the circular segment; `circle` holds starting yaw and
looks in one fixed direction. Both hold yaw during radial entry, so the nose
points at the centre at the beginning of the circle. The entry is shown in the
generated plot.

All variants can be used with radius alone. They default to 1 m/s, derive
positive angular velocity as `speed / radius`, and derive one revolution of
duration as `2*pi / abs(angular_velocity)`. Negative angular velocity selects
counterclockwise motion. Explicit speed and angular velocity may be combined
only when `speed == abs(angular_velocity) * radius`.

The circular-motion duration excludes entry and endpoint closure. At the end
of the commanded revolution, the runner holds the endpoint until the measured
position is within 0.15 m, horizontal speed is at most 0.2 m/s, and both
conditions persist for 0.5 s. The default closure timeout is 15 s and can be
adjusted with `--closure-timeout`. On success, the runner then lands separately;
on timeout, its safety cleanup also commands landing. PX4 controller lag may
leave the measured revolution short of the start point
at the instant the commanded revolution ends; this is why closure is logged
and plotted separately.

For `circle_centripetal` and `circle`, successful closure is followed by a
radial return to the centered circle's original airborne start. The return
retraces entry at `--entry-speed`, is not included in circular-motion duration,
and must settle within 0.15 m at no more than 0.2 m/s for 0.5 s. Only then does
the runner invoke its separate landing action. `circle_side` already begins and
ends at its airborne starting point, so it does not need this radial return.

Analyze the path printed by the runner:

```powershell
python -m flight.analyze_sitl logs\sitl_<UTC-timestamp>_circle_side.csv
python -m flight.analyze_sitl logs\sitl_<UTC-timestamp>_circle_centripetal.csv
python -m flight.analyze_sitl logs\sitl_<UTC-timestamp>_circle.csv
```

The verified centered-circle return artifacts are:

```text
logs\sitl_20261008T075652Z_circle_centripetal.csv
logs\sitl_20261008T075652Z_circle_centripetal_ne.png
logs\sitl_20261008T075140Z_circle.csv
logs\sitl_20261008T075140Z_circle_ne.png
```

The renamed standalone command and endpoint hold were verified with
`sitl_20261008T081428Z_circle_side.csv` and its matching `_ne.png` plot at
radius 5 m and angular velocity 0.2 rad/s. The original Milestone 1 radius
10 m, angular velocity 0.1 rad/s artifact remains
`sitl_20261006T193151Z_circle_side.csv`.
The old `sitl_20261006T193727Z_circle_centered.csv` is historical: its commanded
path completed one revolution, but its measured endpoint remained 1.06 m
from its measured starting point because the runner landed without endpoint
closure. That error was controller lag, not a missing segment in the trajectory
equation; it is now explicitly accounted for by the runner.

The observed circle results were:

```text
unit tests:                              78 passed
circle_side commanded/measured radius:       5.000 / 5.002 m
circle_side radial RMSE:                      0.035 m
circle_side commanded/measured omega:         0.2000 / 0.2001 rad/s
circle_side final endpoint error:             0.105 m
circle_side touchdown ground offset:          0.086 m
circle_centripetal commanded/measured radius: 5.000 / 4.990 m
circle_centripetal radial RMSE:               0.022 m
circle_centripetal commanded/measured omega:  0.2000 / 0.1993 rad/s
circle_centripetal mean centre-heading error: 0.1225 rad
circle_centripetal measured endpoint gap:     1.043 m
circle_centripetal endpoint hold:             2.078 s
circle_centripetal final endpoint error:      0.110 m
circle_centripetal return-to-center error:    0.145 m
circle_centripetal touchdown center offset:   0.074 m
circle_centripetal touchdown ground offset:   0.069 m
circle commanded/measured radius:             5.000 / 5.007 m
circle radial RMSE:                            0.022 m
circle commanded/measured omega:               0.2000 / 0.1995 rad/s
circle maximum yaw change:                     0.008 rad
circle maximum yaw-hold error:                 0.0106 rad
circle measured endpoint gap:                  1.067 m
circle endpoint hold:                          2.203 s
circle final endpoint error:                   0.115 m
circle return-to-center error:                 0.102 m
circle touchdown center offset:                0.052 m
circle touchdown ground offset:                0.069 m
both final armed state:                        false
```

The new plots distinguish commanded circle, measured circle, radial entry,
endpoint hold, return to start, landing, and touchdown. The measured path ends
close to its circumference start after closure and then returns to the center;
a perfect geometric trace is not expected from the physical simulation.
Unit tests cover both directions, arbitrary phase, tangential speed, centre
selection, radial entry, both yaw conventions, continuity, completion,
defaults, and invalid or conflicting inputs. No NED-to-body-FRD velocity
conversion is used by this position-setpoint implementation.

The generated artifacts remain ignored by Git. After the runner reports that
landing completed and the vehicle disarmed, use the controlled PX4/Gazebo
shutdown procedure above. The combined `Takeoff` behavior to a circle behavior
remains unverified until Step 10; that step must select an explicit variant.
