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
python -m pip install -r Documentation\requirements.txt
python -m pip check
python -m pytest
```

From an ordinary PowerShell, where `conda` may not be on `PATH`:

```powershell
D:\Anaconda3\Scripts\conda.exe run -n voicedrone python -m pip install -r Documentation\requirements.txt
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

The PX4/Gazebo build, launch, telemetry, test-runner, analysis, plotting, and
safe-shutdown commands will be documented only after they have been exercised
in their corresponding Milestone 1 verification steps.
