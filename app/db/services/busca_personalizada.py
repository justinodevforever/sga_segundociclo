from django.db.models import Count, Q


def contar_choices_optimizdo(model, campo, campo_filtro):


    choices = model._meta.get_field(campo).choices


    agregacao = {
        valor: Count('id', filter=Q(**{campo: valor}))
        for valor, _ in choices
    }

    contagem = model.objects.filter(status=campo_filtro).aggregate(**agregacao)

    resultado = [
        {
            'valor': valor,
            'nome': nome,
            'total': contagem.get(valor, 0)
        }
        for valor, nome in choices
    ]

    return resultado