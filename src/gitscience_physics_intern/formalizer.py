"""Subprocess-isolated PhysicsIntern formalization agent."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class PhysicsInternFormalizer:
    name = "physics_intern"
    version = "0.1.0"
    environment_packages = ("physics-intern",)

    def source_paths(self) -> list[Path]:
        return [Path(__file__), Path(__file__).with_name("formalizer_bridge.py")]

    def run(
        self, dossier: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        timeout = int(options.get("timeout", 300))
        if timeout < 1 or timeout > 3600:
            raise ValueError("timeout must be between 1 and 3600 seconds")
        model = options.get("model")
        with tempfile.TemporaryDirectory(prefix="gitscience-formalize-") as directory:
            root = Path(directory)
            input_path = root / "dossier.json"
            output_path = root / "proposal.json"
            input_path.write_text(json.dumps(dossier, sort_keys=True))
            command = [
                sys.executable,
                "-m",
                "gitscience_physics_intern.formalizer_bridge",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
            if model:
                command.extend(["--model", str(model)])
            process = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if process.returncode != 0:
                detail = (process.stderr or process.stdout).strip()[-4000:]
                raise RuntimeError(detail or "PhysicsIntern bridge exited unsuccessfully")
            if not output_path.exists() or output_path.stat().st_size > 2_000_000:
                raise RuntimeError("PhysicsIntern returned a missing or oversized proposal")
            result = json.loads(output_path.read_text())
            if not isinstance(result, dict):
                raise TypeError("PhysicsIntern proposal must be a JSON object")
            return result


plugin = PhysicsInternFormalizer()
