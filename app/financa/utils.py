from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils import timezone

def gerar_recibo_pdf(request, pagamento):
    """Gera PDF do recibo usando xhtml2pdf."""
    try:
        from xhtml2pdf import pisa
        qr_base64 = pagamento.gerar_qr_code()
        html = render_to_string('financeiro/recibo_pdf.html', {
            'pagamento': pagamento,
            'qr_base64': qr_base64,
            'escola': getattr(request, 'escola', None),
        }, request=request)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = (
            f'inline; filename="recibo_{pagamento.numero_recibo}.pdf"'
        )
        pisa.CreatePDF(html, dest=response)
        return response
    except ImportError:
        return HttpResponse(
            'xhtml2pdf não instalado. Execute: pip install xhtml2pdf',
            status=500
        )


def gerar_relatorio_pdf(request, contas, totais, por_status):
    """Gera PDF do relatório financeiro."""
    try:
        from xhtml2pdf import pisa
        html = render_to_string('financeiro/relatorio_pdf.html', {
            'contas': contas,
            'totais': totais,
            'por_status': por_status,
            'data': timezone.now(),
            'escola': getattr(request, 'escola', None),
        }, request=request)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="relatorio_financeiro_{timezone.now().strftime("%Y%m%d")}.pdf"'
        )
        pisa.CreatePDF(html, dest=response)
        return response
    except ImportError:
        return HttpResponse(
            'xhtml2pdf não instalado. Execute: pip install xhtml2pdf',
            status=500
        )