"""Read-only extraction from the Askey installer and summary web interfaces."""
from dataclasses import dataclass, field
import http.cookiejar
import re
import urllib.parse
import xml.etree.ElementTree as ET

from ont_config import Client, OntError, normalize_serial

INSTALLER = "/me_install.asp"
LOGIN = "/cgi-bin/te_acceso_router.cgi"
ADV_LOGIN = "/cgi-bin/cbCheckLogin.xml"
SUMMARY = "/cgi-bin/cbGetSummary.xml"
LOGOUT = "/cgi-bin/cbCheckLogout.xml"
ALLOWED = {("/", False), (INSTALLER, False), (LOGIN, True), (ADV_LOGIN, True), (SUMMARY, True), (LOGOUT, True)}


def xml(text):
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        raise OntError("XML del Askey no admitido.")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise OntError("Respuesta del Askey no compatible. No se ha modificado su configuración.") from None


def scramble(value):
    return "".join(chr(ord(c) ^ 31) for c in value)


def hex_var(page, name, size):
    m = re.search(r"\bvar\s+" + re.escape(name) + r"\s*=\s*(['\"])([0-9a-fA-F]*)\1\s*;", page)
    if not m or len(m.group(2)) != size:
        raise OntError("No se ha podido leer el identificador del instalador del Askey. No se usará un valor incompleto.")
    return m.group(2).upper()


@dataclass(frozen=True)
class AskeyData:
    model: str
    firmware: str
    technology: str
    idont: str = field(repr=False)
    serial: str = field(repr=False)

    @property
    def serial_hex(self):
        return normalize_serial(self.serial)

    def masked(self):
        return {"origen": "Askey", "modelo": self.model, "firmware": self.firmware, "tecnología": self.technology,
                "idont": self.idont[:4] + "*" * 16, "serial": self.serial[:4] + "********",
                "configuración del Askey": "solo lectura; sin cambios"}


class AskeyClient(Client):
    def request(self, path, data=None, referer=None):
        # Hard allowlist: even a programming error cannot issue cbSet*, Apply,
        # SaveConfig, firmware or reboot calls through this client.
        if (path, data is not None) not in ALLOWED:
            raise OntError("Esta herramienta solo permite leer el Askey. Petición bloqueada.")
        return super().request(path, data, referer or "/instalacion")

    def login(self, username, password):
        if self.connected:
            raise OntError("Ya hay una sesión abierta en el Askey.")
        if not username or not password:
            raise OntError("Introduce usuario y contraseña del Askey.")
        self.request(INSTALLER)
        self.request(LOGIN, {"Password": password, "curWebPage": INSTALLER,
                            "loginUsername": scramble(username), "loginPassword": scramble(password)})
        reply = xml(self.request(ADV_LOGIN, {"rqUsername": scramble(username), "rqPasswd": scramble(password), "rqTimeout": "600"}))
        if reply.findtext(".//Result") != "0":
            self.jar.clear()
            raise OntError("El Askey ha rechazado el acceso. Comprueba sus credenciales; no se reintentará automáticamente.")
        session = reply.findtext(".//SessionID")
        if not session or len(session) > 1024:
            self.jar.clear()
            raise OntError("No se ha recibido una sesión válida del Askey.")
        host = urllib.parse.urlsplit(self.root).hostname
        for name, value in (("SessionID", session), ("SessionStatus", "Valid"),
                            ("LoginName", scramble(username)), ("TimeOut", "600")):
            self.jar.set_cookie(http.cookiejar.Cookie(0, name, urllib.parse.quote(value), None, False,
                host, False, False, "/", True, False, None, True, None, None, {}, False))
        self.connected = True

    def read(self):
        if not self.connected:
            raise OntError("Primero inicia sesión en el Askey.")
        summary = xml(self.request(SUMMARY, {}))
        if summary.findtext(".//Result") != "0":
            raise OntError("No se puede leer el resumen del Askey.")
        model = summary.findtext(".//DeviceModel") or ""
        manufacturer = summary.findtext(".//DeviceManufacturer") or ""
        if "askey" not in manufacturer.lower() or not re.fullmatch(r"RTF831[67]VW(?:-D1)?(?:-SX)?", model):
            raise OntError("El equipo no se identifica como un Askey WiFi 7 de la familia admitida.")
        serial_hex = normalize_serial(summary.findtext(".//OnuSerialNumber") or "")
        serial = "ASKY" + serial_hex[8:]
        installer = self.request(INSTALLER)
        gp = hex_var(installer, "gponPw", 20)
        mode = re.search(r"\bvar\s+isXGSPON\s*=\s*['\"]([01])['\"]", installer)
        if not mode:
            raise OntError("No se ha podido determinar el modo GPON/XGS-PON del Askey.")
        if mode.group(1) != "1":
            raise OntError("El Askey indica GPON. Esta configuración de referencia requiere XGS-PON; no se importarán valores automáticamente.")
        xgs = hex_var(installer, "xgsponRegId", 72)
        if xgs[:20] != gp or any(c != "0" for c in xgs[20:]):
            raise OntError("Las identidades GPON y XGS del Askey no coinciden con el formato probado. Importación cancelada para no escoger un valor incorrecto.")
        if gp in ("0" * 20, "F" * 20):
            raise OntError("El Askey no contiene un IdONT utilizable para esta importación.")
        return AskeyData(model, summary.findtext(".//SWVersion") or "desconocido", "XGS-PON", gp, serial)

    def close(self):
        if self.connected:
            try:
                self.request(LOGOUT, {})
            except OntError:
                pass
        self.connected = False
        self.jar.clear()
