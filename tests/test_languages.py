"""Exercise real onboarding and all three intakes in every supported language."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from bot import create_bot, FLOWS
from bot_text import TEXT
from privacy.onboarding import UI, Store, load_policy, revision, render
from test_privacy import FakeBot, fixture

ORIGINAL = {'uk', 'pl', 'ru', 'en', 'de', 'es', 'pt'}

class LanguageTests(unittest.TestCase):
    def test_original_seven_and_recovery_language_are_complete(self):
        self.assertTrue(ORIGINAL <= UI.keys())
        self.assertEqual(set(UI), set(TEXT))
        self.assertIn('uz', UI)
        example=json.loads(Path('privacy/policy.example.json').read_text())
        self.assertEqual(set(example['notices']), set(UI))
        with self.assertRaises(ValueError): load_policy(None, json.dumps(example))
        for lang in UI:
            with self.subTest(lang=lang):
                self.assertEqual(set(UI[lang]), set(UI['uk']))
                self.assertTrue(all(UI[lang].values()))
                for kind, steps in FLOWS.items():
                    self.assertEqual(len(TEXT[lang][kind+'_q']), len(steps))
                self.assertIn(UI[lang]['policy']+':', render(fixture(), lang))

    def test_each_language_each_intake_keeps_selected_locale(self):
        for lang in UI:
            for kind in FLOWS:
                with self.subTest(lang=lang, kind=kind), TemporaryDirectory() as tmp:
                    path=Path(tmp)/'policy.json'; db=Path(tmp)/'store.sqlite'
                    policy=fixture(); path.write_text(json.dumps(policy))
                    fake=FakeBot(); create_bot(None,path,db,fake)
                    # Device language differs deliberately: callback choice must persist.
                    def msg(text):
                        return NS(text=text,chat=NS(id=42,type='private'),from_user=NS(id=42,language_code='uk',is_bot=False))
                    fake.handle(msg('/start'))
                    fake.callback(NS(id='test',data=f'p:{revision(policy)}:{lang}:yes',message=msg(''),from_user=NS(id=42)))
                    self.assertTrue(fake.sent[-1][1].startswith(TEXT[lang]['menu']))
                    keyboard=json.loads(fake.sent[-1][2]['reply_markup'].to_json())['keyboard']
                    self.assertIn(TEXT[lang][kind], str(keyboard))
                    fake.handle(msg('/status')); self.assertEqual(fake.sent[-1][1],TEXT[lang]['no_apps'])
                    fake.handle(msg('/arrival')); self.assertEqual(fake.sent[-1][1],TEXT[lang]['no_plan'])
                    fake.handle(msg(TEXT[lang][kind]))
                    for index,(field,_) in enumerate(FLOWS[kind]):
                        self.assertIn(TEXT[lang][kind+'_q'][index],fake.sent[-1][1])
                        if field=='phone':
                            fake.handle(msg('invalid'))
                            self.assertEqual(fake.sent[-1][1],TEXT[lang]['phone'])
                        fake.handle(msg('+48123456789' if field=='phone' else 'SYNTHETIC'))
                    self.assertEqual(fake.sent[-2][1],TEXT[lang]['saved'])
                    store=Store(db,policy)
                    try:
                        self.assertEqual(store.db.execute('SELECT count(*) FROM applications').fetchone()[0],1)
                        self.assertEqual(store.db.execute('SELECT locale FROM privacy_events ORDER BY id DESC LIMIT 1').fetchone()[0],lang)
                    finally: store.close()
                    fake.handle(msg('/withdraw')); self.assertEqual(fake.sent[-1][1],UI[lang]['stopped'])
                    fake.handle(msg('/delete_data')); self.assertTrue(fake.sent[-1][1].startswith(UI[lang]['deleted']))

    def test_missing_restored_translation_blocks_onboarding(self):
        for lang in ORIGINAL:
            with self.subTest(lang=lang):
                policy=fixture(); del policy['notices'][lang]
                with self.assertRaises((ValueError,KeyError)): load_policy(None,json.dumps(policy))
