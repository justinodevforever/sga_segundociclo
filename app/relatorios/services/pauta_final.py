"""
Pauta final por turma: notas por disciplina, Apto / Não Apto dinâmico,
exame de recurso e transição de classe (II Ciclo do Ensino Secundário, Angola).

Tudo é calculado em tempo real a partir de ResultadoAnual, Exame, Falta,
PlanoCurricular e RegraAvaliacao (nada de situação gravada à mão).

PARÂMETROS vindos de RegraAvaliacao (por ano lectivo + classe):
  - nota_minima_positiva (10), nota_minima_exame (10)
  - peso_exame_na_nota_final  -> NF = MFD*(1-peso) + Exame*peso
  - max_negativas_transicao   -> máx. de disciplinas negativas admitidas a recurso
  - classe_exame_exige_todas_positivas
  - limite_faltas_injustificadas_pct
  - arredondar_unidades
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from app.db.models import (
    Exame, Falta, Matricula, PlanoCurricular, ProvaAptidaoProfissional,
    RegraAvaliacao, ResultadoAnual,
)

# --- códigos de situação da disciplina ------------------------------------
APTO = "APTO"
NAO_APTO = "NAO_APTO"
AGUARDAR_EXAME = "AGUARDAR_EXAME"
PENDENTE = "PENDENTE"

# --- códigos de situação final do aluno -----------------------------------
TRANSITA = "TRANSITA"
CONCLUIU = "CONCLUIU"
APROVADO = "APROVADO"
ADMITIDO_EXAME = "ADMITIDO_EXAME"
ADMITIDO_RECURSO = "ADMITIDO_RECURSO"
NAO_TRANSITA = "NAO_TRANSITA"
REPROVADO = "REPROVADO"
REPROVADO_FALTAS = "REPROVADO_FALTAS"
SEM_NOTAS = "SEM_NOTAS"
OUTRA = "OUTRA"  # transferido, desistente, cancelado...

ROTULOS = {
    APTO: "Apto", NAO_APTO: "N/Apto", AGUARDAR_EXAME: "Aguarda Exame", PENDENTE: "—",
    TRANSITA: "Transita", CONCLUIU: "Concluiu", APROVADO: "Aprovado",
    ADMITIDO_EXAME: "Admitido a Exame", ADMITIDO_RECURSO: "Admitido a Recurso",
    NAO_TRANSITA: "Não Transita", REPROVADO: "Reprovado",
    REPROVADO_FALTAS: "Reprovado por Faltas", SEM_NOTAS: "Sem notas",
}


@dataclass
class LinhaDisciplina:
    disciplina: object
    mt1: Decimal = None
    mt2: Decimal = None
    mt3: Decimal = None
    mfd: Decimal = None
    tem_exame: bool = False
    nota_exame: Decimal = None
    nota_recurso: Decimal = None
    nota_final: Decimal = None
    situacao: str = PENDENTE
    via_recurso: bool = False

    @property
    def rotulo(self):
        return ROTULOS[self.situacao]


@dataclass
class ResultadoAluno:
    matricula: object
    linhas: list = field(default_factory=list)       # alinhadas com as disciplinas da turma
    negativas: list = field(default_factory=list)    # nomes das disciplinas N/Apto
    para_recurso: list = field(default_factory=list)
    faltas_pct: Decimal = Decimal("0")
    situacao: str = PENDENTE
    media_geral: Decimal = None
    estado_texto: str = ""

    @property
    def rotulo(self):
        if self.situacao == OUTRA:
            return self.estado_texto
        return ROTULOS.get(self.situacao, self.situacao)

    @property
    def positivo(self):
        return self.situacao in (TRANSITA, CONCLUIU, APROVADO)


# --------------------------------------------------------------------------
def _arred(valor, regra):
    if valor is None:
        return None
    if regra.arredondar_unidades:
        return valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def regra_da_turma(turma):
    regra = RegraAvaliacao.objects.filter(
        ano_lectivo=turma.ano_lectivo, classe=turma.classe).first()
    return regra or RegraAvaliacao(ano_lectivo=turma.ano_lectivo, classe=turma.classe)


def classe_terminal(turma):
    """10.ª + duração do curso - 1  (3 anos -> 12.ª; 4 anos -> 13.ª)."""
    duracao = turma.curso.duracao_anos or 3
    return 10 + duracao - 1


def pauta_publicada(ano_lectivo):
    """A pauta só é pública quando o 3.º trimestre está fechado para lançamento."""
    t3 = ano_lectivo.trimestres.filter(designacao=3).first()
    return bool(t3 and not t3.lancamento_aberto)


# --------------------------------------------------------------------------
def _avaliar_disciplina(plano, ra, recurso, regra):
    minimo = regra.nota_minima_positiva
    min_exame = regra.nota_minima_exame
    peso = Decimal(str(regra.peso_exame_na_nota_final))

    l = LinhaDisciplina(disciplina=plano.disciplina, tem_exame=plano.tem_exame_nacional)
    if ra is None:
        return l
    l.mt1, l.mt2, l.mt3 = ra.mt1, ra.mt2, ra.mt3

    # MFD dinâmica: usa a gravada; senão média das MT lançadas
    mts = [m for m in (ra.mt1, ra.mt2, ra.mt3) if m is not None]
    l.mfd = ra.mfd if ra.mfd is not None else (
        _arred(sum(mts) / len(mts), regra) if len(mts) == 3 else None)
    if l.mfd is None:
        return l

    l.nota_exame = ra.nota_exame
    l.nota_recurso = recurso

    def nf_com(exame):
        return _arred(l.mfd * (1 - peso) + exame * peso, regra)

    if not l.tem_exame:
        # disciplina sem exame: MFD decide; recurso substitui a nota
        l.nota_final = l.mfd
        l.situacao = APTO if l.mfd >= minimo else NAO_APTO
        if l.situacao == NAO_APTO and recurso is not None:
            l.via_recurso = True
            l.nota_final = recurso
            l.situacao = APTO if recurso >= minimo else NAO_APTO
        return l

    # disciplina com exame nacional
    exame = l.nota_exame
    if exame is None and recurso is None:
        l.nota_final = None
        l.situacao = NAO_APTO if l.mfd < minimo else AGUARDAR_EXAME
        return l
    if recurso is not None:
        l.via_recurso = True
        exame = recurso
    l.nota_final = nf_com(exame)
    l.situacao = APTO if (l.nota_final >= minimo and exame >= min_exame) else NAO_APTO
    return l


def _decidir_aluno(res, regra, turma, tem_exame_classe, pap_ok, estado_matricula):
    linhas = res.linhas
    negativas = [l for l in linhas if l.situacao == NAO_APTO]
    res.negativas = [l.disciplina.nome for l in negativas]
    terminal = int(turma.classe.designacao) >= classe_terminal(turma)

    if estado_matricula is not None:
        res.situacao = OUTRA
        res.estado_texto = estado_matricula
        return
    if not linhas or all(l.situacao == PENDENTE for l in linhas):
        res.situacao = SEM_NOTAS
        return
    if any(l.situacao == PENDENTE for l in linhas):
        res.situacao = PENDENTE
        return
    if res.faltas_pct > regra.limite_faltas_injustificadas_pct:
        res.situacao = REPROVADO_FALTAS
        return

    aguardam = [l for l in linhas if l.situacao == AGUARDAR_EXAME]
    ja_recurso = any(l.via_recurso for l in negativas)
    pode_recurso = (
        negativas
        and len(negativas) <= regra.max_negativas_transicao
        and not ja_recurso
    )
    res.para_recurso = [l.disciplina.nome for l in negativas] if pode_recurso else []

    # 1) ainda há exames por realizar
    if aguardam:
        if negativas and regra.classe_exame_exige_todas_positivas:
            res.situacao = ADMITIDO_RECURSO if pode_recurso else REPROVADO
        else:
            res.situacao = ADMITIDO_EXAME
        return

    # 2) tudo positivo
    if not negativas:
        if terminal and not pap_ok:
            res.situacao = REPROVADO          # falta PAP/estágio positivos
        elif terminal:
            res.situacao = CONCLUIU
        elif tem_exame_classe:
            res.situacao = APROVADO
        else:
            res.situacao = TRANSITA
        return

    # 3) com negativas
    if pode_recurso:
        res.situacao = ADMITIDO_RECURSO
    else:
        res.situacao = REPROVADO if (terminal or tem_exame_classe) else NAO_TRANSITA


# --------------------------------------------------------------------------
def gerar_pauta(turma):
    """Devolve (disciplinas, resultados[ResultadoAluno], regra)."""
    regra = regra_da_turma(turma)
    planos = list(
        PlanoCurricular.objects.filter(curso=turma.curso, classe=turma.classe)
        .select_related("disciplina").order_by("disciplina__nome"))
    disciplinas = [p.disciplina for p in planos]
    tem_exame_classe = any(p.tem_exame_nacional for p in planos)
    tempos_previstos = (sum(p.carga_horaria_semanal for p in planos)
                        * (turma.ano_lectivo.semanas_lectivas or 33))

    matriculas = list(
        Matricula.objects.filter(turma=turma, ano_lectivo=turma.ano_lectivo)
        .select_related("aluno").order_by("aluno__nome_completo"))
    ids = [m.id for m in matriculas]

    ras = {(r.matricula_id, r.disciplina_id): r
           for r in ResultadoAnual.objects.filter(matricula_id__in=ids)}
    recursos = {(e.matricula_id, e.disciplina_id): e.nota
                for e in Exame.objects.filter(matricula_id__in=ids, tipo=Exame.Tipo.RECURSO)
                if e.nota is not None}
    faltas = defaultdict(Decimal)
    for f in (Falta.objects.filter(matricula_id__in=ids, justificada=False)
              .values("matricula_id").annotate(t=Sum("tempos"))):
        faltas[f["matricula_id"]] = Decimal(f["t"] or 0)
    paps = {p.matricula_id: p for p in ProvaAptidaoProfissional.objects.filter(matricula_id__in=ids)}

    exige_pap = turma.curso.exige_pap or turma.curso.exige_estagio
    MS = Matricula.Status
    estados = {MS.TRANSFERIDA: "Transferido", MS.DESISTENTE: "Desistente",
               MS.CANCELADA: "Cancelada", MS.TRANCAMENTO: "Trancamento"}

    resultados = []
    for m in matriculas:
        res = ResultadoAluno(matricula=m)
        for p in planos:
            res.linhas.append(_avaliar_disciplina(
                p, ras.get((m.id, p.disciplina_id)),
                recursos.get((m.id, p.disciplina_id)), regra))

        notas = [l.nota_final if l.nota_final is not None else l.mfd for l in res.linhas]
        notas = [n for n in notas if n is not None]
        res.media_geral = _arred(sum(notas) / len(notas), regra) if notas else None
        if tempos_previstos:
            res.faltas_pct = (faltas[m.id] / tempos_previstos * 100).quantize(Decimal("0.1"))

        pap_ok = True
        if exige_pap:
            pap = paps.get(m.id)
            pap_ok = bool(
                pap
                and (not turma.curso.exige_pap or (pap.nota_pap or 0) >= regra.nota_minima_positiva)
                and (not turma.curso.exige_estagio or (pap.nota_estagio or 0) >= regra.nota_minima_positiva))

        estado = estados.get(m.status)
        _decidir_aluno(res, regra, turma, tem_exame_classe, pap_ok, estado)
        resultados.append(res)

    return disciplinas, resultados, regra


def resumo(resultados):
    r = defaultdict(int)
    for x in resultados:
        r[x.situacao] += 1
    return {
        "total": len(resultados),
        "positivos": sum(1 for x in resultados if x.positivo),
        "recurso": r[ADMITIDO_RECURSO],
        "exame": r[ADMITIDO_EXAME],
        "negativos": r[REPROVADO] + r[NAO_TRANSITA] + r[REPROVADO_FALTAS],
    }