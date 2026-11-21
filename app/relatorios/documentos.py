"""Documentos individuais em PDF: boletim, ficha, declaração, histórico escolar e horários."""
import os
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from app.db.models import (Diretor, Falta, HorarioAula, Matricula, PlanoCurricular, ResultadoAnual,
                        ResultadoTrimestral)

from .utils import cel_nota, limiar

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


class DocumentoErro(Exception):
    pass


def _matricula(f):
    m = (Matricula.objects.select_related("aluno", "ano_lectivo", "turma__curso", "turma__classe")
         .filter(aluno=f["aluno"], ano_lectivo=f["ano_lectivo"]).first())
    if not m:
        raise DocumentoErro("O aluno seleccionado não tem matrícula no ano lectivo indicado.")
    if not m.turma:
        raise DocumentoErro("A matrícula do aluno ainda não tem turma atribuída.")
    return m


def _foto(aluno):
    try:
        return aluno.foto.path if aluno.foto and os.path.exists(aluno.foto.path) else None
    except Exception:
        return None


def _diretor():
    return Diretor.objects.filter(status=Diretor.Status.ACTIVO).first()


def _data_extenso(d=None):
    d = d or date.today()
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def linhas_boletim(mat):
    t = mat.turma
    lim = limiar(mat.ano_lectivo, t.classe)
    plano = (PlanoCurricular.objects.filter(curso=t.curso, classe=t.classe).select_related("disciplina")
             .order_by("disciplina__componente", "disciplina__nome"))
    anuais = {r.disciplina_id: r for r in ResultadoAnual.objects.filter(matricula=mat)}
    trims = defaultdict(dict)
    for r in ResultadoTrimestral.objects.filter(matricula=mat).select_related("trimestre"):
        trims[r.disciplina_id][r.trimestre.designacao] = r
    linhas, finais = [], []
    for p in plano:
        d, ra = p.disciplina, anuais.get(p.disciplina_id)
        tri = []
        for n in (1, 2, 3):
            r = trims[d.id].get(n)
            tri.append([cel_nota(getattr(r, c, None), lim) for c in ("mac", "pp", "pt", "mt")])
        nf = None
        if ra:
            nf = ra.nota_final if ra.nota_final is not None else ra.mfd
        if nf is not None:
            finais.append(Decimal(nf))
        linhas.append({
            "disciplina": d.nome, "tri": tri,
            "mt": [tri[i][3] for i in range(3)],
            "mfd": cel_nota(ra.mfd if ra else None, lim),
            "exame": cel_nota(ra.nota_exame if ra else None, lim),
            "nf": cel_nota(nf, lim),
            "obs": "-" if nf is None else ("Positiva" if nf >= lim else "Negativa"),
        })
    f = Falta.objects.filter(matricula=mat).aggregate(
        j=Sum("tempos", filter=Q(justificada=True)), i=Sum("tempos", filter=Q(justificada=False)))
    return {
        "linhas": linhas,
        "media_final": round(sum(finais) / len(finais), 2) if finais else None,
        "negativas": sum(1 for x in finais if x < lim),
        "faltas_j": f["j"] or 0, "faltas_i": f["i"] or 0,
    }


def doc_boletim(f):
    m = _matricula(f)
    return "relatorios/pdf/boletim.html", {"mat": m, "aluno": m.aluno, "turma": m.turma,
                                           "diretor": _diretor(), **linhas_boletim(m)}, "landscape"


def doc_historico(f):
    a = f["aluno"]
    anos = []
    for m in (a.matriculas.select_related("ano_lectivo", "turma__curso", "turma__classe")
              .exclude(status=Matricula.Status.CANCELADA).order_by("ano_lectivo__data_inicio")):
        if m.turma:
            anos.append({"mat": m, **linhas_boletim(m)})
    if not anos:
        raise DocumentoErro("O aluno não tem matrículas com turma atribuída.")
    return "relatorios/pdf/historico.html", {"aluno": a, "anos": anos, "diretor": _diretor(),
                                             "data_extenso": _data_extenso()}, "portrait"


def doc_ficha(f):
    a = f["aluno"]
    return "relatorios/pdf/ficha_aluno.html", {
        "aluno": a, "foto": _foto(a),
        "matriculas": a.matriculas.select_related("ano_lectivo", "turma__curso", "turma__classe")
                       .order_by("-ano_lectivo__data_inicio"),
        "documentos": a.documentos.order_by("tipo_documento")}, "portrait"


def doc_declaracao(f):
    m = _matricula(f)
    return "relatorios/pdf/declaracao.html", {"mat": m, "aluno": m.aluno, "turma": m.turma, "diretor": _diretor(),
                                              "data_extenso": _data_extenso()}, "portrait"

DOCUMENTOS = {
    "boletim": dict(titulo="Boletim de Notas", icone="bi-card-checklist", fn=doc_boletim,
                    desc="Notas de todas as disciplinas por trimestre (MAC, PP, PT, MT), média final e resultado.",
                    campos=("aluno", "ano_lectivo"), obrigatorios=("aluno", "ano_lectivo")),
    "declaracao": dict(titulo="Declaração de Matrícula", icone="bi-file-earmark-text", fn=doc_declaracao,
                       desc="Declaração oficial de que o aluno se encontra matriculado no ano lectivo.",
                       campos=("aluno", "ano_lectivo"), obrigatorios=("aluno", "ano_lectivo")),
    "historico": dict(titulo="Histórico Escolar / Certificado de Habilitações", icone="bi-patch-check",
                      fn=doc_historico, desc="Notas finais de todas as classes frequentadas pelo aluno.",
                      campos=("aluno",), obrigatorios=("aluno",)),
    "ficha": dict(titulo="Ficha Individual do Aluno", icone="bi-person-lines-fill", fn=doc_ficha,
                  desc="Dados pessoais, filiação, localização, matrículas e documentos entregues.",
                  campos=("aluno",), obrigatorios=("aluno",)),
    
}