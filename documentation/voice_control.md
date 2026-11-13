# Local speech transcription

Step 6 provides transcription without command parsing or flight execution.
The microphone samples stay in memory and are discarded after each attempt.
The selected model is `small.en`, running on CPU with int8 requested. `base.en`
remains available through `--model base.en`.

From the `voicedrone` Windows environment at the repository root:

```powershell
python -m voice.run_transcription --device 1 --duration 6
```

Press Enter, speak during the six-second capture, and read the transcript and
input level. Type `q` to quit. The Realtek microphone array was device 1 when
tested; check `python -m sounddevice` if Windows changes the device indices.
The tool does not import the command parser, flight session, or MAVSDK.

On 2026-11-09, `base.en` recognized `Take off to 5 meters` and `land, land`, but
heard `Hey cough` for `takeoff` and twice missed `circle` (`So cool radius 5`
and `So Colby`). Vocabulary hints improved `small.en` on the same Realtek input:

| Spoken phrase | `small.en` transcript |
| --- | --- |
| circle radius five | `circle, radius 5` |
| takeoff, repeated | `takeoff, take off` |
| land | `land` |

With the same hints, `base.en` still returned only `radius 5` for `circle radius
five`, so `small.en` is the default. A four-second near-silent microphone
capture returned no transcript (RMS 0.000015, peak 0.000092). Voice activity
detection filters silence; without it, an earlier synthetic silence sample
produced `You`. Transcription can still miss words, so later steps must reject
unknown text and require keyboard confirmation before any flight action.

The downloaded `small.en` model is cached outside the repository at
`C:\Users\daamu\.cache\huggingface\hub\models--Systran--faster-whisper-small.en\snapshots\d1d751a5f8271d482d14ca55d9e2deeebbae577f`.

## Command preview (step 7)

The preview tool sends each transcript to the same deterministic parser used
by keyboard control. It prints the parsed command and effective parameters or
the rejection reason, then states that no flight action was taken. It does not
create a flight session or connect to PX4.

```powershell
python -m voice.run_voice --device 1 --duration 6
python -m voice.run_voice --transcript "circle, radius 5" --transcript "takeoff and land"
```

The second form previews supplied text without opening the microphone. In a
live microphone check on 2026-11-09, `takeoff to 5 meters` became a takeoff
preview at 5.000 m; `take off and land` was rejected. Two spoken circle tries
were heard as `so` and `so cool` and were rejected. A supplied transcript of
`circle, radius 5` correctly previews the centered inward-facing circle at
5.000 m radius, 1.000 m/s speed, and 31.416 s duration. Live recognition of
`circle` is still inconsistent even though one step 6 capture succeeded.

## Keyboard confirmation and SITL gate (step 8)

To enable spoken commands against the same persistent session used by keyboard
control, launch PX4 v1.17.0 with Gazebo x500 and route its MAVLink stream to
Windows as described in `setup.md`, then run:

```powershell
python -m voice.run_voice --sitl --device 1 --duration 6
```

The program shows the transcript, parsed command, effective parameters, and
complete action. Type `Y` (or `y`) at the keyboard after that preview to execute
it; `N` (or `n`) cancels it. Any other response also cancels it. On the verified
Windows console, keys entered before the confirmation prompt are discarded.
Rejected transcripts never prompt for confirmation. `--transcript`
remains preview-only and cannot be combined with `--sitl`.

Before changing PX4 parameters or arming, the shared session checks
`SYS_AUTOSTART=4001` and `SIM_GZ_EN=1`, the configured Gazebo x500 SITL setup.
The voice CLI has no option for a hardware address. Confirmed commands use the
existing `FlightSession`, including state validation, logs, cancellation,
landing cleanup, and the immediate `L` land key during a maneuver. Records are
named `control_<UTC-timestamp>_voice.jsonl`; raw audio is not saved.

On 2026-11-11, a live disarmed Gazebo x500 connection passed the SITL check.
A simulated `takeoff` transcript was displayed but given no keyboard
confirmation. The voice record logged `accepted: false`, had no requested
flight command, and PX4 remained disarmed. Actual spoken flight execution is
reserved for step 9.

## Spoken takeoff, circle, and land (step 9)

On 2026-11-11 (Pacific time), PX4 v1.17.0/Gazebo x500 completed a real
microphone sequence with separate spoken commands. The user typed `YES` in the
Codex chat after each preview; that confirmation was relayed to the waiting
CLI. The first capture was silent and rejected without a flight action.

| Spoken command | Transcript | Parsed action | Result |
| --- | --- | --- | --- |
| takeoff | `take off` | takeoff to 0.500 m | settled and remained airborne |
| circle radius five | `circle, radius 5` | clockwise `circle_centripetal`, 5.000 m radius | full circle, closure, and return completed |
| land | `land` | land and wait for disarm | touchdown and disarm completed |

The UTC artifacts are
`logs/control_20261112T015647430226Z_voice.jsonl`,
`logs/sitl_20261112T015647Z_control_20261112T015647430226Z.csv`, and the
matching `_ne.png` path plot. The record contains one accepted confirmation
before each requested command and no unexpected flight command. The CSV has
1,256 rows: 195 takeoff, 154 entry, 642 circle, 47 closure, 154 return, and
64 landing samples. Its final sample is disarmed at -0.012 m down position.

CSV analysis reported a 5.002 m measured mean circle radius against 5.000 m
commanded, 0.025 m radial RMSE, 0.992 m/s measured speed against 1.000 m/s
commanded, and 0.005 m mean altitude error during the circle. The return ended
0.138 m from the airborne center; touchdown was 0.026 m from that center.
PX4 separately reported `Disarmed by landing`. The takeoff settled 0.165 m
short of the 0.500 m commanded gain, within the configured settling criteria.
The voice session exited cleanly, prior PX4 failsafe parameter values were
restored, and PX4/Gazebo and MAVSDK Server were shut down.

### Visible Gazebo rerun

On 2026-11-12 (Pacific time), the spoken sequence was repeated with Gazebo's
GUI running. The user confirmed the x500 simulation window was visible before
arming. The separate microphone captures produced `take off`, `circle, radius
5`, and `land`. Each parsed command was previewed, and the user's `YES` in the
Codex chat was relayed to the waiting CLI. All three commands completed; the
circle returned to its airborne start, and landing ended disarmed. PX4 reported
no failsafe.

The record is `logs/control_20261112T225206697538Z_voice.jsonl`; telemetry is
`logs/sitl_20261112T225206Z_control_20261112T225206697538Z.csv` with a matching
`_ne.png` path plot. CSV analysis found a 4.993 m mean radius against 5.000 m
commanded, 0.025 m radial RMSE, 0.963 m/s mean measured speed, and 0.006 m
mean altitude error during the circle. The return ended 0.126 m from the
airborne center, and touchdown was 0.019 m from it. The takeoff settled
0.158 m below the requested 0.500 m gain, within its configured settling
criteria. The voice CLI exited cleanly, the prior PX4 failsafe parameters were
restored, and PX4/Gazebo and MAVSDK Server were shut down.
