import dataclasses
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.parse

from ont_config import (AUTH, CFG, DEVICE, SAVE, SET_AUTH, XGS, Client, OntError, Plan,
                        Snapshot, constructor, local_url, normalize_idont, normalize_serial,
                        save_backup, load_backup, MAGIC)


INITIAL = Snapshot("HN8010Ts-20", "2D62.A", "V5R022C00S510", "485754431234ABCD", "",
                   ("InternetGatewayDevice.X_HW_XgponDeviceInfo", "", "0", "", ""), "02:11:22:33:44:55")
IDONT = "F2A1B2C3D4E5F6000000"
SERIAL = "41534B591234ABCD"


def js(name, values):
    return "var items=new Array(new " + name + "(" + ",".join(json.dumps(x) for x in values) + "),null);"


def auth_page(state):
    return js("stDevInfo", ("InternetGatewayDevice.DeviceInfo", state.serial, "10", "", "", state.idont)) + '<input name="onttoken" value="TOKEN">'


class FakeClient(Client):
    def __init__(self, state=INITIAL):
        super().__init__("192.168.100.1")
        self.state = state
        self.connected = True
        self.posts = []
        self.reads = 0
        self.drift_at = 0
        self.reject = False
        self.drop_after_write = False
        self.alter_xgs = False

    def read(self):
        self.reads += 1
        if self.reads == self.drift_at:
            self.state = dataclasses.replace(self.state, idont="A" * 20)
        if self.drop_after_write and self.posts:
            raise OntError("Simulated disconnected device")
        return self.state

    def request(self, path, data=None, referer=None):
        if path == AUTH:
            return auth_page(self.state)
        if path == CFG:
            return '<input id="hwonttoken" name="onttoken" value="SAVE-TOKEN">'
        self.posts.append((path, data.copy(), referer))
        if path == SET_AUTH:
            if self.reject:
                return "var ErrCode=7;"
            self.state = dataclasses.replace(self.state, idont=data.get("x.X_HW_PonHexPassword", self.state.idont),
                serial=data.get("x.X_HW_PonSN", self.state.serial))
            if self.alter_xgs:
                self.state = dataclasses.replace(self.state, xgs=(self.state.xgs[0], "unexpected", "0", "", ""))
        return "var ErrCode=0;"


