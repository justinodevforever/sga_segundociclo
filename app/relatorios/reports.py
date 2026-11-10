"""
Registo de relatórios tabulares. Cada função recebe os filtros (dict) e devolve
um `Relatorio`; as views geram HTML, PDF (xhtml2pdf) e Excel (openpyxl) a partir dele.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Q, Sum
from django.utils import timezone

from app.db.models import (AtribuicaoDocente, Aluno, AnoLectivo, Candidato, DocumentoAluno, Exame, Falta,
                        Funcionario, HistoricoNota, HorarioAula, Inscricao, LogAuditoria, Matricula,
                        PlanoCurricular, ProvaAptidaoProfissional, Reclamacao, RegraAvaliacao,
                        ResultadoAnual, ResultadoTrimestral, Trimestre, Turma, Utilizador)

from .utils import Relatorio, Tabela, limiar

G_SEC = "Secretaria e Matrículas"
G_AVA = "Avaliação e Aproveitamento"
G_ASS = "Assiduidade"
G_DOC = "Corpo Docente"
G_EST = "Estrutura Escolar"
G_SIS = "Gestão e Sistema"

REGISTO = {}


@dataclass
class Meta:
    slug: str
    titulo: str
    grupo: str
    icone: str
    descricao: str
    filtros: tuple
    obrigatorios: tuple
    excel: bool
    rotulos: dict
    fn: Any


def relatorio(slug, titulo, grupo, icone, descricao, filtros=(), obrigatorios=(), excel=True, rotulos=None):
    def deco(fn):
        REGISTO[slug] = Meta(slug, titulo, grupo, icone, descricao, tuple(filtros),
                             tuple(obrigatorios), excel, rotulos or {}, fn)
        return fn
    return deco


# ==========================================================================
# Helpers
# ==========================================================================
VALIDAS = [Matricula.Status.ACTIVA, Matricula.Status.CONCLUIDA]
TURNO_PERIODO = {"M": "manha", "T": "tarde", "N": "noite"}


def _mat(f, so_validas=True):
    qs = Matricula.objects.select_related("aluno", "ano_lectivo", "turma__curso", "turma__classe")
    if f.get("ano_lectivo"):
        qs = qs.filter(ano_lectivo=f["ano_lectivo"])
    if f.get("turma"):
        qs = qs.filter(turma=f["turma"])
    if f.get("curso"):
        qs = qs.filter(turma__curso=f["curso"])
    if f.get("classe"):
        qs = qs.filter(turma__classe=f["classe"])
    if f.get("turno"):
        qs = qs.filter(turma__periodo=f["turno"])
    if f.get("genero"):
        qs = qs.filter(aluno__genero=f["genero"])
    if f.get("situacao"):
        qs = qs.filter(situacao_final=f["situacao"])
    if f.get("status_matricula"):
        qs = qs.filter(status=f["status_matricula"])
    elif so_validas:
        qs = qs.filter(status__in=VALIDAS)
    return qs.order_by("turma__classe__designacao", "turma__designacao", "aluno__nome_completo")


def _t(t):
    return f"{t.classe.designacao}.ª {t.designacao}" if t else "-"


def _sub_turma(t):
    return f"Turma {_t(t)} | {t.curso.nome} | {t.get_periodo_display()} | Ano lectivo {t.ano_lectivo}"


def _cls(m):
    return f"{m.turma.classe.designacao}.ª Classe" if m.turma else "Sem turma"


def _cur(m):
    return m.turma.curso.nome if m.turma else "Sem turma"


def _trn(m):
    return m.turma.get_periodo_display() if m.turma else "Sem turma"


def _pct(a, b):
    return round(a * 100 / b, 1) if b else 0.0


def _n(v):
    return float(v) if v is not None else None


def _limiar(f):
    classe = f["turma"].classe if f.get("turma") else f.get("classe")
    if f.get("ano_lectivo") and classe:
        return float(limiar(f["ano_lectivo"], classe))
    return 10.0


def _quadro(titulo, col, pares):
    """pares = [(chave, genero)] -> tabela M / F / Total / %"""
    d = defaultdict(lambda: [0, 0, 0])
    for k, g in pares:
        d[k][0 if g == "M" else 1 if g == "F" else 2] += 1
    tot = sum(sum(v) for v in d.values())
    linhas = [[k, v[0], v[1], sum(v), _pct(sum(v), tot)] for k, v in sorted(d.items(), key=lambda x: str(x[0]))]
    rod = ["Total", sum(v[0] for v in d.values()), sum(v[1] for v in d.values()), tot, 100.0 if tot else 0.0]
    return Tabela(titulo, [col, "M", "F", "Total", "%"], linhas, rod)


def _res(m):
    S, Sit = Matricula.Status, Matricula.Situacao
    if m.status == S.TRANSFERIDA:
        return "T"
    if m.status == S.DESISTENTE:
        return "D"
    if m.status == S.CANCELADA:
        return "C"
    if m.situacao_final == Sit.APROVADO:
        return "A"
    if m.situacao_final == Sit.REPROVADO:
        return "R"
    if m.situacao_final == Sit.REPROVADO_FALTAS:
        return "F"
    return "E"


def _quadro_aprov(titulo, col, itens):
    """itens = [(chave, genero, res)]"""
    d = defaultdict(lambda: defaultdict(int))
    for k, g, r in itens:
        d[k]["mat"] += 1
        if r == "A":
            d[k]["A" + (g if g in ("M", "F") else "M")] += 1
        elif r in ("R", "F"):
            d[k]["R" + (g if g in ("M", "F") else "M")] += 1
        elif r in ("T", "D"):
            d[k]["TD"] += 1
    linhas = []
    for k, v in sorted(d.items(), key=lambda x: str(x[0])):
        a, r = v["AM"] + v["AF"], v["RM"] + v["RF"]
        linhas.append([k, v["mat"], v["AM"], v["AF"], a, v["RM"], v["RF"], r, v["TD"], _pct(a, a + r)])
    S = [sum(l[i] for l in linhas) for i in range(1, 9)]
    rod = ["Total"] + S + [_pct(S[3], S[3] + S[6])]
    cols = [col, "Matric.", "Aprov. M", "Aprov. F", "Aprov. Total", "Reprov. M", "Reprov. F",
            "Reprov. Total", "Transf./Desist.", "% Aprov."]
    return Tabela(titulo, cols, linhas, rod)


def _previstos(ano):
    """{(curso_id, classe_id): tempos lectivos previstos no ano} (soma da carga semanal x semanas)."""
    semanas = ano.semanas_lectivas if ano else 33
    return {(r["curso_id"], r["classe_id"]): (r["s"] or 0) * semanas
            for r in PlanoCurricular.objects.values("curso_id", "classe_id").annotate(s=Sum("carga_horaria_semanal"))}


# ==========================================================================
# SECRETARIA E MATRÍCULAS
# ==========================================================================
@relatorio("lista-alunos-turma", "Lista Nominal de Alunos por Turma", G_SEC, "bi-list-ol",
           "Lista oficial dos alunos de uma turma, com dados de identificação.",
           filtros=("ano_lectivo", "turma", "status_matricula"), obrigatorios=("turma",))
def r_lista_turma(f):
    t = f["turma"]
    ms = list(_mat(f))
    linhas = [[i, m.aluno.numero_processo or "-", m.aluno.nome_completo, m.aluno.genero or "-",
               m.aluno.data_nascimento, m.aluno.idade, m.aluno.bi, m.aluno.telefone or "-", m.get_status_display()]
              for i, m in enumerate(ms, 1)]
    M = sum(1 for m in ms if m.aluno.genero == "M")
    F = sum(1 for m in ms if m.aluno.genero == "F")
    cols = ["Nº", "Nº Processo", "Nome Completo", "Género", "Data Nasc.", "Idade", "B.I.", "Telefone", "Estado"]
    return Relatorio("Lista Nominal de Alunos", _sub_turma(t),
                     [Tabela("Alunos", cols, linhas, larguras=[4, 10, 30, 6, 11, 6, 14, 11, 8])],
                     [("Total de alunos", len(ms)), ("Masculino", M), ("Feminino", F),
                      ("Capacidade", t.capacidade_maxima)], assinaturas=True)


@relatorio("folha-presenca", "Folha de Presença (em branco)", G_SEC, "bi-check2-square",
           "Mapa de assiduidade mensal da turma, pronto a imprimir e preencher.",
           filtros=("ano_lectivo", "turma"), obrigatorios=("turma",))
def r_folha(f):
    t = f["turma"]
    ms = list(_mat(f))
    dias = 22
    cols = ["Nº", "Nome Completo"] + [str(i) for i in range(1, dias + 1)]
    larg = [3, 24] + [round(73 / dias, 1)] * dias
    linhas = [[i, m.aluno.nome_completo] + [""] * dias for i, m in enumerate(ms, 1)]
    return Relatorio("Folha de Presença", _sub_turma(t) + "  |  Mês: ____________  Disciplina: ____________________",
                     [Tabela("", cols, linhas, larguras=larg)], orientacao="landscape", assinaturas=True)


@relatorio("alunos-matriculados", "Relatório Geral de Matrículas", G_SEC, "bi-journal-check",
           "Todos os alunos matriculados no ano lectivo, filtrável por curso, classe, turno e estado.",
           filtros=("ano_lectivo", "curso", "classe", "turno", "genero", "status_matricula"))
def r_matriculados(f):
    ms = list(_mat(f))
    linhas = [[i, m.aluno.numero_processo or "-", m.aluno.nome_completo, m.aluno.genero or "-", _cur(m),
               f"{m.turma.classe.designacao}.ª" if m.turma else "-", _t(m.turma), _trn(m),
               m.get_tipo_matricula_display(), m.get_status_display(), m.data_matricula]
              for i, m in enumerate(ms, 1)]
    cols = ["Nº", "Nº Proc.", "Nome Completo", "Gén.", "Curso", "Classe", "Turma", "Turno", "Tipo", "Estado", "Data"]
    return Relatorio("Relatório Geral de Matrículas", "", [Tabela("Matrículas", cols, linhas)],
                     [("Total de matrículas", len(ms))])


@relatorio("estatistica-matriculas", "Mapa Estatístico de Matrículas", G_SEC, "bi-bar-chart-line",
           "Quadros por classe, curso, turno, tipo e estado da matrícula, com distribuição por género.",
           filtros=("ano_lectivo", "status_matricula"))
def r_est_mat(f):
    ms = list(_mat(f, so_validas=not f.get("status_matricula")))
    tabs = [
        _quadro("Por classe", "Classe", ((_cls(m), m.aluno.genero) for m in ms)),
        _quadro("Por curso", "Curso", ((_cur(m), m.aluno.genero) for m in ms)),
        _quadro("Por turno", "Turno", ((_trn(m), m.aluno.genero) for m in ms)),
        _quadro("Por tipo de matrícula", "Tipo", ((m.get_tipo_matricula_display(), m.aluno.genero) for m in ms)),
        _quadro("Por estado da matrícula", "Estado", ((m.get_status_display(), m.aluno.genero) for m in ms)),
    ]
    return Relatorio("Mapa Estatístico de Matrículas", "", tabs, [("Total", len(ms))], orientacao="portrait",
                     assinaturas=True)


@relatorio("ocupacao-turmas", "Mapa de Turmas e Ocupação", G_SEC, "bi-people-fill",
           "Capacidade, alunos matriculados, vagas livres e taxa de ocupação por turma.",
           filtros=("ano_lectivo", "curso", "classe", "turno"))
def r_ocupacao(f):
    qs = Turma.objects.select_related("curso", "classe", "ano_lectivo").annotate(
        n=Count("matriculas", filter=Q(matriculas__status__in=VALIDAS), distinct=True))
    if f.get("ano_lectivo"):
        qs = qs.filter(ano_lectivo=f["ano_lectivo"])
    if f.get("curso"):
        qs = qs.filter(curso=f["curso"])
    if f.get("classe"):
        qs = qs.filter(classe=f["classe"])
    if f.get("turno"):
        qs = qs.filter(periodo=f["turno"])
    ts = list(qs.order_by("classe__designacao", "designacao"))
    linhas, cap_t, n_t = [], 0, 0
    for t in ts:
        cap = t.capacidade_maxima or 0
        cap_t += cap
        n_t += t.n
        linhas.append([_t(t), t.curso.nome, t.get_periodo_display(), t.sala or "-", cap, t.n,
                       max(cap - t.n, 0), _pct(t.n, cap)])
    rod = ["Total", "", "", "", cap_t, n_t, max(cap_t - n_t, 0), _pct(n_t, cap_t)]
    cols = ["Turma", "Curso", "Turno", "Sala", "Capacidade", "Matriculados", "Vagas livres", "Ocupação %"]
    return Relatorio("Mapa de Turmas e Ocupação", "", [Tabela("Turmas", cols, linhas, rod)],
                     [("Turmas", len(ts)), ("Alunos", n_t), ("Ocupação global %", _pct(n_t, cap_t))])


@relatorio("inscricoes", "Relatório de Inscrições", G_SEC, "bi-clipboard-plus",
           "Candidatos inscritos por ano lectivo, curso e turno, com resumo por curso e estado.",
           filtros=("ano_lectivo", "curso", "turno"))
def r_inscricoes(f):
    qs = Inscricao.objects.select_related("candidato", "curso", "periodo")
    if f.get("ano_lectivo"):
        qs = qs.filter(ano_lectivo=f["ano_lectivo"])
    if f.get("curso"):
        qs = qs.filter(curso=f["curso"])
    if f.get("turno"):
        qs = qs.filter(periodo__designacao=TURNO_PERIODO[f["turno"]])
    ins = list(qs.order_by("candidato__nome_completo"))
    linhas = [[i, x.candidato.nome_completo, x.candidato.bi, x.candidato.genero, x.candidato.telefone or "-",
               x.curso.nome, x.periodo.get_designacao_display(), x.data_inscricao, x.get_status_display()]
              for i, x in enumerate(ins, 1)]
    cols = ["Nº", "Candidato", "B.I.", "Gén.", "Telefone", "Curso", "Período", "Data", "Estado"]
    d = defaultdict(lambda: [0, 0, 0])
    for x in ins:
        d[x.curso.nome][{"ativa": 0, "aprovada": 1, "reprovada": 2}.get(x.status, 0)] += 1
    res = [[k, v[0], v[1], v[2], sum(v)] for k, v in sorted(d.items())]
    rod = ["Total"] + [sum(r[i] for r in res) for i in range(1, 5)]
    return Relatorio("Relatório de Inscrições", "",
                     [Tabela("Inscrições", cols, linhas),
                      Tabela("Resumo por curso", ["Curso", "Activas", "Aprovadas", "Reprovadas", "Total"], res, rod)],
                     [("Total de inscrições", len(ins))])


@relatorio("movimento-alunos", "Movimento Escolar (Transferências, Desistências…)", G_SEC, "bi-arrow-left-right",
           "Alunos transferidos, desistentes, com matrícula cancelada ou trancada.",
           filtros=("ano_lectivo", "curso", "classe", "status_matricula", "data_inicio", "data_fim"))
def r_movimento(f):
    S = Matricula.Status
    qs = _mat(f, so_validas=False)
    if not f.get("status_matricula"):
        qs = qs.filter(status__in=[S.TRANSFERIDA, S.DESISTENTE, S.CANCELADA, S.TRANCAMENTO])
    if f.get("data_inicio"):
        qs = qs.filter(data_actualizacao__date__gte=f["data_inicio"])
    if f.get("data_fim"):
        qs = qs.filter(data_actualizacao__date__lte=f["data_fim"])
    ms = list(qs)
    linhas = [[i, m.aluno.nome_completo, m.aluno.genero or "-", _t(m.turma), _cur(m), m.get_status_display(),
               m.motivo_cancelamento or "-", m.data_actualizacao.date() if m.data_actualizacao else None]
              for i, m in enumerate(ms, 1)]
    cols = ["Nº", "Aluno", "Gén.", "Turma", "Curso", "Estado", "Motivo", "Data"]
    return Relatorio("Movimento Escolar", "", [Tabela("Movimentos", cols, linhas),
                                               _quadro("Resumo por estado", "Estado",
                                                       ((m.get_status_display(), m.aluno.genero) for m in ms))],
                     [("Total", len(ms))])


@relatorio("necessidades-especiais", "Alunos com Necessidades Especiais", G_SEC, "bi-universal-access",
           "Alunos matriculados com necessidades educativas especiais registadas.",
           filtros=("ano_lectivo", "curso", "classe", "turma"))
def r_nee(f):
    ms = list(_mat(f).exclude(aluno__necessidades_especiais=""))
    linhas = [[i, m.aluno.nome_completo, m.aluno.genero or "-", m.aluno.idade, _t(m.turma), _cur(m),
               m.aluno.necessidades_especiais] for i, m in enumerate(ms, 1)]
    cols = ["Nº", "Aluno", "Gén.", "Idade", "Turma", "Curso", "Necessidades especiais"]
    return Relatorio("Alunos com Necessidades Especiais", "", [Tabela("", cols, linhas)], [("Total", len(ms))])


@relatorio("bi-a-expirar", "Bilhetes de Identidade Expirados / a Expirar", G_SEC, "bi-person-vcard",
           "Alunos cujo B.I. já expirou ou expira nos próximos dias (por defeito 90).",
           filtros=("ano_lectivo", "curso", "classe", "turma", "limite"), rotulos={"limite": "Dias até expirar"})
def r_bi(f):
    dias = f.get("limite") or 90
    hoje = date.today()
    ms = list(_mat(f).filter(aluno__data_expiracao_bi__isnull=False,
                             aluno__data_expiracao_bi__lte=hoje + timedelta(days=dias))
              .order_by("aluno__data_expiracao_bi"))
    linhas = []
    for i, m in enumerate(ms, 1):
        a = m.aluno
        rest = (a.data_expiracao_bi - hoje).days
        linhas.append([i, a.nome_completo, _t(m.turma), a.bi, a.data_emissao_bi, a.data_expiracao_bi, rest,
                       "Expirado" if rest < 0 else "A expirar"])
    cols = ["Nº", "Aluno", "Turma", "B.I.", "Emissão", "Expiração", "Dias restantes", "Situação"]
    return Relatorio("B.I. Expirados / a Expirar", f"Horizonte: {dias} dias", [Tabela("", cols, linhas)],
                     [("Total", len(ms)), ("Já expirados", sum(1 for l in linhas if l[6] < 0))])


@relatorio("estatistica-demografica", "Estatística Demográfica dos Alunos", G_SEC, "bi-geo-alt",
           "Distribuição dos alunos por província, município, idade e género.",
           filtros=("ano_lectivo", "curso", "classe"))
def r_demografia(f):
    ms = list(_mat(f))
    tabs = [
        _quadro("Por província", "Província", ((m.aluno.provincia or "N/D", m.aluno.genero) for m in ms)),
        _quadro("Por município", "Município", ((m.aluno.municipio or "N/D", m.aluno.genero) for m in ms)),
        _quadro("Por idade", "Idade", ((f"{m.aluno.idade:02d} anos" if m.aluno.idade is not None else "N/D",
                                        m.aluno.genero) for m in ms)),
    ]
    return Relatorio("Estatística Demográfica", "", tabs, [("Alunos", len(ms))], assinaturas=True)


@relatorio("documentos-em-falta", "Controlo de Documentos dos Alunos", G_SEC, "bi-folder-check",
           "Verifica quais alunos têm B.I., certificado, fotografia e atestado médico arquivados.",
           filtros=("ano_lectivo", "curso", "classe", "turma"))
def r_docs(f):
    T = DocumentoAluno.TipoDocumento
    ms = list(_mat(f).prefetch_related("aluno__documentos"))
    linhas = []
    for m in ms:
        tipos = {d.tipo_documento for d in m.aluno.documentos.all()}
        bi, cert = T.BI in tipos, T.CERTIFICADO in tipos
        foto, atest = (T.FOTO in tipos) or bool(m.aluno.foto), T.ATESTADO in tipos
        ok = bi and cert and foto
        linhas.append([m.aluno.nome_completo, _t(m.turma), bi, cert, foto, atest, "Completo" if ok else "Em falta"])
    linhas.sort(key=lambda l: (l[6] == "Completo", l[0]))
    linhas = [[i] + l for i, l in enumerate(linhas, 1)]
    cols = ["Nº", "Aluno", "Turma", "B.I.", "Certificado", "Fotografia", "Atestado", "Situação"]
    return Relatorio("Controlo de Documentos dos Alunos", "", [Tabela("", cols, linhas)],
                     [("Alunos", len(ms)), ("Com documentos em falta", sum(1 for l in linhas if l[7] == "Em falta"))])


# ==========================================================================
# AVALIAÇÃO E APROVEITAMENTO
# ==========================================================================
@relatorio("pauta-trimestral-disciplina", "Pauta Trimestral por Disciplina", G_AVA, "bi-pencil-square",
           "MAC, Prova do Professor, Prova Trimestral e Média Trimestral de uma disciplina numa turma.",
           filtros=("ano_lectivo", "turma", "disciplina", "trimestre"),
           obrigatorios=("turma", "disciplina", "trimestre"))
def r_pauta_disc(f):
    t, d, n, lim = f["turma"], f["disciplina"], int(f["trimestre"]), _limiar(f)
    ms = list(_mat(f))
    res = {r.matricula_id: r for r in
           ResultadoTrimestral.objects.filter(matricula__in=ms, disciplina=d, trimestre__designacao=n)}
    linhas, mts = [], []
    for i, m in enumerate(ms, 1):
        r = res.get(m.id)
        mt = _n(r.mt) if r else None
        if mt is not None:
            mts.append(mt)
        obs = "-" if mt is None else ("Positiva" if mt >= lim else "Negativa")
        linhas.append([i, m.aluno.nome_completo, m.aluno.genero or "-", _n(r.mac) if r else None,
                       _n(r.pp) if r else None, _n(r.pt) if r else None, mt, obs])
    prof = AtribuicaoDocente.objects.filter(turma=t, disciplina=d).select_related("professor").first()
    pos = sum(1 for v in mts if v >= lim)
    cols = ["Nº", "Nome Completo", "Gén.", "MAC", "PP", "PT", "MT", "Observação"]
    return Relatorio(f"Pauta do {n}.º Trimestre - {d.nome}", _sub_turma(t),
                     [Tabela("", cols, linhas, notas_cols=(3, 4, 5, 6), nota_min=lim,
                             larguras=[4, 36, 6, 9, 9, 9, 9, 18])],
                     [("Professor", prof.professor.nome_completo if prof else "-"), ("Alunos", len(ms)),
                      ("Avaliados", len(mts)), ("Positivas", pos), ("Negativas", len(mts) - pos),
                      ("% Positivas", _pct(pos, len(mts))),
                      ("Média da turma", round(sum(mts) / len(mts), 2) if mts else None)], assinaturas=True)


def _matriz(f, anual):
    t, lim = f["turma"], _limiar(f)
    ms = list(_mat(f))
    discs = [p.disciplina for p in PlanoCurricular.objects.filter(curso=t.curso, classe=t.classe)
             .select_related("disciplina").order_by("disciplina__componente", "disciplina__nome")]
    if anual:
        mapa = {(r.matricula_id, r.disciplina_id): (r.nota_final if r.nota_final is not None else r.mfd)
                for r in ResultadoAnual.objects.filter(matricula__in=ms)}
    else:
        n = int(f["trimestre"])
        mapa = {(r.matricula_id, r.disciplina_id): r.mt
                for r in ResultadoTrimestral.objects.filter(matricula__in=ms, trimestre__designacao=n)}
    linhas = []
    for i, m in enumerate(ms, 1):
        notas = [mapa.get((m.id, d.id)) for d in discs]
        vals = [float(x) for x in notas if x is not None]
        neg = sum(1 for v in vals if v < lim)
        media = round(sum(vals) / len(vals), 2) if vals else None
        linhas.append([i, m.aluno.nome_completo] + [_n(x) for x in notas] + [neg, media] +
                      ([m.get_situacao_final_display()] if anual else []))
    nd = len(discs)
    cols = ["Nº", "Nome Completo"] + [d.nome_abreviado for d in discs] + ["Neg.", "Média"] + \
           (["Resultado"] if anual else [])
    fixa, resto = [3, 20], [4, 5] + ([12] if anual else [])
    w = round((100 - sum(fixa) - sum(resto)) / max(nd, 1), 1)
    leg = [[d.nome_abreviado, d.nome, d.get_componente_display()] for d in discs]
    tab = Tabela("Pauta", cols, linhas, notas_cols=tuple(range(2, nd + 2)) + (nd + 3,), nota_min=lim,
                 larguras=fixa + [w] * nd + resto)
    return t, ms, tab, Tabela("Legenda das disciplinas", ["Abreviatura", "Disciplina", "Componente"], leg)


@relatorio("pauta-trimestral-turma", "Pauta Trimestral da Turma", G_AVA, "bi-table",
           "Médias trimestrais de todas as disciplinas do plano curricular, por aluno.",
           filtros=("ano_lectivo", "turma", "trimestre"), obrigatorios=("turma", "trimestre"))
def r_pauta_trim(f):
    t, ms, tab, leg = _matriz(f, anual=False)
    return Relatorio(f"Pauta do {f['trimestre']}.º Trimestre", _sub_turma(t), [tab, leg],
                     [("Alunos", len(ms))], orientacao="landscape", assinaturas=True)


@relatorio("pauta-anual-turma", "Pauta Final / Mapa de Aproveitamento da Turma", G_AVA, "bi-award",
           "Nota final de cada disciplina, média, nº de negativas e resultado final do aluno.",
           filtros=("ano_lectivo", "turma"), obrigatorios=("turma",))
def r_pauta_anual(f):
    t, ms, tab, leg = _matriz(f, anual=True)
    c = defaultdict(int)
    for m in ms:
        c[m.situacao_final] += 1
    Sit = Matricula.Situacao
    return Relatorio("Pauta Final", _sub_turma(t), [tab, leg],
                     [("Alunos", len(ms)), ("Aprovados", c[Sit.APROVADO]),
                      ("Reprovados", c[Sit.REPROVADO] + c[Sit.REPROVADO_FALTAS]), ("Em curso", c[Sit.EM_CURSO])],
                     orientacao="landscape", assinaturas=True)


@relatorio("pauta-exames", "Pauta de Exames", G_AVA, "bi-mortarboard",
           "Notas de exame nacional, recurso e época especial.",
           filtros=("ano_lectivo", "curso", "classe", "turma", "disciplina"))
def r_exames(f):
    lim = _limiar(f)
    qs = Exame.objects.filter(matricula__in=_mat(f)).select_related(
        "matricula__aluno", "matricula__turma__classe", "disciplina")
    if f.get("disciplina"):
        qs = qs.filter(disciplina=f["disciplina"])
    ex = list(qs.order_by("disciplina__nome", "matricula__aluno__nome_completo"))
    linhas = [[i, e.matricula.aluno.nome_completo, _t(e.matricula.turma), e.disciplina.nome,
               e.get_tipo_display(), e.data, _n(e.nota),
               "-" if e.nota is None else ("Aprovado" if e.nota >= lim else "Reprovado")]
              for i, e in enumerate(ex, 1)]
    cols = ["Nº", "Aluno", "Turma", "Disciplina", "Tipo", "Data", "Nota", "Resultado"]
    notas = [l[6] for l in linhas if l[6] is not None]
    return Relatorio("Pauta de Exames", "", [Tabela("", cols, linhas, notas_cols=(6,), nota_min=lim)],
                     [("Exames", len(ex)), ("Aprovados", sum(1 for v in notas if v >= lim)),
                      ("Reprovados", sum(1 for v in notas if v < lim))], assinaturas=True)


@relatorio("aproveitamento-disciplina", "Aproveitamento por Disciplina", G_AVA, "bi-book",
           "Nº de positivas/negativas, percentagem de aproveitamento, média, máximo e mínimo por disciplina.",
           filtros=("ano_lectivo", "trimestre", "curso", "classe", "turma"))
def r_aprov_disc(f):
    lim, ms, tri = _limiar(f), _mat(f), f.get("trimestre")
    if tri:
        pares = list(ResultadoTrimestral.objects.filter(matricula__in=ms, trimestre__designacao=int(tri))
                     .values_list("disciplina__nome", "mt"))
    else:
        pares = [(d, nf if nf is not None else mfd) for d, nf, mfd in
                 ResultadoAnual.objects.filter(matricula__in=ms).values_list("disciplina__nome", "nota_final", "mfd")]
    notas = defaultdict(list)
    for d, v in pares:
        if v is not None:
            notas[d].append(float(v))
    linhas = []
    for d, v in sorted(notas.items()):
        p = sum(1 for x in v if x >= lim)
        linhas.append([d, len(v), p, len(v) - p, _pct(p, len(v)), round(sum(v) / len(v), 2), max(v), min(v)])
    T = [sum(l[i] for l in linhas) for i in (1, 2, 3)]
    rod = ["Total", T[0], T[1], T[2], _pct(T[1], T[0]), "", "", ""]
    cols = ["Disciplina", "Avaliados", "Positivas", "Negativas", "% Positivas", "Média", "Máx.", "Mín."]
    return Relatorio("Aproveitamento por Disciplina", f"{tri}.º Trimestre" if tri else "Nota final anual",
                     [Tabela("", cols, linhas, rod, notas_cols=(5,), nota_min=lim)],
                     [("Disciplinas", len(linhas)), ("% positivas global", _pct(T[1], T[0]))], assinaturas=True)


@relatorio("aproveitamento-turma", "Aproveitamento por Turma", G_AVA, "bi-graph-up",
           "Aprovados, reprovados, reprovados por faltas, transferidos e desistentes em cada turma.",
           filtros=("ano_lectivo", "curso", "classe", "turno"))
def r_aprov_turma(f):
    ms = [m for m in _mat(f, so_validas=False) if m.turma]
    d = defaultdict(lambda: defaultdict(int))
    info = {}
    for m in ms:
        d[m.turma_id][_res(m)] += 1
        d[m.turma_id]["n"] += 1
        info[m.turma_id] = m.turma
    linhas = []
    for tid, t in sorted(info.items(), key=lambda x: _t(x[1])):
        v = d[tid]
        linhas.append([_t(t), t.curso.nome, t.get_periodo_display(), v["n"], v["A"], v["R"], v["F"], v["E"],
                       v["T"], v["D"], _pct(v["A"], v["A"] + v["R"] + v["F"])])
    S = [sum(l[i] for l in linhas) for i in range(3, 10)]
    rod = ["Total", "", ""] + S + [_pct(S[1], S[1] + S[2] + S[3])]
    cols = ["Turma", "Curso", "Turno", "Matric.", "Aprov.", "Reprov.", "Rep. Faltas", "Em curso",
            "Transf.", "Desist.", "% Aprov."]
    return Relatorio("Aproveitamento por Turma", "", [Tabela("", cols, linhas, rod)], assinaturas=True)


@relatorio("estatistica-aproveitamento", "Estatística de Aproveitamento Escolar", G_AVA, "bi-pie-chart",
           "Quadro oficial de aprovados/reprovados por classe, curso e género (fim de ano).",
           filtros=("ano_lectivo", "curso", "classe"))
def r_est_aprov(f):
    ms = list(_mat(f, so_validas=False))
    it = lambda fn: [(fn(m), m.aluno.genero, _res(m)) for m in ms]
    return Relatorio("Estatística de Aproveitamento Escolar", "",
                     [_quadro_aprov("Por classe", "Classe", it(_cls)),
                      _quadro_aprov("Por curso", "Curso", it(_cur)),
                      _quadro_aprov("Por turno", "Turno", it(_trn))],
                     [("Matrículas", len(ms))], orientacao="landscape", assinaturas=True)


def _notas_mat(f, ms):
    d = defaultdict(list)
    if f.get("trimestre"):
        for mid, v in ResultadoTrimestral.objects.filter(
                matricula__in=ms, trimestre__designacao=int(f["trimestre"])).values_list("matricula_id", "mt"):
            if v is not None:
                d[mid].append(float(v))
    else:
        for mid, nf, mfd in ResultadoAnual.objects.filter(matricula__in=ms).values_list(
                "matricula_id", "nota_final", "mfd"):
            v = nf if nf is not None else mfd
            if v is not None:
                d[mid].append(float(v))
    return d


@relatorio("quadro-de-honra", "Quadro de Honra", G_AVA, "bi-trophy",
           "Melhores alunos (só com positivas a todas as disciplinas), por média.",
           filtros=("ano_lectivo", "curso", "classe", "turma", "trimestre", "limite"),
           rotulos={"limite": "Nº de alunos (def. 10)"})
def r_honra(f):
    lim, top = _limiar(f), f.get("limite") or 10
    ms = list(_mat(f))
    notas = _notas_mat(f, ms)
    cand = [(round(sum(notas[m.id]) / len(notas[m.id]), 2), m) for m in ms
            if notas.get(m.id) and min(notas[m.id]) >= lim]
    cand.sort(key=lambda x: (-x[0], x[1].aluno.nome_completo))
    linhas = [[i, m.aluno.nome_completo, _t(m.turma), _cur(m), len(notas[m.id]), media]
              for i, (media, m) in enumerate(cand[:top], 1)]
    cols = ["Pos.", "Aluno", "Turma", "Curso", "Nº disciplinas", "Média"]
    return Relatorio("Quadro de Honra", f"{f['trimestre']}.º Trimestre" if f.get("trimestre") else "Média final",
                     [Tabela("", cols, linhas)], assinaturas=True)


@relatorio("alunos-em-risco", "Alunos com Negativas (Risco de Reprovação)", G_AVA, "bi-exclamation-triangle",
           "Alunos com um mínimo de disciplinas negativas num trimestre, com a lista das disciplinas.",
           filtros=("ano_lectivo", "trimestre", "curso", "classe", "turma", "limite"),
           obrigatorios=("trimestre",), rotulos={"limite": "Mínimo de negativas (def. 3)"})
def r_risco(f):
    lim, minimo = _limiar(f), f.get("limite") or 3
    qs = ResultadoTrimestral.objects.filter(
        matricula__in=_mat(f), trimestre__designacao=int(f["trimestre"]), mt__lt=lim
    ).select_related("disciplina", "matricula__aluno", "matricula__turma__classe")
    d = defaultdict(list)
    for r in qs:
        d[r.matricula].append(r)
    linhas = [[m.aluno.nome_completo, _t(m.turma), len(rs),
               ", ".join(f"{r.disciplina.nome_abreviado} ({r.mt:.0f})" for r in sorted(rs, key=lambda x: x.disciplina.nome))]
              for m, rs in d.items() if len(rs) >= minimo]
    linhas.sort(key=lambda l: (-l[2], l[0]))
    linhas = [[i] + l for i, l in enumerate(linhas, 1)]
    cols = ["Nº", "Aluno", "Turma", "Nº negativas", "Disciplinas (nota)"]
    return Relatorio("Alunos com Negativas", f"{f['trimestre']}.º Trimestre | mínimo {minimo} negativas",
                     [Tabela("", cols, linhas, larguras=[4, 30, 9, 10, 47])], [("Alunos em risco", len(linhas))],
                     assinaturas=True)


@relatorio("lancamento-notas", "Estado do Lançamento de Notas", G_AVA, "bi-clipboard-data",
           "Por turma/disciplina/professor: quantos alunos já têm PP e PT lançadas no trimestre.",
           filtros=("ano_lectivo", "trimestre", "curso", "classe", "turma", "disciplina", "professor"),
           obrigatorios=("ano_lectivo", "trimestre"))
def r_lancamento(f):
    ano, n = f["ano_lectivo"], int(f["trimestre"])
    qs = AtribuicaoDocente.objects.filter(turma__ano_lectivo=ano).select_related(
        "professor", "turma__classe", "turma__curso", "disciplina")
    for campo, lookup in (("turma", "turma"), ("curso", "turma__curso"), ("classe", "turma__classe"),
                          ("disciplina", "disciplina"), ("professor", "professor")):
        if f.get(campo):
            qs = qs.filter(**{lookup: f[campo]})
    tam = dict(Matricula.objects.filter(ano_lectivo=ano, status__in=VALIDAS).values("turma_id")
               .annotate(c=Count("id")).values_list("turma_id", "c"))
    lanc = {(r["matricula__turma_id"], r["disciplina_id"]): r["c"] for r in
            ResultadoTrimestral.objects.filter(matricula__ano_lectivo=ano, trimestre__designacao=n,
                                               pp__isnull=False, pt__isnull=False)
            .values("matricula__turma_id", "disciplina_id").annotate(c=Count("id"))}
    linhas = []
    for a in qs.order_by("turma__classe__designacao", "turma__designacao", "disciplina__nome"):
        tot, ok = tam.get(a.turma_id, 0), lanc.get((a.turma_id, a.disciplina_id), 0)
        estado = "Completo" if tot and ok >= tot else "Parcial" if ok else "Não iniciado"
        linhas.append([_t(a.turma), a.disciplina.nome, a.professor.nome_completo, tot, ok, max(tot - ok, 0),
                       _pct(ok, tot), estado])
    tr = Trimestre.objects.filter(ano_lectivo=ano, designacao=n).first()
    cols = ["Turma", "Disciplina", "Professor", "Alunos", "Lançados", "Em falta", "% Lançado", "Estado"]
    return Relatorio("Estado do Lançamento de Notas", f"{n}.º Trimestre | {ano}", [Tabela("", cols, linhas)],
                     [("Lançamento aberto", tr.lancamento_aberto if tr else None),
                      ("Completos", sum(1 for l in linhas if l[7] == "Completo")),
                      ("Não iniciados", sum(1 for l in linhas if l[7] == "Não iniciado"))])


@relatorio("reclamacoes", "Reclamações de Notas", G_AVA, "bi-chat-left-text",
           "Pedidos de revisão de nota, estado da decisão e notas original/revista.",
           filtros=("ano_lectivo", "trimestre", "curso", "classe", "turma", "disciplina"))
def r_reclamacoes(f):
    qs = Reclamacao.objects.filter(matricula__in=_mat(f, so_validas=False)).select_related(
        "matricula__aluno", "matricula__turma__classe", "disciplina", "trimestre", "decidida_por")
    if f.get("disciplina"):
        qs = qs.filter(disciplina=f["disciplina"])
    if f.get("trimestre"):
        qs = qs.filter(trimestre__designacao=int(f["trimestre"]))
    rs = list(qs.order_by("-criada_em"))
    linhas = [[r.criada_em, r.matricula.aluno.nome_completo, _t(r.matricula.turma), r.disciplina.nome,
               f"{r.trimestre.designacao}.º" if r.trimestre else "-", _n(r.nota_original), _n(r.nota_revista),
               r.get_estado_display(), r.decidida_por.nome_completo if r.decidida_por else "-"] for r in rs]
    cols = ["Data", "Aluno", "Turma", "Disciplina", "Trim.", "Nota orig.", "Nota rev.", "Estado", "Decidida por"]
    c = defaultdict(int)
    for r in rs:
        c[r.estado] += 1
    return Relatorio("Reclamações de Notas", "", [Tabela("", cols, linhas)],
                     [("Total", len(rs)), ("Pendentes", c["PEND"]), ("Deferidas", c["DEF"]),
                      ("Indeferidas", c["INDEF"])])


@relatorio("historico-notas", "Auditoria de Alterações de Notas", G_AVA, "bi-clock-history",
           "Registo de quem alterou notas, valor anterior/novo e motivo (por defeito, últimos 30 dias).",
           filtros=("data_inicio", "data_fim", "limite"), rotulos={"limite": "Máx. registos (def. 1000)"})
def r_hist_notas(f):
    di = f.get("data_inicio") or (date.today() - timedelta(days=30))
    df = f.get("data_fim") or date.today()
    qs = HistoricoNota.objects.filter(data__date__gte=di, data__date__lte=df).select_related("utilizador")
    hs = list(qs.order_by("-data")[: f.get("limite") or 1000])
    linhas = [[h.data, h.utilizador.nome_completo or h.utilizador.username if h.utilizador else "-", h.modelo,
               h.objecto_id, h.campo, h.valor_anterior or "-", h.valor_novo or "-", h.motivo or "-"] for h in hs]
    cols = ["Data/Hora", "Utilizador", "Modelo", "ID", "Campo", "Anterior", "Novo", "Motivo"]
    return Relatorio("Auditoria de Alterações de Notas", f"Período: {di:%d/%m/%Y} a {df:%d/%m/%Y}",
                     [Tabela("", cols, linhas)], [("Registos", len(hs))])


@relatorio("pap-estagio", "Provas de Aptidão Profissional e Estágio", G_AVA, "bi-tools",
           "Notas de estágio e PAP dos alunos de cursos técnicos (classe terminal).",
           filtros=("ano_lectivo", "curso", "classe", "turma"))
def r_pap(f):
    ps = list(ProvaAptidaoProfissional.objects.filter(matricula__in=_mat(f)).select_related(
        "matricula__aluno", "matricula__turma__curso", "matricula__turma__classe")
        .order_by("matricula__aluno__nome_completo"))
    linhas = []
    for i, p in enumerate(ps, 1):
        m, e, n = p.matricula, _n(p.nota_estagio), _n(p.nota_pap)
        res = "Pendente" if e is None or n is None else ("Aprovado" if e >= 10 and n >= 10 else "Reprovado")
        linhas.append([i, m.aluno.nome_completo, _t(m.turma), _cur(m), p.tema or "-", e, n, res])
    cols = ["Nº", "Aluno", "Turma", "Curso", "Tema da PAP", "Estágio", "PAP", "Resultado"]
    return Relatorio("Provas de Aptidão Profissional e Estágio", "",
                     [Tabela("", cols, linhas, notas_cols=(5, 6))], [("Alunos", len(ps))], assinaturas=True)


# ==========================================================================
# ASSIDUIDADE
# ==========================================================================
@relatorio("faltas-resumo", "Resumo de Faltas por Aluno", G_ASS, "bi-calendar-x",
           "Faltas justificadas e injustificadas por aluno (ano, trimestre ou intervalo de datas).",
           filtros=("ano_lectivo", "turma", "curso", "classe", "trimestre", "data_inicio", "data_fim"))
def r_faltas(f):
    ms = list(_mat(f))
    qs = Falta.objects.filter(matricula__in=ms)
    filtrado = False
    tr = (Trimestre.objects.filter(ano_lectivo=f["ano_lectivo"], designacao=int(f["trimestre"])).first()
          if f.get("trimestre") and f.get("ano_lectivo") else None)
    di, df = f.get("data_inicio") or (tr.data_inicio if tr else None), f.get("data_fim") or (tr.data_fim if tr else None)
    if di:
        qs, filtrado = qs.filter(data__gte=di), True
    if df:
        qs, filtrado = qs.filter(data__lte=df), True
    agg = {r["matricula_id"]: r for r in qs.values("matricula_id").annotate(
        j=Sum("tempos", filter=Q(justificada=True)), i=Sum("tempos", filter=Q(justificada=False)))}
    prev = _previstos(f.get("ano_lectivo"))
    linhas = []
    for k, m in enumerate(ms, 1):
        a = agg.get(m.id, {})
        j, i = a.get("j") or 0, a.get("i") or 0
        p = prev.get((m.turma.curso_id, m.turma.classe_id), 0) if m.turma else 0
        linhas.append([k, m.aluno.nome_completo, _t(m.turma), j, i, j + i,
                       None if filtrado or not p else _pct(i, p)])
    cols = ["Nº", "Aluno", "Turma", "Just.", "Injust.", "Total", "% injust. s/ previstos"]
    return Relatorio("Resumo de Faltas por Aluno", "Valores em tempos lectivos", [Tabela("", cols, linhas)],
                     [("Alunos", len(ms)), ("Total de faltas", sum(l[5] for l in linhas))], assinaturas=True)


@relatorio("assiduidade-risco", "Alunos em Risco de Reprovação por Faltas", G_ASS, "bi-person-x",
           "Alunos cuja % de faltas injustificadas, por disciplina, se aproxima ou excede o limite da RegraAvaliacao.",
           filtros=("ano_lectivo", "turma", "curso", "classe", "limite"),
           obrigatorios=("ano_lectivo",), rotulos={"limite": "% mínima a listar (def. 70% do limite)"})
def r_risco_faltas(f):
    ano = f["ano_lectivo"]
    ms = {m.id: m for m in _mat(f)}
    regras = {r.classe_id: float(r.limite_faltas_injustificadas_pct) for r in RegraAvaliacao.objects.filter(ano_lectivo=ano)}
    carga = {(p.curso_id, p.classe_id, p.disciplina_id): p.carga_horaria_semanal
             for p in PlanoCurricular.objects.all()}
    linhas = []
    for r in (Falta.objects.filter(matricula__in=ms.keys(), justificada=False)
              .values("matricula_id", "disciplina_id", "disciplina__nome").annotate(t=Sum("tempos"))):
        m = ms[r["matricula_id"]]
        c = carga.get((m.turma.curso_id, m.turma.classe_id, r["disciplina_id"]))
        if not c:
            continue
        prev, legal = c * ano.semanas_lectivas, regras.get(m.turma.classe_id, 30.0)
        pct = _pct(r["t"], prev)
        if pct >= (f.get("limite") or 0.7 * legal):
            linhas.append([m.aluno.nome_completo, _t(m.turma), r["disciplina__nome"], r["t"], prev, pct, legal,
                           "Reprovado por faltas" if pct > legal else "Em risco"])
    linhas.sort(key=lambda l: -l[5])
    linhas = [[i] + l for i, l in enumerate(linhas, 1)]
    cols = ["Nº", "Aluno", "Turma", "Disciplina", "Faltas injust.", "Tempos previstos", "%", "Limite %", "Situação"]
    return Relatorio("Alunos em Risco por Faltas", f"Ano lectivo {ano}", [Tabela("", cols, linhas)],
                     [("Casos", len(linhas)), ("Acima do limite", sum(1 for l in linhas if l[8] != "Em risco"))],
                     assinaturas=True)


# ==========================================================================
# CORPO DOCENTE
# ==========================================================================
@relatorio("lista-funcionarios", "Lista de Funcionários", G_DOC, "bi-person-workspace",
           "Professores e pessoal administrativo com contrato, habilitações e estado.",
           filtros=("tipo_funcionario", "status_funcionario"))
def r_func(f):
    qs = Funcionario.objects.all()
    if f.get("tipo_funcionario"):
        qs = qs.filter(tipo_funcionario=f["tipo_funcionario"])
    if f.get("status_funcionario"):
        qs = qs.filter(status=f["status_funcionario"])
    fs = list(qs.order_by("nome_completo"))
    linhas = [[i, x.numero_agente or "-", x.nome_completo, x.genero or "-", x.bi, x.tipo_funcionario or "-",
               x.tipo_contrato or "-", x.get_nivel_academico_display(), x.especialidade or "-",
               x.carga_horaria_semanal, x.get_status_display()] for i, x in enumerate(fs, 1)]
    cols = ["Nº", "Nº Agente", "Nome", "Gén.", "B.I.", "Tipo", "Contrato", "Habilitações", "Especialidade",
            "Carga hor.", "Estado"]
    return Relatorio("Lista de Funcionários", "", [Tabela("", cols, linhas)], [("Total", len(fs))], assinaturas=True)


@relatorio("atribuicao-docente", "Distribuição de Serviço Docente", G_DOC, "bi-diagram-2",
           "Professor, disciplina e turma atribuídos no ano lectivo.",
           filtros=("ano_lectivo", "professor", "curso", "classe", "turma", "disciplina"))
def r_atrib(f):
    qs = AtribuicaoDocente.objects.select_related("professor", "turma__classe", "turma__curso", "disciplina")
    if f.get("ano_lectivo"):
        qs = qs.filter(turma__ano_lectivo=f["ano_lectivo"])
    for campo, lookup in (("professor", "professor"), ("curso", "turma__curso"), ("classe", "turma__classe"),
                          ("turma", "turma"), ("disciplina", "disciplina")):
        if f.get(campo):
            qs = qs.filter(**{lookup: f[campo]})
    at = list(qs.order_by("professor__nome_completo", "turma__classe__designacao", "turma__designacao"))
    linhas = [[a.professor.nome_completo, a.disciplina.nome, _t(a.turma), a.turma.curso.nome,
               a.turma.get_periodo_display()] for a in at]
    return Relatorio("Distribuição de Serviço Docente", "",
                     [Tabela("", ["Professor", "Disciplina", "Turma", "Curso", "Turno"], linhas)],
                     [("Atribuições", len(at))], assinaturas=True)


@relatorio("carga-horaria-docentes", "Carga Horária dos Docentes", G_DOC, "bi-clock",
           "Turmas, disciplinas, aulas e horas semanais por professor (a partir do horário).",
           filtros=("ano_lectivo", "status_funcionario"), obrigatorios=("ano_lectivo",))
def r_carga(f):
    ano = f["ano_lectivo"]
    profs = Funcionario.objects.filter(tipo_funcionario=Funcionario.TipoFuncionario.PROFESSOR)
    profs = profs.filter(status=f.get("status_funcionario") or Funcionario.Status.ACTIVO).order_by("nome_completo")
    aulas, mins = defaultdict(int), defaultdict(int)
    for h in HorarioAula.objects.filter(turma__ano_lectivo=ano):
        aulas[h.professor_id] += 1
        mins[h.professor_id] += (h.hora_fim.hour * 60 + h.hora_fim.minute) - (h.hora_inicio.hour * 60 + h.hora_inicio.minute)
    at = {r["professor_id"]: r for r in AtribuicaoDocente.objects.filter(turma__ano_lectivo=ano)
          .values("professor_id").annotate(t=Count("turma_id", distinct=True), d=Count("disciplina_id", distinct=True))}
    linhas = [[p.nome_completo, p.numero_agente or "-", p.tipo_contrato or "-", at.get(p.id, {}).get("t", 0),
               at.get(p.id, {}).get("d", 0), aulas[p.id], round(mins[p.id] / 60, 2), p.carga_horaria_semanal]
              for p in profs]
    cols = ["Professor", "Nº Agente", "Contrato", "Turmas", "Disciplinas", "Aulas/sem.", "Horas/sem.", "Carga contratada"]
    return Relatorio("Carga Horária dos Docentes", f"Ano lectivo {ano}", [Tabela("", cols, linhas)],
                     [("Professores", len(linhas))], assinaturas=True)


@relatorio("estatistica-docentes", "Estatística do Corpo Docente", G_DOC, "bi-bar-chart",
           "Funcionários por habilitações, contrato, tipo e estado, com distribuição por género.",
           filtros=("status_funcionario",))
def r_est_doc(f):
    qs = Funcionario.objects.all()
    if f.get("status_funcionario"):
        qs = qs.filter(status=f["status_funcionario"])
    fs = list(qs)
    return Relatorio("Estatística do Corpo Docente", "", [
        _quadro("Por habilitações", "Nível", ((x.get_nivel_academico_display(), x.genero) for x in fs)),
        _quadro("Por tipo de contrato", "Contrato", ((x.tipo_contrato or "N/D", x.genero) for x in fs)),
        _quadro("Por tipo de funcionário", "Tipo", ((x.tipo_funcionario or "N/D", x.genero) for x in fs)),
        _quadro("Por estado", "Estado", ((x.get_status_display(), x.genero) for x in fs)),
    ], [("Total", len(fs))], assinaturas=True)


# ==========================================================================
# ESTRUTURA ESCOLAR / GESTÃO
# ==========================================================================
@relatorio("plano-curricular", "Plano Curricular do Curso", G_EST, "bi-journal-bookmark",
           "Disciplinas, componente, tempos lectivos semanais e exame nacional por classe.",
           filtros=("curso", "classe"), obrigatorios=("curso",))
def r_plano(f):
    qs = PlanoCurricular.objects.filter(curso=f["curso"]).select_related("disciplina", "classe")
    if f.get("classe"):
        qs = qs.filter(classe=f["classe"])
    g = defaultdict(list)
    for p in qs.order_by("classe__designacao", "disciplina__componente", "disciplina__nome"):
        g[p.classe].append(p)
    tabs = []
    for classe, ps in g.items():
        linhas = [[p.disciplina.nome, p.disciplina.get_componente_display(),
                   p.carga_horaria_semanal, p.tem_exame_nacional] for p in ps]
        rod = ["Total", "", "", sum(p.carga_horaria_semanal for p in ps), ""]
        tabs.append(Tabela(f"{classe.designacao}.ª Classe", ["Disciplina", "Código", "Componente",
                                                              "Tempos/semana", "Exame Nacional"], linhas, rod))
    c = f["curso"]
    return Relatorio("Plano Curricular", f"{c.nome} | {c.get_tipo_display()} | {c.duracao_anos or '-'} anos",
                     tabs, [("Exige PAP", c.exige_pap), ("Exige estágio", c.exige_estagio)], orientacao="portrait")


@relatorio("utilizadores-roles", "Utilizadores e Perfis de Acesso", G_SIS, "bi-shield-lock",
           "Contas do sistema, perfis atribuídos, verificação e último acesso.")
def r_utilizadores(f):
    us = list(Utilizador.objects.prefetch_related("usuario_roles__role").order_by("nome_completo"))
    linhas = [[u.nome_completo or "-", u.username, u.email or "-",
               ", ".join(ur.role.get_nome_display() for ur in u.usuario_roles.all()) or "-",
               u.is_active, u.verificado_email, u.verificado_telefone, u.last_login, u.data_criacao.date()]
              for u in us]
    cols = ["Nome", "Utilizador", "E-mail", "Perfis", "Activo", "E-mail verif.", "Tel. verif.", "Último acesso", "Criado em"]
    return Relatorio("Utilizadores e Perfis de Acesso", "", [Tabela("", cols, linhas)],
                     [("Contas", len(us)), ("Activas", sum(1 for u in us if u.is_active))], assinaturas=True)


@relatorio("log-auditoria", "Log de Auditoria do Sistema", G_SIS, "bi-journal-text",
           "Acções registadas no sistema (login, criação, exportação, impressão…). Por defeito, últimos 30 dias.",
           filtros=("data_inicio", "data_fim", "limite"), rotulos={"limite": "Máx. registos (def. 500)"})
def r_log(f):
    di = f.get("data_inicio") or (date.today() - timedelta(days=30))
    df = f.get("data_fim") or date.today()
    ls = list(LogAuditoria.objects.filter(timestamp__date__gte=di, timestamp__date__lte=df)
              .select_related("utilizador").order_by("-timestamp")[: f.get("limite") or 500])
    linhas = [[l.timestamp, (l.utilizador.nome_completo or l.utilizador.username) if l.utilizador else "-",
               l.get_accao_display(), l.get_modulo_display(), l.descricao, l.ip_address] for l in ls]
    cols = ["Data/Hora", "Utilizador", "Acção", "Módulo", "Descrição", "IP"]
    return Relatorio("Log de Auditoria", f"Período: {di:%d/%m/%Y} a {df:%d/%m/%Y}",
                     [Tabela("", cols, linhas, larguras=[13, 18, 9, 11, 39, 10])], [("Registos", len(ls))])


@relatorio("relatorio-executivo", "Relatório Executivo do Ano Lectivo", G_SIS, "bi-speedometer2",
           "Indicadores-chave para a direcção: matrículas, turmas, docentes, aproveitamento, faltas e reclamações.",
           filtros=("ano_lectivo",), obrigatorios=("ano_lectivo",))
def r_executivo(f):
    ano = f["ano_lectivo"]
    ms = list(_mat({"ano_lectivo": ano}, so_validas=False))
    c = defaultdict(int)
    for m in ms:
        c[_res(m)] += 1
    activas = sum(1 for m in ms if m.status == Matricula.Status.ACTIVA)
    nturmas = Turma.objects.filter(ano_lectivo=ano, activo=True).count()
    prof = Funcionario.objects.filter(status=Funcionario.Status.ACTIVO,
                                      tipo_funcionario=Funcionario.TipoFuncionario.PROFESSOR).count()
    faltas = Falta.objects.filter(matricula__ano_lectivo=ano, justificada=False).aggregate(s=Sum("tempos"))["s"] or 0
    recl = Reclamacao.objects.filter(matricula__ano_lectivo=ano, estado="PEND").count()
    kpi = [
        ["Matrículas (total no ano)", len(ms)], ["Matrículas activas", activas], ["Turmas activas", nturmas],
        ["Média de alunos por turma", round(activas / nturmas, 1) if nturmas else 0],
        ["Professores activos", prof],
        ["Rácio aluno/professor", round(activas / prof, 1) if prof else 0],
        ["Inscrições no ano", Inscricao.objects.filter(ano_lectivo=ano).count()],
        ["Aprovados", c["A"]], ["Reprovados (inclui faltas)", c["R"] + c["F"]],
        ["Taxa de aprovação %", _pct(c["A"], c["A"] + c["R"] + c["F"])],
        ["Transferidos", c["T"]], ["Desistentes", c["D"]],
        ["Faltas injustificadas (tempos)", faltas], ["Reclamações pendentes", recl],
    ]
    return Relatorio("Relatório Executivo", f"Ano lectivo {ano}",
                     [Tabela("Indicadores", ["Indicador", "Valor"], kpi, larguras=[70, 30]),
                      _quadro_aprov("Aproveitamento por classe", "Classe",
                                    [(_cls(m), m.aluno.genero, _res(m)) for m in ms])],
                     orientacao="landscape", assinaturas=True)