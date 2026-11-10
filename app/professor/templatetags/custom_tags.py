from django import template

register = template.Library()

@register.filter
def get_item(dicionario, chave):
    if dicionario:
        
        return dicionario.get(str(chave))