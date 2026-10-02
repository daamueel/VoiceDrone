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
python -m pip check
python -m pytest
```

From an ordinary PowerShell, where `conda` may not be on `PATH`:

```powershell
D:\Anaconda3\Scripts\conda.exe run -n voicedrone python -m pip install -r documentation\requirements.txt
D:\Anaconda3\Scripts\conda.exe run -n voicedrone python -m pytest
```

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

The test-runner, analysis, and plotting commands will be documented after they
have been exercised in their corresponding Milestone 1 verification steps.
