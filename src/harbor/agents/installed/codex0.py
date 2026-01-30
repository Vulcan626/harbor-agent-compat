# -*- coding: utf-8 -*-
"""
harbor/agents/installed/codex0.py

Codex0: Codex CLI agent with official base URL override support.

Official method:
- Set OPENAI_BASE_URL to override the built-in OpenAI provider endpoint.

We expose a Harbor-level `base_url` input and map it to OPENAI_BASE_URL.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from harbor.agents.installed.base import ExecInput
from harbor.agents.installed.codex import Codex
from harbor.models.trial.paths import EnvironmentPaths


# ------ Configs ------
ENV_CODEX_BASE_URL = "CODEX_BASE_URL"  # user-friendly alias for Harbor usage


# ------ Functions ------
def _normalize_openai_base_url(url: str) -> str:
    """
    Codex docs recommend using the v1 endpoint in OPENAI_BASE_URL.
    """
    url = url.strip().rstrip("/")
    if not url.endswith("/v1"):
        url = url + "/v1"
    return url


# ------ Agent ------
class Codex0(Codex):
    """
    Codex0 supports custom OpenAI-compatible base URL via OPENAI_BASE_URL.

    Priority:
    1) agent kwarg: base_url
    2) env: CODEX_BASE_URL
    3) env: OPENAI_BASE_URL (if user already set it)
    """

    def __init__(
        self,
        reasoning_effort: str | None = "high",
        base_url: str | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(reasoning_effort=reasoning_effort, *args, **kwargs)
        self._base_url = (
            base_url
            or os.environ.get(ENV_CODEX_BASE_URL)
            or os.environ.get("OPENAI_BASE_URL")
        )

    @staticmethod
    def name() -> str:
        return "codex0"

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        escaped_instruction = shlex.quote(instruction)

        if not self.model_name:
            raise ValueError("Model name is required")

        model = self.model_name.split("/")[-1]

        env = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
            "CODEX_HOME": (EnvironmentPaths.agent_dir).as_posix(),
        }

        # Official base URL override: OPENAI_BASE_URL
        if self._base_url:
            env["OPENAI_BASE_URL"] = _normalize_openai_base_url(self._base_url)

        reasoning_effort = self._reasoning_effort
        reasoning_flag = (
            f"-c model_reasoning_effort={reasoning_effort} " if reasoning_effort else ""
        )

        # Optional: export diagnostics to /logs/agent for easier debugging
        diag_prefix = (
            "mkdir -p /logs/agent/codex0; "
            "echo '[INFO] env snapshot' > /logs/agent/codex0/env.txt; "
            "env | grep -E 'OPENAI_API_KEY|OPENAI_BASE_URL|CODEX_BASE_URL|CODEX_HOME' "
            ">> /logs/agent/codex0/env.txt 2>/dev/null || true; "
        )

        return [
            ExecInput(
                command=(
                    diag_prefix
                    + """
mkdir -p /tmp/codex-secrets
cat >/tmp/codex-secrets/auth.json <<EOF
{
  "OPENAI_API_KEY": "${OPENAI_API_KEY}"
}
EOF
ln -sf /tmp/codex-secrets/auth.json "$CODEX_HOME/auth.json"
"""
                ),
                env=env,
            ),
            ExecInput(
                command=(
                    "trap 'rm -rf /tmp/codex-secrets \"$CODEX_HOME/auth.json\"' EXIT TERM INT; "
                    "codex exec "
                    "--dangerously-bypass-approvals-and-sandbox "
                    "--skip-git-repo-check "
                    f"--model {model} "
                    "--json "
                    "--enable unified_exec "
                    f"{reasoning_flag}"
                    "-- "  # end of flags
                    f"{escaped_instruction} "
                    f"2>&1 </dev/null | tee {EnvironmentPaths.agent_dir / self._OUTPUT_FILENAME}"
                ),
                env=env,
            ),
        ]
