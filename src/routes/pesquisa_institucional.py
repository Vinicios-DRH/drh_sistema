"""Rotas da Pesquisa Institucional (LNTD / ESASP):
1. Formulário de avaliação dos 102 cursos (1 a 5, inteiro) dividido pelas 11
   seções da ESASP + campo de sugestão de cursos não listados, voltado aos
   militares (perfil ATUALIZACAO CADASTRAL / autoatendimento militar).
2. Painel de consolidação (ordenado de forma decrescente pelo somatório de
   notas em cada curso), listagem de avaliações individuais por militar,
   visualização detalhada das notas de cada militar e exportação Excel (.xlsx)
   para o Super User e militares da BM-3.
"""
from __future__ import annotations

from io import BytesIO
from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src import app, database
from src.authz import (
    can_view_pesquisa_institucional_resultados,
    is_super,
    pode_ver_autoatendimento_militar,
)
from src.formatar_cpf import get_militar_por_user
from src.models import Militar
from src.services.pesquisa_institucional_service import (
    ESCALA_CORES,
    ESCALA_NOTAS,
    ano_pesquisa_vigente,
    listar_cursos_ativos,
    listar_respostas_individuais,
    listar_trilhas_e_cursos,
    obter_consolidado_pesquisa,
    obter_detalhe_resposta_individual,
    obter_resposta_militar,
    salvar_resposta_pesquisa,
)


def _resolver_militar_atual() -> Militar | None:
    mid = getattr(current_user, "militar_id", None)
    if mid:
        militar = database.session.get(Militar, mid)
        if militar:
            return militar
    return get_militar_por_user(current_user)


def _obter_ip_cliente() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64]


def _pode_responder_pesquisa() -> bool:
    if not getattr(current_user, "is_authenticated", False):
        return False
    return (
        pode_ver_autoatendimento_militar()
        or can_view_pesquisa_institucional_resultados()
        or is_super()
        or bool(getattr(current_user, "militar_id", None))
    )


# ---------------------------------------------------------------------------
# 1. Formulário do Militar (ATUALIZACAO CADASTRAL / Autoatendimento)
# ---------------------------------------------------------------------------

@app.route("/pesquisa-institucional", methods=["GET", "POST"])
@login_required
def pesquisa_institucional_form():
    if not _pode_responder_pesquisa():
        abort(403)

    militar = _resolver_militar_atual()
    ano = ano_pesquisa_vigente()
    trilhas = listar_trilhas_e_cursos()
    cursos_ativos = listar_cursos_ativos()
    total_cursos = len(cursos_ativos)

    resposta_existente, notas_atuais = obter_resposta_militar(
        militar.id if militar else None,
        current_user.id,
        ano=ano,
    )
    sugestao_atual = (
        resposta_existente.sugestao_cursos_nao_listados
        if resposta_existente
        else ""
    )

    if request.method == "POST":
        notas_enviadas: dict[int, int] = {}
        for c in cursos_ativos:
            raw_val = (request.form.get(f"nota_{c.id}") or "").strip()
            if raw_val:
                try:
                    notas_enviadas[c.id] = int(raw_val)
                except ValueError:
                    notas_enviadas[c.id] = -1

        sugestao_form = request.form.get("sugestao_cursos_nao_listados") or ""
        try:
            salvar_resposta_pesquisa(
                militar=militar,
                user=current_user,
                notas_por_curso=notas_enviadas,
                sugestao_texto=sugestao_form,
                ip_address=_obter_ip_cliente(),
                ano=ano,
            )
            flash(
                "Sua avaliação na Pesquisa Institucional (LNTD / ESASP) foi "
                "registrada com sucesso! Obrigado pela contribuição.",
                "alert-success",
            )
            return redirect(url_for("pesquisa_institucional_form"))
        except ValueError as e:
            database.session.rollback()
            notas_atuais = {k: v for k, v in notas_enviadas.items() if v in ESCALA_NOTAS}
            sugestao_atual = sugestao_form
            flash(str(e), "alert-warning")
        except Exception as e:
            database.session.rollback()
            current_app.logger.exception("Erro ao salvar Pesquisa Institucional")
            notas_atuais = {k: v for k, v in notas_enviadas.items() if v in ESCALA_NOTAS}
            sugestao_atual = sugestao_form
            flash(f"Erro ao registrar a pesquisa: {e}", "alert-danger")

    return render_template(
        "pesquisa_institucional/formulario.html",
        militar=militar,
        ano=ano,
        trilhas=trilhas,
        total_cursos=total_cursos,
        escala_notas=ESCALA_NOTAS,
        escala_cores=ESCALA_CORES,
        resposta_existente=resposta_existente,
        notas_atuais=notas_atuais,
        sugestao_atual=sugestao_atual or "",
        pode_ver_resultados=can_view_pesquisa_institucional_resultados(),
    )


# ---------------------------------------------------------------------------
# 2. Painel de Consolidação e Notas Individuais (Super User e BM-3)
# ---------------------------------------------------------------------------

