"""Visualizacao 3D / Street View de destinos (RF9).

Monta de forma deterministica a URL (e um embed HTML) de Street View a partir
de um destino (cidade/estado/pais) ou de coordenadas (lat/long). Nenhuma
chamada externa e feita por padrao: a URL e construida a partir de
``Settings.streetview_base_url`` (configuravel) e da eventual chave de API em
``Settings.streetview_api_key`` (nunca hardcoded). Isso permite testar o
comportamento sem depender de um servico real.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlencode

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class Destino:
    """Dados minimos de um destino para montar a visualizacao (RF9)."""

    cidade: str
    estado: Optional[str] = None
    pais: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    id_destino: Optional[int] = None


def _descricao_local(destino: Destino) -> str:
    """Monta a descricao textual do local (cidade, estado, pais)."""
    partes = [p for p in (destino.cidade, destino.estado, destino.pais) if p]
    return ", ".join(partes)


def montar_url_streetview(
    destino: Destino, settings: Optional[Settings] = None
) -> str:
    """Retorna a URL de Street View para o destino, de forma deterministica.

    Prioriza coordenadas (lat/long) quando disponiveis; caso contrario usa a
    descricao textual (cidade/estado/pais) como parametro de localizacao. A
    chave de API so e anexada quando configurada em Settings.
    """
    settings = settings or get_settings()

    params: dict[str, str] = {}
    if destino.latitude is not None and destino.longitude is not None:
        params["location"] = f"{destino.latitude},{destino.longitude}"
    else:
        params["location"] = _descricao_local(destino)

    if settings.streetview_api_key:
        params["key"] = settings.streetview_api_key

    # quote_via=quote preserva virgulas legiveis em location sem quebrar a URL.
    query = urlencode(params, quote_via=quote)
    return f"{settings.streetview_base_url}?{query}"


def montar_embed_html(url: str, titulo: str) -> str:
    """Monta um iframe de embed para a URL de Street View (visualizacao 3D)."""
    titulo_seguro = titulo.replace('"', "&quot;")
    return (
        f'<iframe title="{titulo_seguro}" src="{url}" '
        'width="600" height="450" style="border:0;" '
        'allowfullscreen loading="lazy"></iframe>'
    )
