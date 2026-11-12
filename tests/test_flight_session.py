"""Session ordering and cleanup checks without a PX4 connection."""

import asyncio
from dataclasses import replace
import os
import subprocess
from types import SimpleNamespace

import pytest

from control.commands import CircleCommand, LandCommand, StatusCommand, TakeoffCommand
from control.session import CommandRejected, FlightSession
from flight.trajectory import TrajectoryPoint, VehicleState
from flight.px4_offboard_adapter import PX4OffboardAdapter, _SessionSystem


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.measured = VehicleState(0.0, 0.0, 0.0)

    async def connect(self) -> None:
        self.calls.append("connect")

    async def wait_until_ready(self) -> None:
        self.calls.append("ready")

    async def verify_sitl(self) -> None:
        self.calls.append("verify_sitl")

    async def configure_link_loss_failsafe(self) -> None:
        self.calls.append("configure_failsafe")

    def state(self) -> VehicleState:
        return self.measured

    async def send(self, _: TrajectoryPoint) -> None:
        self.calls.append("send")

    async def arm(self) -> None:
        self.calls.append("arm")
        self.measured = replace(self.measured, armed=True)

    async def start_offboard(self) -> None:
        self.calls.append("start_offboard")

    async def stop_offboard(self) -> None:
        self.calls.append("stop_offboard")

    async def land(self) -> None:
        self.calls.append("land")
        self.measured = replace(self.measured, armed=False)

    async def wait_until_disarmed(self, timeout_s: float) -> None:
        self.calls.append("disarmed")

    async def close(self) -> None:
        self.calls.append("close")


def test_session_rejects_invalid_order_and_keeps_one_connection(tmp_path, monkeypatch) -> None:
    async def fake_takeoff(*args):
        return TrajectoryPoint(0.0, 0.0, -0.5)

    async def fake_circle(*args):
        return TrajectoryPoint(0.0, 0.0, -0.5)

    monkeypatch.setattr("control.session.execute_takeoff", fake_takeoff)
    monkeypatch.setattr("control.session.execute_centered_circle_behavior", fake_circle)
    adapter = FakeAdapter()

    async def scenario() -> None:
        async with FlightSession(adapter=adapter, directory=tmp_path) as session:
            with pytest.raises(CommandRejected, match="while landed"):
                await session.execute(CircleCommand())
            await session.execute(TakeoffCommand())
            with pytest.raises(CommandRejected, match="already airborne"):
                await session.execute(TakeoffCommand())
            await session.execute(CircleCommand())
            assert "airborne" in (await session.execute(StatusCommand())).message
            await session.execute(LandCommand())
            with pytest.raises(CommandRejected, match="already landed"):
                await session.execute(LandCommand())
            assert "landed" in (await session.execute(StatusCommand())).message

    asyncio.run(scenario())
    assert adapter.calls.count("connect") == 1
    assert adapter.calls.index("verify_sitl") < adapter.calls.index("configure_failsafe")
    assert adapter.calls.index("configure_failsafe") < adapter.calls.index("arm")
    assert adapter.calls.count("land") == 1
    assert adapter.calls[-1] == "close"
    assert len(list(tmp_path.glob("control_*_keyboard.jsonl"))) == 1
    assert len(list(tmp_path.glob("sitl_*_control_*.csv"))) == 1


def test_exit_while_airborne_lands_before_close(tmp_path, monkeypatch) -> None:
    async def fake_takeoff(*args):
        return TrajectoryPoint(0.0, 0.0, -0.5)

    monkeypatch.setattr("control.session.execute_takeoff", fake_takeoff)
    adapter = FakeAdapter()

    async def scenario() -> None:
        async with FlightSession(adapter=adapter, directory=tmp_path) as session:
            await session.execute(TakeoffCommand())

    asyncio.run(scenario())
    assert adapter.calls.index("land") < adapter.calls.index("close")
    assert adapter.calls.count("disarmed") == 1


