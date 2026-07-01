"""Orquestração do gera-script: monta config + escreve os artefatos no disco.

Mantém a função de CLI fina (sem ramificação demais) e isola a escrita de
arquivos, que é o único efeito colateral. Determinístico no conteúdo.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .emit import CONFIG_NAME, PS1_NAME, SH_NAME, emit_config_json, emit_ps1, emit_sh
from .schema import build_config

if TYPE_CHECKING:
    from plugadvpl.compile_servers import Server


class ArtifactExistsError(Exception):
    """Algum artefato já existe e ``force`` é False. Carrega os nomes em ``names``."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(", ".join(names))


def generate(
    out: str | Path,
    *,
    server: Server | None = None,
    secret: str = "env",
    shell: str = "both",
    force: bool = False,
    tq: bool = False,
) -> tuple[list[Path], dict[str, str]]:
    """Escreve os artefatos em ``out`` e retorna (paths escritos, config usado).

    ``tq=True`` inclui a 3ª fase (Troca Quente) no script e as chaves TQ no config.
    Levanta ``ArtifactExistsError`` se algum alvo já existe e ``force`` é False.
    """
    cfg = build_config(server=server, secret=secret, tq=tq)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    alvos: list[tuple[Path, str, bool]] = []  # (path, conteudo, executavel)
    if shell in ("ps1", "both"):
        alvos.append((out_dir / PS1_NAME, emit_ps1(with_tq=tq), False))
    if shell in ("sh", "both"):
        alvos.append((out_dir / SH_NAME, emit_sh(with_tq=tq), True))
    alvos.append((out_dir / CONFIG_NAME, emit_config_json(cfg), False))

    existentes = [p.name for p, _c, _x in alvos if p.exists()]
    if existentes and not force:
        raise ArtifactExistsError(existentes)

    escritos: list[Path] = []
    for path, conteudo, executavel in alvos:
        path.write_text(conteudo, encoding="utf-8", newline="")
        if executavel:
            path.chmod(0o755)
        escritos.append(path)
    return escritos, cfg
