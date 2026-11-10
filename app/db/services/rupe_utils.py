"""
Utilitários para geração e gerenciamento de RUPEs
Arquivo: sua_app/utils/rupe_utils.py
"""

import random
import string
from decimal import Decimal
from datetime import datetime
from django.db import transaction
from django.apps import apps
import logging

logger = logging.getLogger(__name__)



class RUPEGenerator:
    """
    Gerador de RUPEs em massa com diferentes formatos
    """
    
    def __init__(self, rupe_model_name='administrador.RUPE'):
        """
        Inicializa o gerador
        
        Args:
            rupe_model_name: Nome do modelo RUPE (formato: app.Model)
        """
        self.RUPE = apps.get_model(rupe_model_name)
    
    def gerar_codigo_simples(self, ano=None, sequencia=None):
        """
        Gera código RUPE no formato: RUPE-ANO-SEQUENCIA
        
        Args:
            ano: Ano (padrão: ano atual)
            sequencia: Número sequencial
        
        Returns:
            String com código RUPE
        """
        if ano is None:
            ano = datetime.now().year
        
        if sequencia is None:
            # Buscar última sequência do ano
            ultimo = self.RUPE.objects.filter(
                codigo__startswith=f'RUPE-{ano}-'
            ).order_by('-codigo').first()
            
            if ultimo:
                try:
                    ultima_seq = int(ultimo.codigo.split('-')[-1])
                    sequencia = ultima_seq + 1
                except:
                    sequencia = 1
            else:
                sequencia = 1
        
        return f'RUPE-{ano}-{sequencia:06d}'
    
    def gerar_codigo_aleatorio(self, prefixo='RUPE', tamanho=12):
        """
        Gera código RUPE aleatório
        
        Args:
            prefixo: Prefixo do código
            tamanho: Tamanho da parte aleatória
        
        Returns:
            String com código RUPE único
        """
        while True:
            parte_aleatoria = ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=tamanho)
            )
            codigo = f'{prefixo}-{parte_aleatoria}'
            
            # Verificar se já existe
            if not self.RUPE.objects.filter(codigo=codigo).exists():
                return codigo
    
    def gerar_codigo_checksum(self, ano=None, sequencia=None):
        """
        Gera código RUPE com checksum para validação
        
        Args:
            ano: Ano (padrão: ano atual)
            sequencia: Número sequencial
        
        Returns:
            String com código RUPE incluindo checksum
        """
        codigo_base = self.gerar_codigo_simples(ano, sequencia)
        
        # Calcular checksum simples (soma dos dígitos mod 10)
        digitos = ''.join(filter(str.isdigit, codigo_base))
        checksum = sum(int(d) for d in digitos) % 10
        
        return f'{codigo_base}-{checksum}'
    
    @transaction.atomic
    def criar_rupes_em_lote(self, quantidade, valor=Decimal('5000.00'), 
                           formato='simples', **kwargs):
        """
        Cria múltiplos RUPEs em lote
        
        Args:
            quantidade: Número de RUPEs a criar
            valor: Valor de cada RUPE
            formato: Formato do código ('simples', 'aleatorio', 'checksum')
            **kwargs: Argumentos adicionais para o gerador
        
        Returns:
            Lista de RUPEs criados
        """
        logger.info(f'Criando {quantidade} RUPEs em lote...')
        
        rupes = []
        codigos_criados = set()
        
        for i in range(quantidade):
            # Gerar código baseado no formato
            if formato == 'simples':
                codigo = self.gerar_codigo_simples(**kwargs)
            elif formato == 'aleatorio':
                codigo = self.gerar_codigo_aleatorio(**kwargs)
            elif formato == 'checksum':
                codigo = self.gerar_codigo_checksum(**kwargs)
            else:
                raise ValueError(f'Formato inválido: {formato}')
            
            # Evitar duplicatas na mesma execução
            if codigo in codigos_criados:
                logger.warning(f'Código duplicado gerado: {codigo}. Pulando...')
                continue
            
            codigos_criados.add(codigo)
            
            rupes.append(
                self.Gerador_rupe(codigo=codigo, valor=valor)
            )
            
            # Criar em lotes de 1000 para melhor performance
            if len(rupes) >= 1000:
                self.RUPE.objects.bulk_create(rupes, ignore_conflicts=True)
                logger.info(f'Criados {len(rupes)} RUPEs...')
                rupes = []
        
        # Criar os restantes
        if rupes:
            self.RUPE.objects.bulk_create(rupes, ignore_conflicts=True)
        
        logger.info(f'Total de {quantidade} RUPEs criados com sucesso!')
        
        return codigos_criados
    
    def validar_codigo(self, codigo):
        """
        Valida se um código RUPE é válido
        
        Args:
            codigo: Código RUPE a validar
        
        Returns:
            Boolean indicando se é válido
        """
        if not codigo:
            return False
        
        # Validações básicas
        if not codigo.startswith('RUPE-'):
            return False
        
        partes = codigo.split('-')
        if len(partes) < 3:
            return False
        
        # Se tem checksum, validar
        if len(partes) == 4:
            try:
                checksum = int(partes[-1])
                digitos = ''.join(filter(str.isdigit, '-'.join(partes[:-1])))
                checksum_calculado = sum(int(d) for d in digitos) % 10
                return checksum == checksum_calculado
            except:
                return False
        
        return True
    
    def gerar_relatorio_rupes(self):
        """
        Gera relatório estatístico dos RUPEs
        
        Returns:
            Dicionário com estatísticas
        """
        total = self.RUPE.objects.count()
        usados = self.RUPE.objects.filter(usado=True).count()
        disponiveis = self.RUPE.objects.filter(usado=False).count()
        
        # RUPEs por ano
        from django.db.models.functions import ExtractYear
        rupes_por_ano = self.RUPE.objects.annotate(
            ano=ExtractYear('data_criacao')
        ).values('ano').annotate(
            count=Count('id')
        ).order_by('-ano')
        
        return {
            'total': total,
            'usados': usados,
            'disponiveis': disponiveis,
            'percentual_uso': (usados / total * 100) if total > 0 else 0,
            'por_ano': list(rupes_por_ano)
        }