@app.get("/pesquisa-institucional/resultados")
@login_required
def pesquisa_institucional_resultados():
    if not can_view_pesquisa_institucional_resultados():
        abort(403)

    ano = request.args.get("ano", type=int) or ano_pesquisa_vigente()
    secao_filtro = (request.args.get("secao") or "").strip().lower() or None
    busca = (request.args.get("q") or "").strip() or None
    busca_militar = (request.args.get("qm") or "").strip() or None
    aba_ativa = (request.args.get("aba") or "ranking").strip().lower()

    consolidado = obter_consolidado_pesquisa(
        ano=ano,
        secao_filtro=secao_filtro,
        busca=busca,
    )
    respostas_individuais = listar_respostas_individuais(
        ano=ano,
        busca=busca_militar,
    )
    sugestoes_lista = [
        r
        for r in respostas_individuais
        if r.get("sugestao_cursos_nao_listados")
        and r["sugestao_cursos_nao_listados"].strip()
    ]
    trilhas_catalogo = listar_trilhas_e_cursos()

    return render_template(
        "pesquisa_institucional/resultados_bm3.html",
        ano=ano,
        secao_filtro=secao_filtro or "",
        busca=busca or "",
        busca_militar=busca_militar or "",
        aba_ativa=aba_ativa,
        consolidado=consolidado,
        respostas_individuais=respostas_individuais,
        sugestoes_lista=sugestoes_lista,
        trilhas_catalogo=trilhas_catalogo,
        escala_notas=ESCALA_NOTAS,
        escala_cores=ESCALA_CORES,
    )


@app.get("/pesquisa-institucional/respostas/<int:resposta_id>")
@login_required
def pesquisa_institucional_detalhe_militar(resposta_id: int):
    if not can_view_pesquisa_institucional_resultados():
        abort(403)

    detalhe = obter_detalhe_resposta_individual(resposta_id)
    if not detalhe:
        abort(404)

    return render_template(
        "pesquisa_institucional/detalhe_militar.html",
        detalhe=detalhe,
        escala_notas=ESCALA_NOTAS,
        escala_cores=ESCALA_CORES,
    )


@app.get("/pesquisa-institucional/resultados/exportar.xlsx")
@login_required
def pesquisa_institucional_exportar_excel():
    if not can_view_pesquisa_institucional_resultados():
        abort(403)

    ano = request.args.get("ano", type=int) or ano_pesquisa_vigente()
    consolidado = obter_consolidado_pesquisa(ano=ano)
    respostas = listar_respostas_individuais(ano=ano)

    wb = Workbook()

    header_fill = PatternFill(start_color="0B2E4F", end_color="0B2E4F", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    # Planilha 1: Ranking Consolidado (Ordem Decrescente de Somatório)
    ws_rank = wb.active
    ws_rank.title = "Ranking Consolidado"
    headers_rank = [
        "Posição",
        "Trilha (Código)",
        "Área Educacional (ESASP)",
        "Curso",
        "Somatório de Notas",
        "Média (1 a 5)",
        "Total de Avaliações",
        "Nota 5 (Muito relevante)",
        "Nota 4 (Relevante)",
        "Nota 3 (Moderadamente relevante)",
        "Nota 2 (Pouco relevante)",
        "Nota 1 (Irrelevante)",
        "% Relevante / Muito Relevante",
    ]
    ws_rank.append(headers_rank)
    for col_idx in range(1, len(headers_rank) + 1):
        cell = ws_rank.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for item in consolidado["ranking_cursos"]:
        ws_rank.append([
            item["posicao"],
            item["secao_codigo"].upper(),
            item["secao_titulo"],
            item["nome"],
            item["somatorio_notas"],
            item["media_notas"],
            item["total_votos"],
            item["qtd_5"],
            item["qtd_4"],
            item["qtd_3"],
            item["qtd_2"],
            item["qtd_1"],
            f"{item['pct_relevante']}%",
        ])

    # Planilha 2: Notas Individuais por Militar
    ws_ind = wb.create_sheet(title="Notas Individuais")
    headers_ind = [
        "Data/Hora",
        "Posto/Grad",
        "Nome Completo",
        "Nome de Guerra",
        "Matrícula",
        "OBM",
        "Trilha",
        "Curso",
        "Nota (1 a 5)",
        "Classificação",
    ]
    ws_ind.append(headers_ind)
    for col_idx in range(1, len(headers_ind) + 1):
        cell = ws_ind.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r_resumo in respostas:
        det = obter_detalhe_resposta_individual(r_resumo["id"])
        if not det:
            continue
        dt_str = (
            det["atualizado_em"].strftime("%d/%m/%Y %H:%M")
            if det["atualizado_em"]
            else "—"
        )
        for sec in det["secoes"]:
            for c_av in sec["cursos_avaliados"]:
                ws_ind.append([
                    dt_str,
                    det["posto_grad"],
                    det["nome_completo"],
                    det["nome_guerra"],
                    det["matricula"],
                    det["obm_sigla"],
                    f"{sec['codigo'].upper()} - {sec['titulo']}",
                    c_av["nome"],
                    c_av["nota"] or "",
                    c_av["nota_label"],
                ])

    # Planilha 3: Sugestões de Cursos Não Listados
    ws_sug = wb.create_sheet(title="Cursos Não Listados")
    headers_sug = [
        "Data/Hora",
        "Posto/Grad",
        "Nome Completo",
        "Matrícula",
        "OBM",
        "Sugestão de Treinamento / Capacitação Não Listada",
    ]
    ws_sug.append(headers_sug)
    for col_idx in range(1, len(headers_sug) + 1):
        cell = ws_sug.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r_resumo in respostas:
        sug = (r_resumo.get("sugestao_cursos_nao_listados") or "").strip()
        if not sug:
            continue
        dt_str = (
            r_resumo["atualizado_em"].strftime("%d/%m/%Y %H:%M")
            if r_resumo.get("atualizado_em")
            else "—"
        )
        ws_sug.append([
            dt_str,
            r_resumo["posto_grad"],
            r_resumo["nome_completo"],
            r_resumo["matricula"],
            r_resumo["obm_sigla"],
            sug,
        ])

    for ws in (ws_rank, ws_ind, ws_sug):
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 58)
            for cell in col:
                cell.border = thin_border

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=f"Pesquisa_Institucional_LNTD_ESASP_{ano}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
