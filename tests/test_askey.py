import dataclasses
from unittest import TestCase
from unittest.mock import patch
from ont_config import Client, OntError
from askey import AskeyClient, AskeyData, INSTALLER, LOGIN, ADV_LOGIN, SUMMARY, LOGOUT, scramble
from test_core import IDONT


def summary(serial="ASKY1234ABCD", model="RTF8317VW-SX", manufacturer="Askey"):
    return '<Response><Result>0</Result><DeviceModel>' + model + '</DeviceModel><DeviceManufacturer>' + manufacturer + '</DeviceManufacturer><OnuSerialNumber>' + serial + '</OnuSerialNumber><SWVersion>synthetic-firmware</SWVersion></Response>'


def installer(gp=IDONT, xgs=None, mode="1"):
    xgs = xgs if xgs is not None else gp.ljust(72, "0")
    return "var gponPw='" + gp + "';var xgsponRegId='" + xgs + "';var isXGSPON='" + mode + "';"


class AskeyTests(TestCase):
    def test_login_read_logout_use_only_read_and_session_endpoints(self):
        c = AskeyClient("127.0.0.1:18082")
        history = []
        def response(path, data=None, referer=None):
            history.append((path, data))
            if path == ADV_LOGIN:
                self.assertEqual(data['rqUsername'], scramble('1234'))
                self.assertEqual(data['rqPasswd'], scramble('test-password'))
                return '<Response><Result>0</Result><SessionID>test-session</SessionID></Response>'
            if path == SUMMARY:
                return summary()
            if path == INSTALLER:
                return installer()
            return 'OK'
        with patch.object(Client, 'request', side_effect=response):
            c.login('1234', 'test-password')
            data = c.read()
            self.assertEqual(data.idont, IDONT)
            self.assertEqual(data.serial, 'ASKY1234ABCD')
            self.assertEqual(data.serial_hex, '41534B591234ABCD')
            c.close()
        self.assertEqual([x[0] for x in history], [INSTALLER, LOGIN, ADV_LOGIN, SUMMARY, INSTALLER, LOGOUT])
        self.assertFalse(c.connected)
        self.assertFalse(list(c.jar))

    def read_with(self, markup, overview=None):
        c = AskeyClient('192.168.1.1'); c.connected = True
        with patch.object(Client, 'request', side_effect=lambda path, *args, **kw: (overview or summary()) if path == SUMMARY else markup):
            return c.read()

    def test_preserves_full_twenty_characters_and_leading_zeroes(self):
        value = '00112233445566778899'
        self.assertEqual(self.read_with(installer(gp=value)).idont, value)

    def test_mismatching_gp_and_xgs_blocks_import(self):
        with self.assertRaisesRegex(OntError, 'no coinciden'):
            self.read_with(installer(xgs='A' * 20 + '0' * 52))

    def test_nonzero_xgs_tail_blocks_import(self):
        with self.assertRaises(OntError):
            self.read_with(installer(xgs=IDONT + '0' * 51 + '1'))

    def test_wrong_lengths_block_import(self):
        for text in (installer(gp='F' * 14), installer(xgs='F' * 20), 'login form'):
            with self.subTest(text=text), self.assertRaises(OntError):
                self.read_with(text)

    def test_gpon_mode_not_silently_imported(self):
        with self.assertRaisesRegex(OntError, 'requiere XGS-PON'):
            self.read_with(installer(mode='0'))

    def test_dummy_idont_not_imported(self):
        for value in ('0' * 20, 'F' * 20):
            with self.assertRaises(OntError):
                self.read_with(installer(gp=value))

    def test_model_and_vendor_are_checked(self):
        for overview in (summary(model='other-router'), summary(manufacturer='other-vendor')):
            with self.assertRaises(OntError):
                self.read_with(installer(), overview)

    def test_mac_is_not_accepted_as_optical_serial(self):
        with self.assertRaises(OntError):
            self.read_with(installer(), summary(serial='02:11:22:33:44:55'))

    def test_incorrect_password_is_not_retried(self):
        c = AskeyClient('192.168.1.1')
        with patch.object(Client, 'request', return_value='<Response><Result>1</Result></Response>') as wire:
            with self.assertRaisesRegex(OntError, 'rechazado'):
                c.login('1234', 'wrong-password')
        self.assertEqual(wire.call_count, 3)
        self.assertFalse(c.connected)

    def test_configuration_endpoints_are_hard_blocked(self):
        c = AskeyClient('192.168.1.1')
        with patch.object(Client, 'request') as wire:
            for path in ('/cgi-bin/cbSaveConfig.xml', '/cgi-bin/cbSetWifi.xml', '/cgi-bin/te_mm.cmd?action=Apply', '/reboot.asp'):
                with self.subTest(path=path), self.assertRaises(OntError):
                    c.request(path, {})
            wire.assert_not_called()

    def test_masked_output_and_repr_hide_values(self):
        data = AskeyData('RTF8317VW-SX', 'synthetic', 'XGS-PON', IDONT, 'ASKY1234ABCD')
        output = repr(data) + str(data.masked())
        self.assertNotIn(IDONT, output)
        self.assertNotIn('ASKY1234ABCD', output)

    def test_xml_declarations_are_rejected(self):
        with self.assertRaises(OntError):
            self.read_with(installer(), '<!DOCTYPE x [<!ENTITY x "y">]><Response/>')