class NormalizationTests(unittest.TestCase):
    def test_idont_14_pads_right_and_preserves_leading_zero(self):
        self.assertEqual(normalize_idont("00112233445566"), "00112233445566000000")

    def test_idont_20_unchanged(self):
        self.assertEqual(normalize_idont(IDONT.lower()), IDONT)

    def test_invalid_idonts(self):
        for value in ("", "0x" + IDONT, "F" * 16, "G" * 20, "F2 A1B2C3D4E5F6", "F" * 72):
            with self.subTest(value=value), self.assertRaises(OntError):
                normalize_idont(value)

    def test_serial_only_prefix_is_converted(self):
        self.assertEqual(normalize_serial("ASKY0012ABCD"), "41534B590012ABCD")
        self.assertEqual(normalize_serial("41534b590012abcd"), "41534B590012ABCD")

    def test_serial_rejects_double_conversion_dummy_and_mac(self):
        for value in ("F" * 16, "0" * 16, "41534B593132333441424344", "88:33:74:00:00:00", "ASKY1234ABCG"):
            with self.subTest(value=value), self.assertRaises(OntError):
                normalize_serial(value)

    def test_local_destinations_only(self):
        self.assertEqual(local_url("127.0.0.1:18081"), "http://127.0.0.1:18081")
        self.assertEqual(local_url("https://192.168.100.1/"), "https://192.168.100.1")
        for value in ("https://example.com", "8.8.8.8", "http://user:pass@192.168.1.1", "http://192.168.1.1/path", "http://192.168.1.1?foo=bar", "169.254.169.254"):
            with self.subTest(value=value), self.assertRaises(OntError):
                local_url(value)

    def test_js_hex_escapes(self):
        s = r'new stDeviceInfo("InternetGatewayDevice.DeviceInfo","x","2D62\x2eA","fw","HN8010Ts\x2d20","a","b","c","d","e","f")'
        values = constructor(s, "stDeviceInfo", (11,))
        self.assertEqual(values[2], "2D62.A")
        self.assertEqual(values[4], "HN8010Ts-20")


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "before.hnont"

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_never_posts(self):
        c = FakeClient()
        self.assertTrue(c.plan(c.read(), IDONT, "ASKY1234ABCD").changed)
        self.assertEqual(c.posts, [])

    def test_unsupported_firmware_blocks_write(self):
        c = FakeClient(dataclasses.replace(INITIAL, firmware="UNKNOWN"))
        with self.assertRaises(OntError):
            c.plan(c.read(), IDONT, "")

    def test_unknown_model_blocks_write(self):
        for model in ("EN8010Ts-20", "HN8010Ts"):
            c = FakeClient(dataclasses.replace(INITIAL, model=model))
            with self.assertRaises(OntError):
                c.plan(c.read(), IDONT)

    def test_confirmation_required(self):
        c = FakeClient()
        with self.assertRaises(OntError):
            c.apply(c.plan(c.read(), IDONT), self.path)
        self.assertEqual(c.posts, [])

    def test_noop_does_not_write_save_or_backup(self):
        c = FakeClient(dataclasses.replace(INITIAL, idont=IDONT))
        c.apply(c.plan(c.read(), IDONT), self.path, confirmed=True)
        self.assertEqual(c.posts, [])
        self.assertFalse(self.path.exists())

    def test_prewrite_drift_blocks(self):
        c = FakeClient()
        plan = c.plan(c.read(), IDONT)
        c.drift_at = 2
        with self.assertRaises(OntError):
            c.apply(plan, self.path, confirmed=True)
        self.assertEqual(c.posts, [])

    def test_backup_failure_prevents_write(self):
        c = FakeClient()
        with patch("ont_config.save_backup", side_effect=OntError("disk failure")):
            with self.assertRaises(OntError):
                c.apply(c.plan(c.read(), IDONT), self.path, confirmed=True)
        self.assertEqual(c.posts, [])

    def test_drift_after_backup_prevents_write(self):
        c = FakeClient()
        plan = c.plan(c.read(), IDONT)
        c.drift_at = 3
        with patch("ont_config.save_backup"):
            with self.assertRaises(OntError):
                c.apply(plan, self.path, confirmed=True)
        self.assertEqual(c.posts, [])

    def test_only_requested_fields_are_posted_and_save_after_readback(self):
        c = FakeClient()
        with patch("ont_config.save_backup") as backup:
            c.apply(c.plan(c.read(), IDONT), self.path, confirmed=True)
        backup.assert_called_once()
        self.assertEqual([p[0] for p in c.posts], [SET_AUTH, SAVE])
        payload = c.posts[0][1]
        self.assertEqual(set(payload), {"x.X_HW_PonHexPassword", "x.X_HW_ForceSet", "x.X_HW_Token"})
        self.assertEqual(list(payload)[-1], "x.X_HW_Token")
        self.assertEqual(c.state.serial, INITIAL.serial)
        self.assertEqual(c.state.xgs, INITIAL.xgs)

    def test_serial_and_idont(self):
        c = FakeClient()
        with patch("ont_config.save_backup"):
            c.apply(c.plan(c.read(), IDONT, "ASKY1234ABCD"), self.path, confirmed=True)
        self.assertEqual(c.state.serial, SERIAL)
        self.assertEqual(c.state.idont, IDONT)

    def test_refused_write_not_saved(self):
        c = FakeClient(); c.reject = True
        with patch("ont_config.save_backup"), self.assertRaises(OntError):
            c.apply(c.plan(c.read(), IDONT), self.path, confirmed=True)
        self.assertEqual(len(c.posts), 1)

    def test_disconnect_reports_uncertainty_and_no_retry(self):
        c = FakeClient(); c.drop_after_write = True
        with patch("ont_config.save_backup"), self.assertRaisesRegex(OntError, "parcialmente"):
            c.apply(c.plan(c.read(), IDONT), self.path, confirmed=True)
        self.assertEqual(len(c.posts), 1)

    def test_xgs_drift_prevents_save(self):
        c = FakeClient(); c.alter_xgs = True
        with patch("ont_config.save_backup"), self.assertRaises(OntError):
            c.apply(c.plan(c.read(), IDONT), self.path, confirmed=True)
        self.assertEqual(len(c.posts), 1)

    def test_masked_reports_and_reprs_do_not_leak_identifiers(self):
        c = FakeClient(dataclasses.replace(INITIAL, idont=IDONT))
        p = c.plan(c.read(), "A" * 20, "ASKY1234ABCD")
        report = repr(c.state) + repr(p) + json.dumps(c.state.masked()) + json.dumps(p.masked())
        for secret in (IDONT, INITIAL.serial, INITIAL.mac, SERIAL):
            self.assertNotIn(secret, report)

    def test_backup_encrypted_roundtrip_and_exclusive_create(self):
        save_backup(self.path, INITIAL)
        raw = self.path.read_bytes()
        self.assertTrue(raw.startswith(MAGIC))
        self.assertNotIn(INITIAL.serial.encode(), raw)
        self.assertNotIn(INITIAL.mac.encode(), raw)
        values = load_backup(self.path)
        self.assertEqual(values["serial"], INITIAL.serial)
        with self.assertRaises(OntError):
            save_backup(self.path, INITIAL)

    def test_restore_factory_identity_and_blank_idont(self):
        save_backup(self.path, INITIAL)
        c = FakeClient(dataclasses.replace(INITIAL, serial=SERIAL, idont=IDONT))
        plan = c.restore_plan(c.read(), load_backup(self.path))
        with patch("ont_config.save_backup"):
            c.apply(plan, Path(self.tmp.name) / "second.hnont", confirmed=True)
        self.assertEqual(c.state, INITIAL)

    def test_backup_cannot_restore_another_ont(self):
        save_backup(self.path, INITIAL)
        c = FakeClient(dataclasses.replace(INITIAL, mac="02:11:22:33:44:66"))
        with self.assertRaises(OntError):
            c.restore_plan(c.read(), load_backup(self.path))


