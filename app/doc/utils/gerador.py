"""
Serviço de geração de Certificados e Declarações para o II Ciclo — Angola.

Responsabilidades:
  - Resolver variáveis dinâmicas ({{aluno_nome}}, etc.)
  - Gerar HTML final do documento (usado para impressão via browser)
  - Gerar ficheiro DOCX (via docx-js através de subprocess)
  - Converter números para extenso em português angolano
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ── Números por extenso (0–20, escala de notas) ────────────────────────────────

_UNIDADES = [
    "zero", "um", "dois", "três", "quatro", "cinco",
    "seis", "sete", "oito", "nove", "dez",
    "onze", "doze", "treze", "catorze", "quinze",
    "dezasseis", "dezassete", "dezoito", "dezanove", "vinte",
]


def nota_por_extenso(nota: Decimal | float | None) -> str:
    """
    Converte uma nota (0-20) para extenso em português.
    Ex: 16.5 → "dezasseis vírgula cinco valores"
         10   → "dez valores"
    """
    if nota is None:
        return "não disponível"
    nota = Decimal(str(nota))
    inteiro = int(nota)
    decimal_parte = nota - inteiro

    if 0 <= inteiro <= 20:
        texto = _UNIDADES[inteiro]
    else:
        texto = str(inteiro)

    if decimal_parte > 0:
        dec_str = str(decimal_parte).split(".")[1].rstrip("0")
        texto += f" vírgula {dec_str}"

    return f"{texto} valores"


def formatar_data_pt(d: date | None) -> str:
    """Formata uma data em português: '15 de Março de 2024'."""
    if d is None:
        return "—"
    meses = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    return f"{d.day} de {meses[d.month]} de {d.year}"


# ── Resolução de variáveis ─────────────────────────────────────────────────────

def _get_director_nome(escola) -> str:
    """Obtém o nome do director activo da escola."""
    try:
        director = escola.diretor_set.filter(status="Activo").first()
        return director.nome_completo if director else "—"
    except Exception:
        return "—"


def _get_media_geral(resultados_anuais) -> str:
    """Calcula a média geral das notas finais."""
    notas = [r.nota_final for r in resultados_anuais if r.nota_final is not None]
    if not notas:
        return "—"
    media = sum(notas) / len(notas)
    return f"{media:.2f}"


def resolver_variaveis(
    template,
    aluno,
    matricula=None,
    ano_lectivo=None,
    resultados_anuais=None,
    data_emissao: date | None = None,
    numero_documento: str = "",
) -> dict[str, str]:
    """
    Resolve todas as variáveis disponíveis para um dado aluno/matrícula.
    Retorna um dicionário {variavel: valor} pronto para substituição.
    """
    if data_emissao is None:
        data_emissao = timezone.now().date()

    resultados = resultados_anuais or []
    escola = template.escola

    # Turma e curso a partir da matrícula
    turma = matricula.turma if matricula else None
    classe = turma.classe if turma else None
    curso = turma.curso if turma else None
    periodo = turma.periodo if turma else None

    # Nota final — usa média geral ou nota de resultado específico
    nota_final_val = None
    if resultados:
        notas_validas = [r.nota_final for r in resultados if r.nota_final is not None]
        if notas_validas:
            nota_final_val = sum(notas_validas) / len(notas_validas)

    situacao = "—"
    if resultados:
        # Usa a situação mais comum entre os resultados
        situacoes = [r.situacao for r in resultados if r.situacao]
        if situacoes:
            from collections import Counter
            situacao = Counter(situacoes).most_common(1)[0][0]

    variaveis = {
        # ── Aluno ──────────────────────────────────────────────────────────
        "aluno_nome": aluno.nome_completo or "—",
        "aluno_bi": aluno.bi or "—",
        "aluno_naturalidade": getattr(aluno, "naturalidade", "—") or "—",
        "aluno_data_nasc": formatar_data_pt(aluno.data_nascimento) if aluno.data_nascimento else "—",
        "aluno_nome_pai": getattr(aluno, "nome_pai", "—") or "—",
        "aluno_nome_mae": getattr(aluno, "nome_mae", "—") or "—",
        "aluno_numero_processo": aluno.numero_processo or "—",
        # ── Académico ──────────────────────────────────────────────────────
        "ano_lectivo": ano_lectivo.designacao if ano_lectivo else "—",
        "classe": classe.designacao if classe else "—",
        "curso": curso.nome if curso else "—",
        "turma": turma.designacao if turma else "—",
        "periodo": periodo.get_designacao_display() if periodo else "—",
        # ── Resultado ──────────────────────────────────────────────────────
        "nota_final_num": f"{nota_final_val:.0f}" if nota_final_val is not None else "—",
        "nota_final_extenso": nota_por_extenso(nota_final_val) if nota_final_val is not None else "—",
        "situacao_final": situacao,
        "media_geral": _get_media_geral(resultados),
        # ── Escola ─────────────────────────────────────────────────────────
        "escola_nome": escola.nome or "—",
        "escola_provincia": escola.provincia or "—",
        "escola_municipio": escola.municipio or "—",
        "escola_nif": escola.nif or "—",
        "escola_director": _get_director_nome(escola),
        # ── Data / Emissão ─────────────────────────────────────────────────
        "data_emissao": formatar_data_pt(data_emissao),
        "local_emissao": template.local_emissao,
        "numero_documento": numero_documento,
        "tipo_documento": template.get_tipo_display().lower(),
    }

    # Segunda passagem: resolver variáveis dentro de outras variáveis
    # Ex: local_emissao = "{{escola_municipio}}" → já foi resolvido acima
    for chave in list(variaveis.keys()):
        val = variaveis[chave]
        for sub_chave, sub_val in variaveis.items():
            val = val.replace(f"{{{{{sub_chave}}}}}", sub_val)
        variaveis[chave] = val

    return variaveis


def aplicar_variaveis(texto: str, variaveis: dict[str, str]) -> str:
    """Substitui todas as variáveis {{chave}} pelo respectivo valor."""
    for chave, valor in variaveis.items():
        texto = texto.replace(f"{{{{{chave}}}}}", str(valor))
    return texto


# ── Geração de HTML para impressão ────────────────────────────────────────────

def gerar_html_documento(
    template,
    aluno,
    matricula=None,
    ano_lectivo=None,
    resultados_anuais=None,
    assinaturas=None,
    numero_documento: str = "",
    data_emissao: date | None = None,
) -> str:
    """
    Gera o HTML completo do documento para impressão via browser.
    Este HTML é auto-suficiente (CSS inline) e optimizado para impressão.
    """
    variaveis = resolver_variaveis(
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        resultados_anuais=resultados_anuais or [],
        data_emissao=data_emissao,
        numero_documento=numero_documento,
    )

    def ap(texto: str) -> str:
        return aplicar_variaveis(texto, variaveis)

    # Tabela de notas (se pedida)
    tabela_html = ""
    if template.incluir_tabela_notas and resultados_anuais:
        linhas = ""
        for i, res in enumerate(resultados_anuais, 1):
            mac1 = f"{res.mac_1_trimestre:.1f}" if res.mac_1_trimestre is not None else "—"
            mac2 = f"{res.mac_2_trimestre:.1f}" if res.mac_2_trimestre is not None else "—"
            mac3 = f"{res.mac_3_trimestre:.1f}" if res.mac_3_trimestre is not None else "—"
            mac_anual = f"{res.mac_anual:.1f}" if res.mac_anual is not None else "—"
            nota_final = f"{res.nota_final:.1f}" if res.nota_final is not None else "—"
            exame = f"{res.nota_exame:.1f}" if res.nota_exame is not None else "—"
            situacao_css = "aprovado" if "Aprovado" in (res.situacao or "") else "reprovado"
            linhas += f"""
            <tr>
                <td class="num">{i}</td>
                <td class="disciplina">{res.disciplina.nome}</td>
                <td class="nota">{mac1}</td>
                <td class="nota">{mac2}</td>
                <td class="nota">{mac3}</td>
                <td class="nota mac">{mac_anual}</td>
                <td class="nota">{exame}</td>
                <td class="nota final">{nota_final}</td>
                <td class="situacao {situacao_css}">{res.situacao or '—'}</td>
            </tr>"""

        tabela_html = f"""
        <div class="secao-notas">
            <p class="texto-antes-tabela">{ap(template.texto_antes_tabela)}</p>
            <table class="tabela-notas">
                <thead>
                    <tr>
                        <th class="num">Nº</th>
                        <th class="disciplina">Disciplina</th>
                        <th class="nota">1º Trim.</th>
                        <th class="nota">2º Trim.</th>
                        <th class="nota">3º Trim.</th>
                        <th class="nota mac">MAC</th>
                        <th class="nota">Exame</th>
                        <th class="nota final">Final</th>
                        <th class="situacao">Situação</th>
                    </tr>
                </thead>
                <tbody>{linhas}</tbody>
            </table>
        </div>"""

    # Assinaturas
    assinaturas_html = ""
    if assinaturas:
        colunas = ""
        for assinatura in assinaturas:
            colunas += f"""
            <div class="assinatura-coluna">
                <div class="linha-assinatura"></div>
                <p class="assinatura-nome">{assinatura.nome_completo}</p>
                <p class="assinatura-cargo">{assinatura.cargo_display}</p>
            </div>"""
        assinaturas_html = f'<div class="bloco-assinaturas">{colunas}</div>'

    # Logótipo
    logo_html = ""
    if template.mostrar_brasao:
        try:
            logo_url = template.escola.logotipo.url
            logo_html = f'<img src="{logo_url}" class="logo-escola" alt="Logótipo">'
        except Exception:
            logo_html = '<div class="logo-placeholder">🏫</div>'

    borda_class = "com-borda" if template.usar_borda else ""
    orientacao_class = "paisagem" if template.orientacao == "paisagem" else "retrato"
    font_size = template.tamanho_fonte_corpo
    margin_top = template.margem_topo
    margin_lr = template.margem_lateral

    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ap(template.cabecalho_titulo)} — {aluno.nome_completo}</title>
<style>
  /* ── Reset & Variáveis ── */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --cor-primaria: #1a3a5c;
    --cor-secundaria: #2e6da4;
    --cor-texto: #1a1a1a;
    --cor-borda: #2e6da4;
    --cor-tabela-header: #1a3a5c;
    --cor-tabela-zebra: #f0f4f8;
    --cor-aprovado: #1a6b3a;
    --cor-reprovado: #9b1a1a;
    --font-principal: 'Times New Roman', Times, serif;
    --font-sans: Arial, sans-serif;
  }}

  /* ── Página ── */
  body {{ font-family: var(--font-principal); background: #e8e8e8; }}

  .pagina {{
    background: white;
    margin: 20px auto;
    padding: {margin_top}cm {margin_lr}cm;
    font-size: {font_size}pt;
    line-height: 1.6;
    color: var(--cor-texto);
    position: relative;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  }}
  .pagina.retrato {{ width: 21cm; min-height: 29.7cm; }}
  .pagina.paisagem {{ width: 29.7cm; min-height: 21cm; }}

  /* ── Borda decorativa ── */
  .com-borda::before {{
    content: '';
    position: absolute;
    top: 0.8cm; left: 0.8cm;
    right: 0.8cm; bottom: 0.8cm;
    border: 3px double var(--cor-borda);
    pointer-events: none;
  }}
  .com-borda::after {{
    content: '';
    position: absolute;
    top: 1.0cm; left: 1.0cm;
    right: 1.0cm; bottom: 1.0cm;
    border: 1px solid var(--cor-borda);
    pointer-events: none;
  }}

  /* ── Cabeçalho ── */
  .cabecalho {{
    text-align: center;
    margin-bottom: 0.8cm;
    padding-bottom: 0.5cm;
    border-bottom: 2px solid var(--cor-primaria);
  }}
  .logo-escola {{
    height: 2.2cm;
    max-width: 4cm;
    object-fit: contain;
    margin-bottom: 0.3cm;
  }}
  .logo-placeholder {{
    font-size: 2.5cm;
    line-height: 1;
    margin-bottom: 0.3cm;
  }}
  .republica-angola {{
    font-family: var(--font-sans);
    font-size: 9pt;
    font-weight: bold;
    letter-spacing: 0.05em;
    color: #555;
    text-transform: uppercase;
    margin-bottom: 0.15cm;
  }}
  .ministerio {{
    font-family: var(--font-sans);
    font-size: 8pt;
    color: #666;
    margin-bottom: 0.3cm;
  }}
  .escola-nome {{
    font-family: var(--font-sans);
    font-size: 13pt;
    font-weight: bold;
    color: var(--cor-primaria);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 0.1cm;
  }}
  .escola-info {{
    font-size: 9pt;
    color: #555;
    font-family: var(--font-sans);
  }}

  /* ── Título do documento ── */
  .titulo-documento {{
    text-align: center;
    margin: 0.6cm 0 0.5cm;
  }}
  .titulo-documento h1 {{
    font-family: var(--font-sans);
    font-size: 16pt;
    font-weight: bold;
    color: var(--cor-primaria);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    border-bottom: 3px solid var(--cor-secundaria);
    display: inline-block;
    padding-bottom: 0.15cm;
  }}
  .subtitulo {{
    font-size: 10pt;
    color: #666;
    margin-top: 0.2cm;
    font-style: italic;
  }}

  /* ── Número do documento ── */
  .numero-documento {{
    text-align: right;
    font-family: var(--font-sans);
    font-size: 9pt;
    color: #666;
    margin-bottom: 0.4cm;
  }}

  /* ── Corpo ── */
  .texto-abertura,
  .texto-identificacao,
  .texto-corpo,
  .texto-rodape {{
    text-align: justify;
    margin-bottom: 0.4cm;
  }}
  .texto-identificacao {{
    font-weight: bold;
    font-style: italic;
  }}
  .texto-corpo {{
    padding: 0.3cm 0.5cm;
    border-left: 3px solid var(--cor-secundaria);
    background: #f8fafc;
  }}

  /* ── Tabela de notas ── */
  .secao-notas {{ margin: 0.5cm 0; }}
  .texto-antes-tabela {{
    font-size: 10pt;
    font-style: italic;
    margin-bottom: 0.2cm;
    font-family: var(--font-sans);
  }}
  .tabela-notas {{
    width: 100%;
    border-collapse: collapse;
    font-size: 9pt;
    font-family: var(--font-sans);
  }}
  .tabela-notas thead tr {{
    background: var(--cor-tabela-header);
    color: white;
  }}
  .tabela-notas th {{
    padding: 0.2cm 0.15cm;
    text-align: center;
    font-weight: bold;
    font-size: 8pt;
    letter-spacing: 0.02em;
  }}
  .tabela-notas th.disciplina {{ text-align: left; }}
  .tabela-notas tbody tr:nth-child(even) {{
    background: var(--cor-tabela-zebra);
  }}
  .tabela-notas tbody tr:hover {{ background: #dbe8f5; }}
  .tabela-notas td {{
    padding: 0.18cm 0.15cm;
    border-bottom: 1px solid #ddd;
    text-align: center;
  }}
  .tabela-notas td.disciplina {{ text-align: left; }}
  .tabela-notas td.mac {{
    font-weight: bold;
    background: rgba(46, 109, 164, 0.1);
  }}
  .tabela-notas td.final {{
    font-weight: bold;
    font-size: 10pt;
  }}
  .tabela-notas .aprovado {{ color: var(--cor-aprovado); font-weight: bold; }}
  .tabela-notas .reprovado {{ color: var(--cor-reprovado); font-weight: bold; }}
  .tabela-notas .num {{ color: #888; width: 1.2cm; }}

  /* ── Data e local ── */
  .data-local {{
    text-align: right;
    margin: 0.6cm 0 0.4cm;
    font-style: italic;
    font-size: 11pt;
  }}

  /* ── Assinaturas ── */
  .bloco-assinaturas {{
    display: flex;
    justify-content: space-around;
    margin-top: 1cm;
    gap: 1cm;
  }}
  .assinatura-coluna {{
    text-align: center;
    flex: 1;
    max-width: 7cm;
  }}
  .linha-assinatura {{
    border-top: 1px solid var(--cor-texto);
    margin-bottom: 0.2cm;
  }}
  .assinatura-nome {{
    font-weight: bold;
    font-size: 10pt;
    font-family: var(--font-sans);
  }}
  .assinatura-cargo {{
    font-size: 9pt;
    color: #555;
    font-style: italic;
    font-family: var(--font-sans);
  }}

  /* ── Rodapé do documento ── */
  .rodape-pagina {{
    margin-top: 0.8cm;
    padding-top: 0.3cm;
    border-top: 1px solid #ccc;
    font-size: 8pt;
    color: #888;
    text-align: center;
    font-family: var(--font-sans);
  }}

  /* ── Barra de controlo (não imprime) ── */
  .barra-controlo {{
    display: flex;
    gap: 1rem;
    justify-content: center;
    padding: 1rem;
    background: #1a3a5c;
    margin-bottom: 1rem;
    border-radius: 0;
    position: sticky;
    top: 0;
    z-index: 100;
  }}
  .btn-imprimir {{
    background: white;
    color: #1a3a5c;
    border: none;
    padding: 0.5rem 1.5rem;
    font-size: 14px;
    font-weight: bold;
    cursor: pointer;
    border-radius: 4px;
    font-family: Arial, sans-serif;
  }}
  .btn-imprimir:hover {{ background: #e8f0f7; }}

  /* ── Impressão ── */
  @media print {{
    body {{ background: white; }}
    .barra-controlo {{ display: none !important; }}
    .pagina {{
      margin: 0;
      box-shadow: none;
      padding: {margin_top}cm {margin_lr}cm;
    }}
    @page {{
      size: {"A4 landscape" if template.orientacao == "paisagem" else "A4 portrait"};
      margin: 0;
    }}
  }}
</style>
</head>
<body>

<div class="barra-controlo">
  <button class="btn-imprimir" onclick="window.print()">🖨️ Imprimir</button>
  <button class="btn-imprimir" onclick="window.close()">✕ Fechar</button>
</div>

<div class="pagina {orientacao_class} {borda_class}">

  <!-- CABEÇALHO -->
  <div class="cabecalho">
    {logo_html}
    {"<p class='republica-angola'>República de Angola</p>" if template.mostrar_cabecalho_escola else ""}
    {"<p class='ministerio'>Ministério da Educação</p>" if template.mostrar_cabecalho_escola else ""}
    {"<p class='escola-nome'>" + ap("{{escola_nome}}") + "</p>" if template.mostrar_cabecalho_escola else ""}
    {"<p class='escola-info'>" + ap("{{escola_provincia}} — {{escola_municipio}}") + "</p>" if template.mostrar_cabecalho_escola else ""}
  </div>

  <!-- TÍTULO -->
  <div class="titulo-documento">
    <h1>{ap(template.cabecalho_titulo)}</h1>
    {"<p class='subtitulo'>" + ap(template.cabecalho_subtitulo) + "</p>" if template.cabecalho_subtitulo else ""}
  </div>

  <!-- NÚMERO DO DOCUMENTO -->
  {f'<p class="numero-documento">N.º {numero_documento}</p>' if numero_documento else ""}

  <!-- CORPO -->
  <p class="texto-abertura">{ap(template.texto_abertura)}</p>
  <p class="texto-identificacao">{ap(template.texto_identificacao)}</p>
  <p class="texto-corpo">{ap(template.texto_corpo)}</p>

  {tabela_html}

  <p class="texto-rodape">{ap(template.texto_rodape)}</p>

  <!-- DATA E LOCAL -->
  <p class="data-local">{ap(template.texto_data_emissao)}</p>

  <!-- ASSINATURAS -->
  {assinaturas_html}

  <!-- RODAPÉ DA PÁGINA -->
  <div class="rodape-pagina">
    <p>Documento emitido pelo Sistema de Gestão Académica &bull; {template.escola.nome} &bull; NIF: {template.escola.nif}</p>
  </div>

</div>

</body>
</html>"""