def test_cancelled_flight_attempts_landing_before_close(tmp_path, monkeypatch) -> None:
    async def cancelled_takeoff(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr("control.session.execute_takeoff", cancelled_takeoff)
    adapter = FakeAdapter()

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            async with FlightSession(adapter=adapter, directory=tmp_path) as session:
                await session.execute(TakeoffCommand())

    asyncio.run(scenario())
    assert adapter.calls.index("land") < adapter.calls.index("close")


def test_disconnect_interrupts_idle_session_and_attempts_landing(
    tmp_path, monkeypatch
) -> None:
    async def fake_takeoff(*args):
        return TrajectoryPoint(0.0, 0.0, -0.5)

    monkeypatch.setattr("control.session.execute_takeoff", fake_takeoff)

    class DisconnectingAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.disconnect = asyncio.Event()

        async def wait_until_disconnected(self) -> None:
            await self.disconnect.wait()

    adapter = DisconnectingAdapter()

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            async with FlightSession(adapter=adapter, directory=tmp_path) as session:
                await session.execute(TakeoffCommand())
                adapter.disconnect.set()
                await asyncio.sleep(10)

    asyncio.run(scenario())
    assert adapter.calls.index("land") < adapter.calls.index("close")


def test_disconnected_session_records_unconfirmed_landing(tmp_path, monkeypatch) -> None:
    async def fake_takeoff(*args):
        return TrajectoryPoint(0.0, 0.0, -0.5)

    monkeypatch.setattr("control.session.execute_takeoff", fake_takeoff)

    class LostLinkAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.disconnect = asyncio.Event()

        async def wait_until_disconnected(self) -> None:
            await self.disconnect.wait()

        async def land(self) -> None:
            self.calls.append("land")
            raise TimeoutError("link unavailable")

    adapter = LostLinkAdapter()

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError, match="connection lost"):
            async with FlightSession(adapter=adapter, directory=tmp_path) as session:
                await session.execute(TakeoffCommand())
                adapter.disconnect.set()
                await asyncio.sleep(10)

    asyncio.run(scenario())
    assert adapter.calls.index("land") < adapter.calls.index("close")
    record = next(tmp_path.glob("control_*_keyboard.jsonl")).read_text()
    assert '"event": "landing_unconfirmed"' in record


def test_mavsdk_server_survives_windows_console_interrupt(monkeypatch) -> None:
    if os.name != "nt":
        pytest.skip("Windows console process groups only")
    launches = []

    def fake_popen(arguments, **options):
        launches.append((arguments, options))
        return object()

    monkeypatch.setattr("flight.px4_offboard_adapter.subprocess.Popen", fake_popen)
    _SessionSystem._start_mavsdk_server(
        "udpin://0.0.0.0:14540", 50051, 245, 190
    )

    arguments, options = launches[0]
    assert arguments[-1] == "udpin://0.0.0.0:14540"
    assert options["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP


def test_adapter_sets_and_verifies_onboard_land_failsafes() -> None:
    values = {"COM_OBL_RC_ACT": 0, "NAV_DLL_ACT": 2}
    changes = []

    async def get_param(name):
        return values[name]

    async def set_param(name, value):
        changes.append((name, value))
        values[name] = value

    adapter = PX4OffboardAdapter()
    adapter._drone = SimpleNamespace(param=SimpleNamespace(
        get_param_int=get_param, set_param_int=set_param,
    ))
    asyncio.run(adapter.configure_link_loss_failsafe())

    assert changes == [("COM_OBL_RC_ACT", 4), ("NAV_DLL_ACT", 3)]


def test_adapter_rejects_unverified_failsafe_setting() -> None:
    async def get_param(_name):
        return 0

    async def set_param(_name, _value):
        pass

    adapter = PX4OffboardAdapter()
    adapter._drone = SimpleNamespace(param=SimpleNamespace(
        get_param_int=get_param, set_param_int=set_param,
    ))
    with pytest.raises(RuntimeError, match="COM_OBL_RC_ACT"):
        asyncio.run(adapter.configure_link_loss_failsafe())


def test_adapter_accepts_only_gazebo_x500_sitl() -> None:
    values = {"SYS_AUTOSTART": 4001, "SIM_GZ_EN": 1}

    async def get_param(name):
        return values[name]

    adapter = PX4OffboardAdapter()
    adapter._drone = SimpleNamespace(param=SimpleNamespace(get_param_int=get_param))
    asyncio.run(adapter.verify_sitl())

    values["SIM_GZ_EN"] = 0
    with pytest.raises(RuntimeError, match="SIM_GZ_EN"):
        asyncio.run(adapter.verify_sitl())

    values.update(SIM_GZ_EN=1, SYS_AUTOSTART=4019)
    with pytest.raises(RuntimeError, match="SYS_AUTOSTART"):
        asyncio.run(adapter.verify_sitl())


def test_session_rejects_non_sitl_before_failsafe_changes(tmp_path) -> None:
    class WrongVehicle(FakeAdapter):
        async def verify_sitl(self) -> None:
            self.calls.append("verify_sitl")
            raise RuntimeError("not Gazebo SITL")

    adapter = WrongVehicle()

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="not Gazebo SITL"):
            async with FlightSession(adapter=adapter, directory=tmp_path):
                pass

    asyncio.run(scenario())
    assert "configure_failsafe" not in adapter.calls
    assert "arm" not in adapter.calls
    assert adapter.calls[-1] == "close"


def test_adapter_closes_after_telemetry_stream_fails() -> None:
    async def failed_stream():
        raise ConnectionError("server stopped")

    stopped = []
    adapter = PX4OffboardAdapter()
    adapter._drone = SimpleNamespace(_stop_mavsdk_server=lambda: stopped.append(True))

    async def scenario() -> None:
        task = asyncio.create_task(failed_stream())
        await asyncio.sleep(0)
        adapter._tasks = [task]
        await adapter.close()

    asyncio.run(scenario())
    assert stopped == [True]