class HttpIntegrationTests(unittest.TestCase):
    def test_login_cookie_read_and_logout_over_http(self):
        posts = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.reply(None)
            def do_POST(self):
                data = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode(), keep_blank_values=True)
                posts.append((self.path, data))
                self.reply(data)
            def reply(self, data):
                if self.path == "/asp/GetRandCount.asp":
                    body = "\ufeffNONCE"
                elif self.path == "/login.cgi":
                    self.assert_payload(data)
                    body = "var pageName = 'index.asp';"
                elif self.path == DEVICE:
                    body = js("stDeviceInfo", ("InternetGatewayDevice.DeviceInfo", INITIAL.serial, INITIAL.hardware,
                        INITIAL.firmware, INITIAL.model, "HWTC", "release", INITIAL.mac, "description", "manufacture", ""))
                elif self.path == AUTH:
                    body = auth_page(INITIAL)
                elif self.path == XGS:
                    body = js("stXDevInfo", INITIAL.xgs)
                else:
                    body = "OK"
                self.send_response(200)
                if self.path == "/login.cgi":
                    self.send_header("Set-Cookie", "sid=synthetic; Path=/")
                self.end_headers();self.wfile.write(body.encode())
            def assert_payload(self, data):
                if data.get("x.X_HW_Token") != ["NONCE"] or "Cookie=body:Language:english:id=-1" not in self.headers.get("Cookie", ""):
                    raise AssertionError("invalid login")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True);t.start()
        try:
            c = Client("127.0.0.1:" + str(server.server_port))
            c.login("telecomadmin", "test-only-password")
            self.assertEqual(c.read(), INITIAL)
            c.close()
            self.assertFalse(c.connected)
            self.assertEqual([p[0] for p in posts], ["/asp/GetRandCount.asp", "/login.cgi"])
        finally:
            server.shutdown();server.server_close();t.join()


if __name__ == "__main__":
    unittest.main()
