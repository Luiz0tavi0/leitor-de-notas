import re
from datetime import datetime
from leitordenotas.builder.builder_reader_base import BuilderReaderBase


class ClearReaderBuilder(BuilderReaderBase):
    NEGOCIACOES_PATTERN = '(1-BOVESPA\n)([CV]\s)(VISTA\s|FRACIONARIO\s)([A-Z0-9 ]+)(\n\#\n|\n)([0-9]+\n)([0-9.]+,[0-9]{2}\n)([0-9.]+,[0-9]{2}\n)([CD]\n)'
    RESUMO_NEGOCIOS_PATTERN = '(([0-9.]+,[0-9]{2}\s){8})(Resumo dos Negócios)'
    RESUMO_FINANCEIRO_PATTERN = '([0-9.]+,[0-9]{2})\n([A-Za-z0-9 íóçõã\.\,\/]+\n)([CD]\n|)'
    NUMERO_NOTA_PATTERN = '(Nr. nota\n)([0-9]+)'
    DATA_NOTA_PATTERN = '(Data pregão\n)([0-9\/]+)'

    def build_negociacoes(self):
        self.parsed_data['negocios'] = []
        for negociacao in re.findall(self.NEGOCIACOES_PATTERN, self.raw_text):
            self.parsed_data['negocios'].append(
                {
                    'titulo': self.clean_string(negociacao[3]),
                    'qtd': self.parse_real(negociacao[5]),
                    'preco': self.parse_real(negociacao[6], dc=negociacao[8]),
                    'valor_operacao': self.parse_real(negociacao[7], dc=negociacao[8]),
                    'obs': self.clean_string(negociacao[4])
                }
            )

    def build_resumo_negocios(self):
        extracted = re.findall(self.RESUMO_NEGOCIOS_PATTERN, self.raw_text)
        values = extracted[0][0].split()
        self.parsed_data['resumo_negocios'] = {
            'debentures': self.parse_real(values[0], dc='D'),
            'vendas_vista': self.parse_real(values[1], dc='C'),
            'compras_vista': self.parse_real(values[2], dc='D'),
            'opcoes_compras': self.parse_real(values[3], dc='D'),
            'opcoes_vendas': self.parse_real(values[4], dc='C'),
            'operacoes_termo': self.parse_real(values[5], dc='D'),
            'valor_operacoes_titulos_publicos': self.parse_real(values[6], dc='D'),
            'valor_operacoes': self.parse_real(values[7], dc='D')
        }

    def build_resumo_financeiro(self):
        clean_text = re.sub(' R\$[0-9.]+,[0-9]{2}', '', self.raw_text)
        extracted = re.findall(self.RESUMO_FINANCEIRO_PATTERN, clean_text)
        extracted.reverse()
        self.parsed_data['resumo_financeiro'] = {
            'clearing': {
                'valor_liquido_operacoes': self.parse_real(extracted[14][0], dc=extracted[14][2]),
                'taxa_liquidacao': self.parse_real(extracted[13][0], dc=extracted[13][2]),
                'taxa_registro': self.parse_real(extracted[12][0], dc=extracted[12][2]),
                'total_cblc': self.parse_real(extracted[15][0], dc=extracted[15][2]),
            },
            'bolsa': {
                'taxa_termo_opcoes': self.parse_real(extracted[10][0], dc=extracted[10][2]),
                'taxa_ana': self.parse_real(extracted[9][0], dc=extracted[9][2]),
                'emolumentos': self.parse_real(extracted[8][0], dc=extracted[8][2]),
                'total_bovespa': self.parse_real(extracted[11][0], dc=extracted[11][2])
            },
            'custos_operacionais': {
                'taxa_operacional': self.parse_real(extracted[6][0], dc=extracted[6][2]),
                'execucao': self.parse_real(extracted[5][0], dc=extracted[5][2]),
                'taxa_custodia': self.parse_real(extracted[4][0], dc=extracted[4][2]),
                'impostos': self.parse_real(extracted[3][0], dc=extracted[3][2]),
                'irrf': self.parse_real(extracted[2][0], dc=extracted[2][2]),
                'outros': self.parse_real(extracted[1][0], dc=extracted[1][2]),
                'total_custos_despesas': self.parse_real(extracted[7][0], dc=extracted[7][2])
            }
        }

        self.parsed_data['total'] = self.parse_real(extracted[0][0], dc=extracted[0][2])

    def build_info(self):
        numero = re.search(self.NUMERO_NOTA_PATTERN, self.raw_text).group(2)
        self.parsed_data['numero'] = numero
        data_pregao = re.search(self.DATA_NOTA_PATTERN, self.raw_text).group(2)
        self.parsed_data['data_pregao'] = datetime.strptime(data_pregao, "%d/%m/%Y")

    def apropriacao_de_custos(self):
        custos_operacionais = self.parsed_data['resumo_financeiro']['custos_operacionais']['total_custos_despesas']

        custos_clearing = self.parsed_data['resumo_financeiro']['clearing']['taxa_registro'] + \
                          self.parsed_data['resumo_financeiro']['clearing']['taxa_liquidacao']
        custos_bolsa = sum(self.parsed_data['resumo_financeiro']['bolsa'].values())

        self.parsed_data['resumo_financeiro']['custo_da_nota'] = \
            (custos_clearing + custos_bolsa + custos_operacionais) - \
            self.parsed_data['resumo_financeiro']['custos_operacionais']['irrf']
        custo_a_apropriar = self.parsed_data['resumo_financeiro']['custo_da_nota']
        fracao_ideal_ = self.parsed_data['resumo_financeiro']['custo_da_nota'] / self.parsed_data['resumo_negocios'][
            'valor_operacoes']
        self.parsed_data['negocios'].sort(key=lambda n: abs(n['valor_operacao']), reverse=True)
        print(f'Custo a apropriar da nota {self.parsed_data["numero"]} -> {custo_a_apropriar}')
        for negocio in self.parsed_data['negocios']:
            ajuste = abs(round(negocio['valor_operacao'] * fracao_ideal_))
            novo_preco = negocio['preco'] - ajuste
            custo_a_apropriar += ajuste
            negocio.update({'preco_ajustado': novo_preco})
            novo_valor_operacao = negocio['valor_operacao'] - ajuste
            negocio.update({'valor_operacao_ajustado': novo_valor_operacao})

        if custo_a_apropriar > 0:
            novo_preco = self.parsed_data['negocios'][-1]['preco'] - abs(custo_a_apropriar)
            novo_valor_operacao = self.parsed_data['negocios'][-1]['valor_operacao'] - abs(custo_a_apropriar)
            self.parsed_data['negocios'][-1].update(
                {'preco_ajustado': novo_preco,
                 'valor_operacao_ajustado': novo_valor_operacao}
            )

