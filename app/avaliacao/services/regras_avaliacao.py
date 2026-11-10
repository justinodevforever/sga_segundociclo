"""Regras de cálculo da avaliação (II Ciclo - Angola)."""
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, Sum

from app.db.models import (AvaliacaoContinua, Exame, Falta, Matricula, PlanoCurricular,
                     RegraAvaliacao, ResultadoAnual, ResultadoTrimestral)


def obter_regra(ano_lectivo, classe):
    regra = (RegraAvaliacao.objects.filter(ano_lectivo=ano_lectivo, classe=classe).first()
             or RegraAvaliacao.objects.filter(ano_lectivo=ano_lectivo, classe__isnull=True).first())
    if regra is None:
        raise ValueError(f"Sem RegraAvaliacao definida para {ano_lectivo} / {classe}.ª classe")
    return regra


def arredondar(valor, regra):
    if valor is None:
        return None
    q = Decimal("1") if regra.arredondar_unidades else Decimal("0.01")
    return Decimal(valor).quantize(q, rounding=ROUND_HALF_UP)


def recalcular_trimestral(r: ResultadoTrimestral):
    """MAC = média das avaliações contínuas; MT = média ponderada de MAC, PP, PT."""
    regra = obter_regra(r.matricula.ano_lectivo, r.matricula.turma.classe)
    media = (AvaliacaoContinua.objects
             .filter(matricula=r.matricula, disciplina=r.disciplina, trimestre=r.trimestre)
             .aggregate(m=Avg("valor"))["m"])
    r.mac = arredondar(media, regra)
    if None in (r.mac, r.pp, r.pt):
        r.mt = None
    else:
        soma_pesos = regra.peso_mac + regra.peso_pp + regra.peso_pt
        mt = (r.mac * regra.peso_mac + r.pp * regra.peso_pp + r.pt * regra.peso_pt) / soma_pesos
        r.mt = arredondar(mt, regra)
    return r


def recalcular_anual(matricula: Matricula, disciplina):
    """MFD = média das 3 MT; classes com exame: NF = MFD*(1-p) + Exame*p."""
    classe = matricula.turma.classe
    regra = obter_regra(matricula.ano_lectivo, classe)
    ra, _ = ResultadoAnual.objects.get_or_create(matricula=matricula, disciplina=disciplina)

    mts = {rt.trimestre.designacao: rt.mt for rt in ResultadoTrimestral.objects
           .filter(matricula=matricula, disciplina=disciplina).select_related("trimestre")}
    ra.mt1, ra.mt2, ra.mt3 = mts.get(1), mts.get(2), mts.get(3)

    if None in (ra.mt1, ra.mt2, ra.mt3):
        ra.mfd = ra.nota_final = ra.nota_exame = None
        ra.situacao = ResultadoAnual.Situacao.PENDENTE
        ra.save()
        return ra

    ra.mfd = arredondar((ra.mt1 + ra.mt2 + ra.mt3) / 3, regra)

    plano = PlanoCurricular.objects.filter(
        curso=matricula.turma.curso, classe=classe, disciplina=disciplina).first()
    tem_exame = bool(plano and plano.tem_exame_nacional)

    if tem_exame:
        exame = (Exame.objects.filter(matricula=matricula, disciplina=disciplina, nota__isnull=False)
                 .order_by("-data", "-id").first())
        ra.nota_exame = exame.nota if exame else None
        if ra.nota_exame is None:
            ra.nota_final = None
            ra.situacao = ResultadoAnual.Situacao.PENDENTE
            ra.save()
            return ra
        p = regra.peso_exame_na_nota_final
        ra.nota_final = arredondar(ra.mfd * (1 - p) + ra.nota_exame * p, regra)
        positiva = (ra.nota_final >= regra.nota_minima_positiva
                    and ra.nota_exame >= regra.nota_minima_exame)
    else:
        ra.nota_exame = None
        ra.nota_final = ra.mfd
        positiva = ra.nota_final >= regra.nota_minima_positiva

    ra.situacao = ResultadoAnual.Situacao.POSITIVA if positiva else ResultadoAnual.Situacao.NEGATIVA
    ra.save()
    return ra


def percentagem_faltas_injustificadas(matricula: Matricula):
    """Faltas injustificadas / tempos previstos no ano (carga semanal x semanas lectivas)."""
    semanas = matricula.ano_lectivo.semanas_lectivas
    plano = PlanoCurricular.objects.filter(curso=matricula.turma.curso, classe=matricula.turma.classe)
    previstos = (plano.aggregate(s=Sum("carga_horaria_semanal"))["s"] or 0) * semanas
    if not previstos:
        return Decimal("0")
    faltas = (Falta.objects.filter(matricula=matricula, justificada=False)
              .aggregate(s=Sum("tempos"))["s"] or 0)
    return Decimal(faltas) * 100 / previstos


def decidir_situacao_final(matricula: Matricula, gravar=True):
    S = Matricula.Situacao
    classe = matricula.turma.classe
    regra = obter_regra(matricula.ano_lectivo, classe)
    plano = PlanoCurricular.objects.filter(curso=matricula.turma.curso, classe=classe)

    if percentagem_faltas_injustificadas(matricula) > regra.limite_faltas_injustificadas_pct:
        situacao = S.REPROVADO_FALTAS
    else:
        resultados = {ra.disciplina_id: ra for ra in matricula.resultados_anuais.all()}
        pendente = any(
            p.disciplina_id not in resultados
            or resultados[p.disciplina_id].situacao == ResultadoAnual.Situacao.PENDENTE
            for p in plano)
        if pendente or not plano.exists():
            situacao = S.EM_CURSO
        else:
            negativas = sum(1 for ra in resultados.values()
                            if ra.situacao == ResultadoAnual.Situacao.NEGATIVA)
            classe_exame = plano.filter(tem_exame_nacional=True).exists()
            limite = 0 if (classe_exame and regra.classe_exame_exige_todas_positivas) \
                else regra.max_negativas_transicao
            situacao = S.APROVADO if negativas <= limite else S.REPROVADO

    if gravar:
        matricula.situacao_final = situacao
        matricula.save(update_fields=["situacao_final"])
    return situacao