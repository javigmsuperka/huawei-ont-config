import tkinter as tk
import unittest
from unittest.mock import patch
from app import App
from test_core import INITIAL, IDONT, FakeClient
from askey import AskeyData


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root)
        self.app.client = FakeClient()
        self.app.snapshot = INITIAL

    def tearDown(self):
        self.root.destroy()

    def test_review_enables_apply_and_editing_invalidates_plan(self):
        self.app.idont.set(IDONT)
        self.app.preview()
        self.assertIsNotNone(self.app.prepared)
        self.assertEqual(str(self.app.apply_button['state']), 'normal')
        self.app.serial.set('ASKY1234ABCD')
        self.assertIsNone(self.app.prepared)
        self.assertEqual(str(self.app.apply_button['state']), 'disabled')

    def test_cancelled_confirmation_never_writes_or_creates_backup(self):
        self.app.idont.set(IDONT)
        self.app.preview()
        with patch('app.messagebox.askyesno', return_value=False), patch('app.filedialog.asksaveasfilename') as dialog:
            self.app.apply()
        dialog.assert_not_called()
        self.assertEqual(self.app.client.posts, [])

    def test_invalid_input_cannot_enable_apply(self):
        self.app.idont.set('not-an-idont')
        with patch('app.messagebox.showerror'):
            self.app.preview()
        self.assertIsNone(self.app.prepared)
        self.assertEqual(str(self.app.apply_button['state']), 'disabled')

    def test_askey_extraction_fills_fields_without_enabling_write(self):
        data = AskeyData('RTF8317VW-SX', 'test', 'XGS-PON', IDONT, 'ASKY1234ABCD')
        def immediate(fn, done):
            done(fn())
        self.app.work = immediate
        with patch('app.AskeyLoginDialog') as dialog, patch('app.AskeyClient') as factory:
            dialog.return_value.result = ('192.168.1.1', '1234', 'synthetic-password')
            factory.return_value.read.return_value = data
            self.app.import_askey()
            factory.return_value.close.assert_called_once()
        self.assertEqual(self.app.idont.get(), IDONT)
        self.assertEqual(self.app.serial.get(), 'ASKY1234ABCD')
        self.assertIsNone(self.app.prepared)
        self.assertEqual(self.app.client.posts, [])
        self.assertEqual(str(self.app.apply_button['state']), 'disabled')


if __name__ == '__main__':
    unittest.main()