class RUPEExporter:
    """
    Exportador de RUPEs para diferentes formatos
    """
    
    def __init__(self, rupe_model_name='administrador.RUPE'):
        self.RUPE = apps.get_model(rupe_model_name)
    
    def exportar_csv(self, filepath, apenas_disponiveis=False):
        """
        Exporta RUPEs para arquivo CSV
        
        Args:
            filepath: Caminho do arquivo de saída
            apenas_disponiveis: Se True, exporta apenas RUPEs não usados
        """
        import csv
        
        queryset = self.RUPE.objects.all()
        if apenas_disponiveis:
            queryset = queryset.filter(usado=False)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Cabeçalho
            writer.writerow([
                'Código', 'Valor', 'Usado', 'Data Criação', 
                'Data Uso', 'ID Inscrição'
            ])
            
            # Dados
            for rupe in queryset:
                writer.writerow([
                    rupe.codigo,
                    rupe.valor,
                    'Sim' if rupe.usado else 'Não',
                    rupe.data_criacao.strftime('%Y-%m-%d %H:%M:%S'),
                    rupe.data_uso.strftime('%Y-%m-%d %H:%M:%S') if rupe.data_uso else '',
                    rupe.inscricao_id if rupe.inscricao else ''
                ])
        
        logger.info(f'RUPEs exportados para {filepath}')
    
    def exportar_json(self, filepath, apenas_disponiveis=False):
        """
        Exporta RUPEs para arquivo JSON
        
        Args:
            filepath: Caminho do arquivo de saída
            apenas_disponiveis: Se True, exporta apenas RUPEs não usados
        """
        import json
        
        queryset = self.RUPE.objects.all()
        if apenas_disponiveis:
            queryset = queryset.filter(usado=False)
        
        dados = []
        for rupe in queryset:
            dados.append({
                'codigo': rupe.codigo,
                'valor': str(rupe.valor),
                'usado': rupe.usado,
                'data_criacao': rupe.data_criacao.isoformat(),
                'data_uso': rupe.data_uso.isoformat() if rupe.data_uso else None,
                'inscricao_id': rupe.inscricao_id if rupe.inscricao else None
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        
        logger.info(f'RUPEs exportados para {filepath}')


# ============================================================
# MANAGEMENT COMMAND PARA GERAR RUPES
# Salve como: administrador/management/commands/gerar_rupes.py
# ============================================================

"""
from django.core.management.base import BaseCommand
from administrador.utils.rupe_utils import RUPEGenerator


class Command(BaseCommand):
    help = 'Gera RUPEs em massa'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'quantidade',
            type=int,
            help='Quantidade de RUPEs a gerar'
        )
        parser.add_argument(
            '--valor',
            type=float,
            default=5000.00,
            help='Valor de cada RUPE (padrão: 5000.00)'
        )
        parser.add_argument(
            '--formato',
            type=str,
            choices=['simples', 'aleatorio', 'checksum'],
            default='simples',
            help='Formato do código RUPE'
        )
        parser.add_argument(
            '--exportar',
            type=str,
            help='Exportar códigos para arquivo CSV'
        )
    
    def handle(self, *args, **options):
        from decimal import Decimal
        
        generator = RUPEGenerator()
        
        self.stdout.write('Gerando RUPEs...')
        
        codigos = generator.criar_rupes_em_lote(
            quantidade=options['quantidade'],
            valor=Decimal(str(options['valor'])),
            formato=options['formato']
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✓ {len(codigos)} RUPEs gerados com sucesso!'
            )
        )
        
        if options['exportar']:
            from sua_app.utils.rupe_utils import RUPEExporter
            exporter = RUPEExporter()
            exporter.exportar_csv(options['exportar'], apenas_disponiveis=True)
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ RUPEs exportados para {options["exportar"]}'
                )
            )

# Uso:
# python manage.py gerar_rupes 1000
# python manage.py gerar_rupes 5000 --valor 10000 --formato checksum
# python manage.py gerar_rupes 1000 --exportar rupes_disponiveis.csv
"""