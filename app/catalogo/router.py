"""Rotas HTTP do catalogo: busca de pacotes (RF3) e visualizacao 3D (RF9).

Endpoints:
  GET /catalogo/pacotes            - busca de pacotes com filtros (RF3)
  GET /catalogo/destinos/{id}/streetview - URL/embed de Street View (RF9)

A logica de filtragem e de montagem de URL vive em funcoes puras testaveis.
Sem banco configurado, ``DatabaseNotConfiguredError`` vira HTTP 503.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.catalogo import repository
from app.catalogo.schemas import (
    DestinoCriar,
    DestinoSaida,
    HospedagemCriar,
    HospedagemSaida,
    PacoteCriar,
    PacoteSaida,
    ResultadoBusca,
    StreetViewSaida,
    ViagemCriar,
    ViagemSaida,
)
from app.catalogo.service import filtrar_pacotes
from app.core.authz import Permissao
from app.core.deps import requer_permissao
from app.db.session import DatabaseNotConfiguredError
from app.integracoes.streetview import (
    montar_embed_html,
    montar_url_streetview,
)

router = APIRouter(prefix="/catalogo", tags=["catalogo"])


def _erro_db_indisponivel() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Banco de dados nao configurado. Configure as variaveis "
            "WANDERLUST_DB_* para habilitar a persistencia."
        ),
    )


@router.get("/pacotes", response_model=ResultadoBusca)
def buscar_pacotes(
    tipo_viagem: Optional[str] = Query(default=None),
    nivel: Optional[str] = Query(default=None),
    data_inicio: Optional[date] = Query(default=None),
    data_fim: Optional[date] = Query(default=None),
    somente_disponiveis: bool = Query(default=True),
) -> ResultadoBusca:
    """Busca pacotes por tipo, nivel e janela de datas (RF3)."""
    try:
        pacotes = repository.listar_pacotes()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    filtrados = filtrar_pacotes(
        pacotes,
        tipo_viagem=tipo_viagem,
        nivel=nivel,
        data_inicio=data_inicio,
        data_fim=data_fim,
        somente_disponiveis=somente_disponiveis,
    )
    return ResultadoBusca(total=len(filtrados), pacotes=filtrados)


@router.get("/pacotes/{id_pacote}", response_model=PacoteSaida)
def obter_pacote(id_pacote: int) -> PacoteSaida:
    """Carrega um pacote unico pelo id (leitura publica do catalogo, RF3).

    Fecha o R do CRUD de Pacote: assim como GET /catalogo/pacotes lista e e
    publico, esta leitura por id tambem permanece publica (sem gate).
    """
    try:
        pacote = repository.buscar_pacote(id_pacote)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if pacote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pacote nao encontrado."
        )
    return pacote


@router.get("/destinos", response_model=List[DestinoSaida])
def listar_destinos() -> List[DestinoSaida]:
    """Lista os destinos do catalogo (leitura publica, RF3/RF9).

    Fecha o R do CRUD de Destino: a leitura por id completa (ja existente,
    gated) e a listagem publica aqui compoem o read simetrico. Mantem a
    convencao dos demais GET de catalogo, que sao publicos.
    """
    try:
        return repository.listar_destinos()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.get("/destinos/{id_destino}/streetview", response_model=StreetViewSaida)
def streetview_destino(id_destino: int) -> StreetViewSaida:
    """Retorna a URL/embed de Street View (visualizacao 3D) de um destino (RF9)."""
    try:
        destino = repository.buscar_destino(id_destino)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if destino is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Destino nao encontrado."
        )

    url = montar_url_streetview(destino)
    local = ", ".join(p for p in (destino.cidade, destino.estado, destino.pais) if p)
    return StreetViewSaida(
        id_destino=destino.id_destino,
        local=local,
        url=url,
        embed_html=montar_embed_html(url, local),
    )


# ---------------------------------------------------------------------------
# Gerenciar Catalogo (Administrador, secao 4.1): CRUD de Pacote e Destino.
# Todas as rotas abaixo exigem a permissao GERENCIAR_CATALOGO (403 para quem
# nao tem; 401 sem token). As rotas GET publicas acima permanecem sem gate.
# ---------------------------------------------------------------------------


@router.post(
    "/pacotes",
    response_model=PacoteSaida,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def criar_pacote(dados: PacoteCriar) -> PacoteSaida:
    """Cria um pacote no catalogo (Gerenciar Catalogo, secao 4.1)."""
    try:
        return repository.criar_pacote(dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.put(
    "/pacotes/{id_pacote}",
    response_model=PacoteSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def atualizar_pacote(id_pacote: int, dados: PacoteCriar) -> PacoteSaida:
    """Atualiza um pacote existente (Gerenciar Catalogo, secao 4.1)."""
    try:
        atualizado = repository.atualizar_pacote(id_pacote, dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if atualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pacote nao encontrado."
        )
    return atualizado


@router.delete(
    "/pacotes/{id_pacote}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def excluir_pacote(id_pacote: int) -> None:
    """Remove um pacote do catalogo (Gerenciar Catalogo, secao 4.1)."""
    try:
        removido = repository.excluir_pacote(id_pacote)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pacote nao encontrado."
        )


@router.post(
    "/destinos",
    response_model=DestinoSaida,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def criar_destino(dados: DestinoCriar) -> DestinoSaida:
    """Cria um destino no catalogo (Gerenciar Catalogo, secao 4.1)."""
    try:
        return repository.criar_destino(dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.get(
    "/destinos/{id_destino}",
    response_model=DestinoSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def obter_destino(id_destino: int) -> DestinoSaida:
    """Carrega um destino completo pelo id (Gerenciar Catalogo, secao 4.1)."""
    try:
        destino = repository.buscar_destino_completo(id_destino)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if destino is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Destino nao encontrado."
        )
    return destino


@router.put(
    "/destinos/{id_destino}",
    response_model=DestinoSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def atualizar_destino(id_destino: int, dados: DestinoCriar) -> DestinoSaida:
    """Atualiza um destino existente (Gerenciar Catalogo, secao 4.1)."""
    try:
        atualizado = repository.atualizar_destino(id_destino, dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if atualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Destino nao encontrado."
        )
    return atualizado


@router.delete(
    "/destinos/{id_destino}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def excluir_destino(id_destino: int) -> None:
    """Remove um destino do catalogo (Gerenciar Catalogo, secao 4.1)."""
    try:
        removido = repository.excluir_destino(id_destino)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Destino nao encontrado."
        )


# ---------------------------------------------------------------------------
# Agendar Viagem (Administrador, secao 4.1): criar/listar/excluir Viagem.
# Exige a permissao AGENDAR.
# ---------------------------------------------------------------------------


@router.post(
    "/viagens",
    response_model=ViagemSaida,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requer_permissao(Permissao.AGENDAR))],
)
def agendar_viagem(dados: ViagemCriar) -> ViagemSaida:
    """Agenda uma viagem vinculada a um destino (Agendar Viagem, secao 4.1)."""
    try:
        return repository.criar_viagem(dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.get(
    "/viagens",
    response_model=List[ViagemSaida],
    dependencies=[Depends(requer_permissao(Permissao.AGENDAR))],
)
def listar_viagens() -> List[ViagemSaida]:
    """Lista as viagens agendadas (Agendar Viagem, secao 4.1)."""
    try:
        return repository.listar_viagens()
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.delete(
    "/viagens/{id_viagem}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requer_permissao(Permissao.AGENDAR))],
)
def excluir_viagem(id_viagem: int) -> None:
    """Remove uma viagem agendada (Agendar Viagem, secao 4.1)."""
    try:
        removido = repository.excluir_viagem(id_viagem)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Viagem nao encontrada."
        )


# ---------------------------------------------------------------------------
# Gerenciar Catalogo (Administrador, secao 4.1): CRUD de Hospedagem.
# Todas as rotas exigem a permissao GERENCIAR_CATALOGO (403 para quem nao tem;
# 401 sem token). 404 para id inexistente; 503 sem banco.
# ---------------------------------------------------------------------------


@router.post(
    "/hospedagens",
    response_model=HospedagemSaida,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def criar_hospedagem(dados: HospedagemCriar) -> HospedagemSaida:
    """Cria uma hospedagem vinculada a um pacote (Gerenciar Catalogo, 4.1)."""
    try:
        return repository.criar_hospedagem(dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.get(
    "/hospedagens",
    response_model=List[HospedagemSaida],
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def listar_hospedagens(
    fk_pacote: Optional[int] = Query(default=None),
) -> List[HospedagemSaida]:
    """Lista hospedagens, opcionalmente filtrando por pacote (Gerenciar, 4.1)."""
    try:
        return repository.listar_hospedagens(fk_pacote)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc


@router.get(
    "/hospedagens/{id_hospedagem}",
    response_model=HospedagemSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def obter_hospedagem(id_hospedagem: int) -> HospedagemSaida:
    """Carrega uma hospedagem pelo id (Gerenciar Catalogo, secao 4.1)."""
    try:
        hospedagem = repository.buscar_hospedagem(id_hospedagem)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if hospedagem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospedagem nao encontrada.",
        )
    return hospedagem


@router.put(
    "/hospedagens/{id_hospedagem}",
    response_model=HospedagemSaida,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def atualizar_hospedagem(
    id_hospedagem: int, dados: HospedagemCriar
) -> HospedagemSaida:
    """Atualiza uma hospedagem existente (Gerenciar Catalogo, secao 4.1)."""
    try:
        atualizada = repository.atualizar_hospedagem(id_hospedagem, dados)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if atualizada is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospedagem nao encontrada.",
        )
    return atualizada


@router.delete(
    "/hospedagens/{id_hospedagem}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requer_permissao(Permissao.GERENCIAR_CATALOGO))],
)
def excluir_hospedagem(id_hospedagem: int) -> None:
    """Remove uma hospedagem do catalogo (Gerenciar Catalogo, secao 4.1)."""
    try:
        removido = repository.excluir_hospedagem(id_hospedagem)
    except DatabaseNotConfiguredError as exc:
        raise _erro_db_indisponivel() from exc

    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospedagem nao encontrada.",
        )
