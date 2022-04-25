import re

import fitz

from leitordenotas.builder.clear_reader_builder import ClearReaderBuilder
from leitordenotas.builder.easynvest_reader_builder import EasynvestReaderBuilder
from leitordenotas.builder.inter_reader_builder import InterReaderBuilder
from leitordenotas.models import NotaDeCorretagem, NotasDeCorretagem


class NotaDeCorretagemReader:
    def __init__(self, filepath: str, parser=None):
        self.filepath = filepath
        self.parser = parser
        self.raw_text = ''
        self.notas_de_corretagem = {'notas': []}

    def read(self, parser=None) -> NotasDeCorretagem:

        doc = fitz.open(self.filepath)

        for page in doc:
            pdf_text = page.get_text("text")
            self.raw_text = re.sub('[ \u00A0]+', ' ', pdf_text)

            if not parser:
                if re.search('(CLEAR CORRETORA - GRUPO XP)', self.raw_text):
                    parser = ClearReaderBuilder
                elif re.search('(Easynvest - Título Corretora de Valores SA)', self.raw_text):
                    parser = EasynvestReaderBuilder
                else:
                    parser = InterReaderBuilder
            self.notas_de_corretagem['notas'].append(NotaDeCorretagem(**parser(self.raw_text).build()))
        return NotasDeCorretagem(**self.notas_de_corretagem)
