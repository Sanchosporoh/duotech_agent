"""Read a GAP working copy through PetEx OpenServer without saving it."""

from __future__ import annotations

import json
from pathlib import Path

import win32com.client


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "runtime" / "petex_case" / "IM_2022_06" / "BEL_PROD.gap"


def main() -> None:
    server = win32com.client.Dispatch("PX32.OpenServer.1")
    events: list[dict[str, object]] = []
    events.append(
        {
            "methods": [name for name in dir(server) if not name.startswith("_")],
            "signatures": {
                name: repr(entry)
                for name, entry in server._olerepr_.mapFuncs.items()
                if name in {"GetValue", "GetValue2", "DoCmd2", "GetLastError"}
            },
        }
    )

    def cmd(command: str) -> None:
        server.DoCommand(command)
        events.append({"command": command, "error": str(server.GetLastError("GAP"))})

    def get(variable: str) -> object:
        try:
            value = server.GetValue(variable)
            events.append({"variable": variable, "value": value})
            return value
        except Exception as exc:  # OpenServer reports useful failures as COM errors.
            events.append({"variable": variable, "error": repr(exc)})
            return None

    cmd(f'GAP.OPENFILE("{MODEL}")')
    for variable in (
        "GAP.MOD.WELL[{W_BEL_13}].SolverResults[0].Qoil",
        "GAP.MOD.WELL[{W_BEL_13}].SolverResults[0].Qliq",
        "GAP.MOD.WELL[{W_BEL_13}].SolverResults[0].TotMassRate",
    ):
        get(variable)

    print(json.dumps(events, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
