import tempfile
import unittest
from pathlib import Path
from persistence import SQLiteRepository
from services import ClinicService,Stock
from assistant import ClinicAssistant
from expand_inventory import expand


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.repo=SQLiteRepository(Path(self.tmp.name)/'stock.sqlite3')
        self.repo.add_user(dict(email='owner@example.test',role='owner',empresa_id='a'))
        self.service=ClinicService(self.repo,'a')
        for name,quantity,minimum,unit in [('Luvas',12,5,'Caixa'),('Máscaras',3,5,'Caixa'),('Sugadores',0,2,'Pacote'),('Gaze no mínimo',2,2,'Pacote')]:
            self.service.save_stock(Stock(nome=name,categoria='Material',unidade=unit,quantidade=quantity,minimo=minimum))

    def test_question_em_falta_lists_only_zero_and_low(self):
        response=ClinicAssistant(self.repo,'a').reply('quais itens estao em falta no estoque?')
        text=response['resposta']
        self.assertFalse(response['gerado_por_llm'])
        self.assertIn('3 itens precisam de reposição',text)
        self.assertIn('Esgotados',text);self.assertIn('No mínimo ou abaixo dele',text)
        self.assertIn('Sugadores: 0 pacotes',text);self.assertIn('Máscaras: 3 caixas',text)
        self.assertIn('Faltam 2 caixas',text)
        self.assertNotIn('Luvas',text);self.assertIn('Gaze no mínimo',text);self.assertIn('No ponto de reposição',text)
        self.assertEqual(ClinicAssistant(self.repo,'b').reply('itens em falta no estoque')['resposta'],'Ainda não há materiais cadastrados no estoque da sua clínica.')

    def test_zero_only_adequate_and_general_inventory(self):
        agent=ClinicAssistant(self.repo,'a')
        zero=agent.reply('Quais itens estão esgotados no estoque?')['resposta']
        self.assertIn('Sugadores',zero);self.assertNotIn('Máscaras',zero)
        adequate=agent.reply('Quais itens estão em dia no estoque?')['resposta']
        self.assertIn('Luvas',adequate);self.assertNotIn('Gaze no mínimo',adequate);self.assertNotIn('Máscaras',adequate)
        all_items=agent.reply('Mostre o estoque da clínica')['resposta']
        for name in ('Luvas','Máscaras','Sugadores','Gaze no mínimo'):self.assertIn(name,all_items)

    def test_expansion_preserves_balances_and_does_not_duplicate(self):
        original=self.service.stocks()
        result=expand(self.repo,'a')
        self.assertEqual(result['itens_adicionados'],20)
        for item in original:
            current=next(s for s in self.service.stocks() if s['id']==item['id'])
            self.assertEqual(item,current)
        self.assertEqual(expand(self.repo,'a')['itens_adicionados'],0)
        self.assertEqual(self.repo.list('stock','b'),[])

    def test_zero_minimum_does_not_invent_purchase_or_negative_shortage(self):
        self.service.save_stock(Stock(nome='Material sem mínimo',categoria='Material',unidade='Unidade',quantidade=0,minimo=0))
        text=ClinicAssistant(self.repo,'a').reply('Quais itens estão em falta no estoque?')['resposta']
        self.assertIn('Defina um mínimo',text)
        self.assertNotIn('Faltam 0',text)
        self.assertIn('nenhuma compra ou entrada foi registrada',text)