def construir_snapshot(
    template,
    aluno,
    matricula=None,
    ano_lectivo=None,
    resultados_anuais=None,
    numero_documento: str = "",
) -> dict[str, Any]:
    """Constrói o snapshot JSON dos dados para arquivo imutável."""
    variaveis = resolver_variaveis(
        template=template,
        aluno=aluno,
        matricula=matricula,
        ano_lectivo=ano_lectivo,
        resultados_anuais=resultados_anuais or [],
        numero_documento=numero_documento,
    )
    return {
        "variaveis": variaveis,
        "template_id": str(template.id),
        "template_nome": template.nome,
        "tipo_documento": template.tipo,
        "aluno_id": str(aluno.id),
        "aluno_nome": aluno.nome_completo,
        "resultados": [
            {
                "disciplina": r.disciplina.nome,
                "mac_1": str(r.mac_1_trimestre) if r.mac_1_trimestre is not None else None,
                "mac_2": str(r.mac_2_trimestre) if r.mac_2_trimestre is not None else None,
                "mac_3": str(r.mac_3_trimestre) if r.mac_3_trimestre is not None else None,
                "mac_anual": str(r.mac_anual) if r.mac_anual is not None else None,
                "nota_exame": str(r.nota_exame) if r.nota_exame is not None else None,
                "nota_final": str(r.nota_final) if r.nota_final is not None else None,
                "situacao": r.situacao,
            }
            for r in (resultados_anuais or [])
        ],
        "gerado_em": timezone.now().isoformat(),
    }