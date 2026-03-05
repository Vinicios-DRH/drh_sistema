# src/routes_historico.py
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, abort
from sqlalchemy import text
from src import database as db
from src.authz import require_perm

bp_historico = Blueprint("historico_militar", __name__,
                         url_prefix="/historico")


def _to_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


@bp_historico.get("/")
@require_perm("HISTORICO_MILITAR_READ")
def pagina_historico():
    """
    Página do painel.
    """
    militar_id = _to_int(request.args.get("militar_id"))
    return render_template("historico/historico_militar.html", militar_id=militar_id)


@bp_historico.get("/api/search")
@require_perm("HISTORICO_MILITAR_READ")
def api_search_militares():
    """
    Autocomplete do Select2.
    /historico/api/search?q=joao
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"results": []})

    like = f"%{q}%"
    sql = text("""
        SELECT
            m.id,
            m.nome_completo,
            m.nome_guerra,
            m.matricula,
            pg.sigla AS posto_grad
        FROM militar m
        LEFT JOIN posto_grad pg ON pg.id = m.posto_grad_id
        WHERE
            m.nome_completo ILIKE :like
            OR m.nome_guerra ILIKE :like
            OR m.matricula ILIKE :like
            OR m.cpf ILIKE :like
        ORDER BY m.nome_completo
        LIMIT 20
    """)
    rows = db.session.execute(sql, {"like": like}).mappings().all()

    results = []
    for r in rows:
        label = f"{r['posto_grad'] or ''} {r['nome_guerra'] or r['nome_completo']} — ID {r['id']}"
        if r["matricula"]:
            label += f" (Mat: {r['matricula']})"
        results.append({"id": r["id"], "text": label})

    return jsonify({"results": results})


@bp_historico.get("/api/<int:militar_id>/header")
@require_perm("HISTORICO_MILITAR_READ")
def api_header(militar_id: int):
    """
    Dados do militar (cartão de topo).
    """
    sql = text("""
        SELECT
            m.id,
            m.nome_completo,
            m.nome_guerra,
            m.matricula,
            m.cpf,
            m.rg,
            m.sexo,
            m.data_nascimento,
            pg.sigla AS posto_grad,
            q.quadro AS quadro,
            l.sigla AS localidade,
            s1.condicao AS situacao1,
            s2.condicao AS situacao2,
            e.ocupacao AS especialidade,
            d.local AS destino,
            m.inativo
        FROM militar m
        LEFT JOIN posto_grad pg ON pg.id = m.posto_grad_id
        LEFT JOIN quadro q ON q.id = m.quadro_id
        LEFT JOIN localidade l ON l.id = m.localidade_id
        LEFT JOIN situacao s1 ON s1.id = m.situacao_id
        LEFT JOIN situacao s2 ON s2.id = m.situacao2_id
        LEFT JOIN especialidade e ON e.id = m.especialidade_id
        LEFT JOIN destino d ON d.id = m.destino_id
        WHERE m.id = :militar_id
        LIMIT 1
    """)
    row = db.session.execute(
        sql, {"militar_id": militar_id}).mappings().first()
    if not row:
        abort(404, "Militar não encontrado.")
    return jsonify({"ok": True, "militar": dict(row)})


@bp_historico.get("/api/<int:militar_id>/timeline")
@require_perm("HISTORICO_MILITAR_READ")
def api_timeline(militar_id: int):
    """
    Timeline unificada com filtros/paginação.

    Querystring:
      - tipos=BG,LTS,DISPOSICAO (csv)
      - q=busca textual
      - de=YYYY-MM-DD
      - ate=YYYY-MM-DD
      - page=1
      - per_page=20 (máx 50)
    """
    tipos_csv = (request.args.get("tipos") or "").strip()
    q = (request.args.get("q") or "").strip()
    de_raw = (request.args.get("de") or "").strip()
    ate_raw = (request.args.get("ate") or "").strip()

    de = de_raw if de_raw else None
    ate = ate_raw if ate_raw else None
    page = max(_to_int(request.args.get("page"), 1), 1)
    per_page = min(max(_to_int(request.args.get("per_page"), 20), 5), 50)
    offset = (page - 1) * per_page

    tipos = [t.strip().upper()
             for t in tipos_csv.split(",") if t.strip()] if tipos_csv else []

    # busca
    like = f"%{q}%" if q else None

    # SQL base (UNION ALL). A gente filtra por tipo/data/texto no SELECT externo.
    sql = text("""
        WITH
        mil AS (
        SELECT m.*, pg.sigla AS posto_grad_sigla
        FROM militar m
        LEFT JOIN posto_grad pg ON pg.id = m.posto_grad_id
        WHERE m.id = :militar_id
        ),
        usr AS (
        SELECT u.*
        FROM "user" u
        WHERE u.militar_id = :militar_id
        ORDER BY u.id DESC
        ),
        eventos AS (

        /* ===========================
            1) EVENTO “CADASTRO MILITAR”
            =========================== */
        SELECT
            ('MILITAR:' || m.id)::text AS id_evento,
            'MILITAR'::text AS tipo,
            COALESCE(m.data_criacao::date, m.inclusao) AS data_inicio,
            NULL::date AS data_fim,
            ('Cadastro do Militar - ' || COALESCE(m.posto_grad_sigla,'') )::text AS titulo,
            COALESCE(m.nome_guerra, m.nome_completo)::text AS descricao,
            m.id::bigint AS ref_id,
            to_jsonb(m) AS payload
        FROM mil m

        UNION ALL

        /* ===========================
            2) USER VINCULADO AO MILITAR
            =========================== */
        SELECT
            ('USER:' || u.id)::text AS id_evento,
            'USER'::text AS tipo,
            COALESCE(u.data_criacao::date, CURRENT_DATE) AS data_inicio,
            NULL::date AS data_fim,
            ('Conta no sistema - ' || COALESCE(u.tipo_perfil,'MILITAR'))::text AS titulo,
            (COALESCE(u.nome,'') || ' • ' || COALESCE(u.email,''))::text AS descricao,
            u.id::bigint AS ref_id,
            to_jsonb(u) AS payload
        FROM usr u

        UNION ALL

        /* ===========================
            3) USER PERMISSÕES
            =========================== */
        SELECT
            ('USER_PERM:' || up.id)::text AS id_evento,
            'USER_PERMISSAO'::text AS tipo,
            up.created_at::date AS data_inicio,
            NULL::date AS data_fim,
            ('Permissão ' || up.codigo)::text AS titulo,
            ('Ativo: ' || up.ativo)::text AS descricao,
            up.id::bigint AS ref_id,
            to_jsonb(up) AS payload
        FROM user_permissao up
        JOIN usr u ON u.id = up.user_id

        UNION ALL

        /* ===========================
            4) USER OBM ACESSO (delegações)
            =========================== */
        SELECT
            ('USER_OBM:' || uoa.id)::text AS id_evento,
            'USER_OBM_ACESSO'::text AS tipo,
            uoa.created_at::date AS data_inicio,
            NULL::date AS data_fim,
            ('Acesso OBM - ' || COALESCE(o.sigla,''))::text AS titulo,
            ('Tipo: ' || COALESCE(uoa.tipo,'') || ' • Ativo: ' || uoa.ativo)::text AS descricao,
            uoa.id::bigint AS ref_id,
            (to_jsonb(uoa) || jsonb_build_object('obm_sigla', o.sigla)) AS payload
        FROM user_obm_acesso uoa
        JOIN usr u ON u.id = uoa.user_id
        LEFT JOIN obm o ON o.id = uoa.obm_id

        UNION ALL

        /* ===========================
            5) OBM GESTÃO (se fizer sentido pro usuário do militar)
            =========================== */
        SELECT
            ('OBM_GESTAO:' || og.id)::text AS id_evento,
            'OBM_GESTAO'::text AS tipo,
            CURRENT_DATE AS data_inicio,
            NULL::date AS data_fim,
            ('Gestão OBM - ' || COALESCE(o1.sigla,'') || ' → ' || COALESCE(o2.sigla,''))::text AS titulo,
            ('Ativo: ' || og.ativo)::text AS descricao,
            og.id::bigint AS ref_id,
            (to_jsonb(og) || jsonb_build_object('obm_gestora', o1.sigla, 'obm_gerida', o2.sigla)) AS payload
        FROM obm_gestao og
        LEFT JOIN obm o1 ON o1.id = og.obm_gestora_id
        LEFT JOIN obm o2 ON o2.id = og.obm_gerida_id
        WHERE og.obm_gestora_id IN (SELECT obm_id_1 FROM usr) OR og.obm_gestora_id IN (SELECT obm_id_2 FROM usr)

        UNION ALL

        /* ===========================
            6) BG (Publicações)
            =========================== */
        SELECT
            ('BG:' || pb.id)::text AS id_evento,
            'BG'::text AS tipo,
            NULL::date AS data_inicio,
            NULL::date AS data_fim,
            pb.tipo_bg::text AS titulo,
            pb.boletim_geral::text AS descricao,
            pb.id::bigint AS ref_id,
            to_jsonb(pb) AS payload
        FROM publicacaobg pb
        WHERE pb.militar_id = :militar_id

        UNION ALL

        /* ===========================
            7) OBM/FUNÇÃO (lotação/função)
            =========================== */
        SELECT
            ('OBM_FUNCAO:' || mof.id)::text AS id_evento,
            'OBM_FUNCAO'::text AS tipo,
            mof.data_criacao::date AS data_inicio,
            mof.data_fim::date AS data_fim,
            (COALESCE(o.sigla,'') || ' - ' || COALESCE(f.ocupacao,''))::text AS titulo,
            NULL::text AS descricao,
            mof.id::bigint AS ref_id,
            (to_jsonb(mof) || jsonb_build_object('obm_sigla', o.sigla, 'funcao', f.ocupacao)) AS payload
        FROM militar_obm_funcao mof
        LEFT JOIN obm o ON o.id = mof.obm_id
        LEFT JOIN funcao f ON f.id = mof.funcao_id
        WHERE mof.militar_id = :militar_id

        UNION ALL

        /* ===========================
            8) À DISPOSIÇÃO
            =========================== */
        SELECT
            ('DISPOSICAO:' || mad.id)::text AS id_evento,
            'DISPOSICAO'::text AS tipo,
            mad.inicio_periodo AS data_inicio,
            mad.fim_periodo_disposicao AS data_fim,
            ('À disposição - ' || COALESCE(mad.status,''))::text AS titulo,
            NULL::text AS descricao,
            mad.id::bigint AS ref_id,
            to_jsonb(mad) AS payload
        FROM militares_a_disposicao mad
        WHERE mad.militar_id = :militar_id

        UNION ALL

        /* ===========================
            9) AGREGAÇÃO
            =========================== */
        SELECT
            ('AGREGACAO:' || mag.id)::text AS id_evento,
            'AGREGACAO'::text AS tipo,
            mag.inicio_periodo AS data_inicio,
            mag.fim_periodo_agregacao AS data_fim,
            ('Agregação - ' || COALESCE(mag.status,''))::text AS titulo,
            NULL::text AS descricao,
            mag.id::bigint AS ref_id,
            to_jsonb(mag) AS payload
        FROM militares_agregados mag
        WHERE mag.militar_id = :militar_id

        UNION ALL

        /* ===========================
            10) LICENÇA ESPECIAL
            =========================== */
        SELECT
            ('LICENCA_ESPECIAL:' || le.id)::text AS id_evento,
            'LICENCA_ESPECIAL'::text AS tipo,
            le.inicio_periodo_le AS data_inicio,
            le.fim_periodo_le AS data_fim,
            ('Licença Especial - ' || COALESCE(le.status,''))::text AS titulo,
            NULL::text AS descricao,
            le.id::bigint AS ref_id,
            to_jsonb(le) AS payload
        FROM licenca_especial le
        WHERE le.militar_id = :militar_id

        UNION ALL

        /* ===========================
            11) LTS (MILITAR)
            =========================== */
        SELECT
            ('LTS:' || lts.id)::text AS id_evento,
            'LTS'::text AS tipo,
            lts.inicio_periodo_lts AS data_inicio,
            lts.fim_periodo_lts AS data_fim,
            ('LTS - ' || COALESCE(lts.status,''))::text AS titulo,
            NULL::text AS descricao,
            lts.id::bigint AS ref_id,
            to_jsonb(lts) AS payload
        FROM licenca_para_tratamento_de_saude lts
        WHERE lts.militar_id = :militar_id

        UNION ALL

        /* ===========================
            12) PAF (ANTIGO)
            =========================== */
        SELECT
            ('PAF:' || p.id)::text AS id_evento,
            'PAF'::text AS tipo,
            p.primeiro_periodo_ferias AS data_inicio,
            p.fim_primeiro_periodo AS data_fim,
            ('PAF ' || p.ano_referencia)::text AS titulo,
            ('Mes usufruto: ' || COALESCE(p.mes_usufruto,''))::text AS descricao,
            p.id::bigint AS ref_id,
            to_jsonb(p) AS payload
        FROM paf p
        WHERE p.militar_id = :militar_id

        UNION ALL

        /* ===========================
            13) NOVO PAF
            =========================== */
        SELECT
            ('NOVO_PAF:' || np.id)::text AS id_evento,
            'NOVO_PAF'::text AS tipo,
            np.data_entrega::date AS data_inicio,
            NULL::date AS data_fim,
            ('Novo PAF ' || np.ano_referencia || ' - ' || np.status)::text AS titulo,
            NULL::text AS descricao,
            np.id::bigint AS ref_id,
            to_jsonb(np) AS payload
        FROM novo_paf np
        WHERE np.militar_id = :militar_id

        UNION ALL

        /* ===========================
            14) PLANO DE FÉRIAS
            =========================== */
        SELECT
            ('PAF_PLANO:' || pfp.id)::text AS id_evento,
            'PAF_PLANO'::text AS tipo,
            pfp.inicio_p1 AS data_inicio,
            pfp.fim_p1 AS data_fim,
            ('Plano Férias ' || pfp.ano_referencia || ' - ' || pfp.status)::text AS titulo,
            NULL::text AS descricao,
            pfp.id::bigint AS ref_id,
            to_jsonb(pfp) AS payload
        FROM paf_ferias_plano pfp
        WHERE pfp.militar_id = :militar_id

        UNION ALL

        /* ===========================
            15) MOTORISTA/CNH
            =========================== */
        SELECT
            ('MOTORISTA:' || mo.id)::text AS id_evento,
            'MOTORISTA'::text AS tipo,
            mo.created::date AS data_inicio,
            NULL::date AS data_fim,
            ('CNH - ' || COALESCE(cat.sigla,'') )::text AS titulo,
            COALESCE(mo.boletim_geral, mo.siged)::text AS descricao,
            mo.id::bigint AS ref_id,
            (to_jsonb(mo) || jsonb_build_object('categoria', cat.sigla)) AS payload
        FROM motoristas mo
        LEFT JOIN categoria cat ON cat.id = mo.categoria_id
        WHERE mo.militar_id = :militar_id

        UNION ALL

        /* ===========================
            16) VIATURAS (vínculos)
            =========================== */
        SELECT
            ('VIATURA:' || vm.id)::text AS id_evento,
            'VIATURA'::text AS tipo,
            vm.created_at::date AS data_inicio,
            NULL::date AS data_fim,
            (COALESCE(v.prefixo,'') || ' - ' || COALESCE(v.placa,'') )::text AS titulo,
            COALESCE(v.marca_modelo,'')::text AS descricao,
            vm.id::bigint AS ref_id,
            (to_jsonb(vm) || jsonb_build_object('prefixo', v.prefixo, 'placa', v.placa, 'marca_modelo', v.marca_modelo)) AS payload
        FROM viatura_militar vm
        JOIN viaturas v ON v.id = vm.viatura_id
        WHERE vm.militar_id = :militar_id

        UNION ALL

        /* ===========================
            17) SEGUNDO VÍNCULO (se existir no teu sistema)
            =========================== */
        SELECT
            ('SEGUNDO_VINCULO:' || sv.id)::text AS id_evento,
            'SEGUNDO_VINCULO'::text AS tipo,
            sv.data_registro::date AS data_inicio,
            NULL::date AS data_fim,
            ('Segundo vínculo - ' || COALESCE(sv.possui_vinculo::text,'false'))::text AS titulo,
            COALESCE(sv.descricao_vinculo,'')::text AS descricao,
            sv.id::bigint AS ref_id,
            to_jsonb(sv) AS payload
        FROM segundo_vinculo sv
        WHERE sv.militar_id = :militar_id

        UNION ALL

        /* ===========================
            18) DECLARAÇÃO ACÚMULO
            =========================== */
        SELECT
            ('DECLARACAO:' || da.id)::text AS id_evento,
            'DECLARACAO'::text AS tipo,
            da.data_entrega::date AS data_inicio,
            NULL::date AS data_fim,
            ('Declaração ' || da.ano_referencia || ' - ' || da.status)::text AS titulo,
            ('Tipo: ' || da.tipo || ' | Meio: ' || da.meio_entrega)::text AS descricao,
            da.id::bigint AS ref_id,
            to_jsonb(da) AS payload
        FROM declaracao_acumulo da
        WHERE da.militar_id = :militar_id

        UNION ALL

        /* ===========================
            19) VÍNCULO EXTERNO (do militar via declaração)
            =========================== */
        SELECT
            ('VINCULO_EXT:' || ve.id)::text AS id_evento,
            'VINCULO_EXTERNO'::text AS tipo,
            ve.data_inicio AS data_inicio,
            NULL::date AS data_fim,
            (ve.empregador_nome || ' - ' || ve.cargo_funcao)::text AS titulo,
            ('CH: ' || ve.carga_horaria_semanal || 'h • ' || ve.jornada_trabalho)::text AS descricao,
            ve.id::bigint AS ref_id,
            (to_jsonb(ve) || jsonb_build_object('declaracao_id', ve.declaracao_id)) AS payload
        FROM vinculo_externo ve
        JOIN declaracao_acumulo da ON da.id = ve.declaracao_id
        WHERE da.militar_id = :militar_id

        UNION ALL

        /* ===========================
            20) AUDITORIA DECLARAÇÃO
            =========================== */
        SELECT
            ('AUD_DECL:' || ad.id)::text AS id_evento,
            'AUDITORIA_DECLARACAO'::text AS tipo,
            ad.data_alteracao::date AS data_inicio,
            NULL::date AS data_fim,
            ('Status: ' || COALESCE(ad.de_status,'') || ' → ' || ad.para_status)::text AS titulo,
            COALESCE(ad.motivo,'')::text AS descricao,
            ad.id::bigint AS ref_id,
            (to_jsonb(ad) || jsonb_build_object('declaracao_id', ad.declaracao_id)) AS payload
        FROM auditoria_declaracao ad
        JOIN declaracao_acumulo da ON da.id = ad.declaracao_id
        WHERE da.militar_id = :militar_id

        UNION ALL

        /* ===========================
            21) DRAFT DECLARAÇÃO
            =========================== */
        SELECT
            ('DRAFT_DECL:' || dd.id)::text AS id_evento,
            'DRAFT_DECLARACAO'::text AS tipo,
            dd.updated_at::date AS data_inicio,
            NULL::date AS data_fim,
            ('Draft Declaração ' || dd.ano_referencia)::text AS titulo,
            NULL::text AS descricao,
            dd.id::bigint AS ref_id,
            to_jsonb(dd) AS payload
        FROM draft_declaracao_acumulo dd
        WHERE dd.militar_id = :militar_id

        UNION ALL

        /* ===========================
            22) DOCUMENTOS ENVIADOS
            =========================== */
        SELECT
            ('DOC:' || dm.id)::text AS id_evento,
            'DOC'::text AS tipo,
            dm.criado_em::date AS data_inicio,
            NULL::date AS data_fim,
            dm.nome_original::text AS titulo,
            dm.content_type::text AS descricao,
            dm.id::bigint AS ref_id,
            to_jsonb(dm) AS payload
        FROM documento_militar dm
        WHERE dm.militar_id = :militar_id

        UNION ALL

        /* ===========================
            23) TAREFA ATUALIZAÇÃO (cadete)
            =========================== */
        SELECT
            ('TAREFA_CADETE:' || tc.id)::text AS id_evento,
            'TAREFA_ATUALIZACAO'::text AS tipo,
            COALESCE(tc.atualizado_em::date, tc.criado_em::date) AS data_inicio,
            NULL::date AS data_fim,
            ('Tarefa Atualização - ' || tc.status)::text AS titulo,
            ('Cadete user: ' || tc.cadete_user_id || ' • Militar atribuído: ' || tc.militar_id)::text AS descricao,
            tc.id::bigint AS ref_id,
            to_jsonb(tc) AS payload
        FROM tarefa_atualizacao_cadete tc
        WHERE tc.militar_id = :militar_id OR tc.cadete_militar_id = :militar_id

        UNION ALL

        /* ===========================
            24) DEPENDENTES - PROCESSOS
            =========================== */
        SELECT
            ('DEP_PROC:' || dp.id)::text AS id_evento,
            'DEPENDENTE_PROCESSO'::text AS tipo,
            dp.enviado_em::date AS data_inicio,
            NULL::date AS data_fim,
            ('Dep. ' || COALESCE(dp.dependente_nome,'') || ' • ' || dp.ano)::text AS titulo,
            ('Status: ' || dp.status || ' • Protocolo: ' || dp.protocolo)::text AS descricao,
            dp.id::bigint AS ref_id,
            to_jsonb(dp) AS payload
        FROM dep_processo dp
        WHERE dp.militar_id = :militar_id

        UNION ALL

        /* ===========================
            25) DEPENDENTES - ARQUIVOS
            =========================== */
        SELECT
            ('DEP_ARQ:' || da.id)::text AS id_evento,
            'DEPENDENTE_ARQUIVO'::text AS tipo,
            da.criado_em::date AS data_inicio,
            NULL::date AS data_fim,
            COALESCE(da.nome_original,'Arquivo de dependente')::text AS titulo,
            COALESCE(da.content_type,'')::text AS descricao,
            da.id::bigint AS ref_id,
            (to_jsonb(da) || jsonb_build_object('processo_id', da.processo_id)) AS payload
        FROM dep_arquivo da
        JOIN dep_processo dp ON dp.id = da.processo_id
        WHERE dp.militar_id = :militar_id

        UNION ALL

        /* ===========================
            26) DEPENDENTES - AÇÕES (LOG)
            =========================== */
        SELECT
            ('DEP_ACAO:' || dl.id)::text AS id_evento,
            'DEPENDENTE_ACAO'::text AS tipo,
            dl.criado_em::date AS data_inicio,
            NULL::date AS data_fim,
            dl.acao::text AS titulo,
            COALESCE(dl.detalhes,'')::text AS descricao,
            dl.id::bigint AS ref_id,
            (to_jsonb(dl) || jsonb_build_object('processo_id', dl.processo_id)) AS payload
        FROM dep_acao_log dl
        JOIN dep_processo dp ON dp.id = dl.processo_id
        WHERE dp.militar_id = :militar_id

        UNION ALL

        /* ===========================
            27) TAF AVALIAÇÕES
            =========================== */
        SELECT
            ('TAF:' || t.id)::text AS id_evento,
            'TAF'::text AS tipo,
            t.criado_em::date AS data_inicio,
            NULL::date AS data_fim,
            (t.modalidade || ' - ' || t.atividade)::text AS titulo,
            ('Valor: ' || t.valor || ' | OK: ' || t.resultado_ok)::text AS descricao,
            t.id::bigint AS ref_id,
            to_jsonb(t) AS payload
        FROM taf_avaliacao t
        WHERE t.militar_id = :militar_id
        ),

        filtrado AS (
            SELECT
                *,
                COALESCE(data_inicio, data_fim, CURRENT_DATE) AS ev_inicio,
                COALESCE(data_fim, data_inicio, CURRENT_DATE) AS ev_fim
            FROM eventos
            WHERE
                (:tem_tipos = 0 OR tipo = ANY(CAST(:tipos AS text[])))

                -- SEM CAST('' AS date): usa NULL no backend
                AND (:de IS NULL OR COALESCE(data_fim, data_inicio, CURRENT_DATE) >= CAST(:de AS date))
                AND (:ate IS NULL OR COALESCE(data_inicio, data_fim, CURRENT_DATE) <= CAST(:ate AS date))

                AND (:q_is_null = 1 OR (
                COALESCE(titulo,'') ILIKE :like
                OR COALESCE(descricao,'') ILIKE :like
                OR payload::text ILIKE :like
                ))
            )
            SELECT
            (SELECT COUNT(*) FROM filtrado) AS total,
            COALESCE(jsonb_agg(to_jsonb(pagina)), '[]'::jsonb) AS items
            FROM (
            SELECT *
            FROM filtrado
            ORDER BY
                ev_inicio DESC,
                id_evento DESC
            LIMIT :limit OFFSET :offset
            ) pagina;
        """)

    params = {
        "militar_id": militar_id,
        "tem_tipos": 1 if tipos else 0,
        "tipos": tipos if tipos else ["__NONE__"],
        "de": de,       # agora é None ou 'YYYY-MM-DD'
        "ate": ate,     # idem
        "q_is_null": 0 if like else 1,
        "like": like or "",
        "limit": per_page,
        "offset": offset,
    }
    row = db.session.execute(sql, params).mappings().first()
    total = int(row["total"]) if row and row["total"] is not None else 0
    items = row["items"] if row else []

    return jsonify({
        "ok": True,
        "militar_id": militar_id,
        "page": page,
        "per_page": per_page,
        "total": total,
        "items": items
    })
