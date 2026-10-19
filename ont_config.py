"""HN8010Ts-20 web client. No SSH, firmware changes, or automatic reboots."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from html.parser import HTMLParser
import http.cookiejar
import http.client
import ipaddress
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

VERSION = "0.2.0"
AUTH = "/html/amp/ontauth/passwordcommon.asp"
DEVICE = "/html/ssmp/deviceinfo/deviceinfocut.asp"
XGS = "/html/amp/ontauth/xgponauth_func.asp"
CFG = "/html/ssmp/cfgfile/cfgfile.asp"
SET_AUTH = "/html/amp/ontauth/set.cgi?x=InternetGatewayDevice.DeviceInfo&RequestFile=html/amp/ontauth/passwordcommon.asp"
SAVE = "/html/ssmp/cfgfile/set.cgi?x=InternetGatewayDevice.X_HW_DEBUG.SSP.DBSave&RequestFile=html/ssmp/cfgfile/cfgfile.asp"
SUPPORTED = {("HN8010Ts-20", "2D62.A", "V5R022C00S462"),
             ("HN8010Ts-20", "2D62.A", "V5R022C00S510")}


class OntError(Exception):
    """Safe, user-facing error. Never include response bodies or credentials."""


def normalize_idont(value: str) -> str:
    value = value.strip()
    if len(value) not in (14, 20) or not re.fullmatch(r"[0-9a-fA-F]+", value):
        raise OntError("El IdONT debe tener 14 o 20 caracteres hexadecimales, sin espacios ni 0x.")
    return value.upper().ljust(20, "0")


def normalize_serial(value: str) -> str:
    value = value.strip().upper()
    if re.fullmatch(r"ASKY[0-9A-F]{8}", value):
        value = "41534B59" + value[4:]
    if not re.fullmatch(r"41534B59[0-9A-F]{8}", value):
        raise OntError("Usa el serial óptico del Askey: ASKY y 8 caracteres hexadecimales, o sus 16 caracteres hexadecimales.")
    return value


def local_url(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = "http://" + value
    p = urllib.parse.urlsplit(value)
    if p.scheme not in ("http", "https") or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment:
        raise OntError("Introduce solo la IP local de la ONT, con puerto opcional.")
    try:
        ip = ipaddress.IPv4Address(p.hostname)
        port = p.port
    except (ValueError, TypeError):
        raise OntError("Se necesita una dirección IPv4 local, no un nombre de dominio.") from None
    if not any(ip in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")):
        raise OntError("Solo se permiten IP privadas o un túnel en localhost.")
    if port is not None and not 1 <= port <= 65535:
        raise OntError("Puerto no válido.")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, "", "", ""))


class LocalRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin: str):
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlsplit(newurl)
        if urllib.parse.urlunsplit((p.scheme, p.netloc, "", "", "")) != self.origin:
            raise OntError("La ONT ha redirigido a otro destino. Acceso cancelado.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def constructor(page: str, name: str, count: tuple[int, ...]) -> tuple[str, ...]:
    m = re.search(r"\bnew\s+" + re.escape(name) + r"\s*\((.*?)\)", page, re.S)
    if not m:
        raise OntError("No reconozco la respuesta del firmware. No se ha modificado nada.")
    parts = re.findall(r'"((?:\\.|[^"\\])*)"', m.group(1))
    if len(parts) not in count:
        raise OntError("Formato de datos no compatible con esta versión de la herramienta.")
    try:
        values = tuple(json.loads('"' + re.sub(r"\\x([0-9a-fA-F]{2})", r"\\u00\1", x) + '"') for x in parts)
    except (ValueError, json.JSONDecodeError):
        raise OntError("La respuesta contiene un formato de texto no admitido.") from None
    if values[0] not in ("InternetGatewayDevice.DeviceInfo", "InternetGatewayDevice.X_HW_XgponDeviceInfo"):
        raise OntError("Dominio de configuración inesperado.")
    return values


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input":
            for key in (a.get("name"), a.get("id")):
                if key:
                    self.values[key] = a.get("value", "")


def token(page: str) -> str:
    p = Inputs()
    p.feed(page)
    result = p.values.get("onttoken") or p.values.get("hwonttoken")
    if not result or len(result) > 1024:
        raise OntError("No se ha encontrado el token de sesión. Vuelve a conectar.")
    return result


@dataclass(frozen=True)
class Snapshot:
    model: str
    hardware: str
    firmware: str
    serial: str = field(repr=False)
    idont: str = field(repr=False)
    xgs: tuple[str, ...] = field(repr=False)
    mac: str = field(repr=False)

    @property
    def supported(self):
        return (self.model, self.hardware, self.firmware) in SUPPORTED

    def masked(self):
        return {"modelo": self.model, "hardware": self.hardware, "firmware": self.firmware,
                "serial": self.serial[:8] + "********", "idont": self.idont[:4] + "*" * max(0, len(self.idont) - 4) if self.idont else "vacío",
                "xgs_registration_id": "vacío" if not self.xgs[1] else "configurado (no se modifica)",
                "compatible_para_escritura": self.supported}


@dataclass(frozen=True)
class Plan:
    before: Snapshot
    idont: str = field(repr=False)
    serial: str = field(repr=False)
    restore: bool = False

    @property
    def changed(self):
        return self.before.idont != self.idont or self.before.serial != self.serial

    def masked(self):
        return {"IdONT GPON": "cambiar" if self.idont != self.before.idont else "sin cambios",
                "serial óptico": "cambiar" if self.serial != self.before.serial else "sin cambios",
                "XGS Registration ID": "se conserva", "reinicio automático": "no"}


class Client:
    def __init__(self, address: str, timeout=12):
        self.root = local_url(address)
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self.jar), LocalRedirects(self.root))
        self.connected = False

    def request(self, path: str, data=None, referer=None) -> str:
        headers = {"User-Agent": "HuaweiONTConfig/" + VERSION, "Referer": self.root + (referer or "/"), "Origin": self.root}
        encoded = None if data is None else urllib.parse.urlencode(data).encode("ascii")
        if encoded is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            with self.opener.open(urllib.request.Request(self.root + path, encoded, headers), timeout=self.timeout) as r:
                raw = r.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise OntError("Respuesta demasiado grande. Operación cancelada.")
                return raw.decode("utf-8-sig")
        except OntError:
            raise
        except (OSError, ValueError, UnicodeError, urllib.error.URLError, http.client.HTTPException):
            raise OntError("No se puede completar la petición a la ONT. Comprueba IP, conexión y sesión.") from None

    def login(self, username: str, password: str):
        if self.connected:
            raise OntError("Cierra la sesión anterior antes de iniciar otra.")
        self.request("/")
        nonce = self.request("/asp/GetRandCount.asp", {}).strip()
        if not nonce or len(nonce) > 1024 or "<" in nonce:
            raise OntError("Respuesta de autenticación no compatible.")
        host = urllib.parse.urlsplit(self.root).hostname
        self.jar.set_cookie(http.cookiejar.Cookie(0, "Cookie", "body:Language:english:id=-1", None, False,
            host, False, False, "/", True, False, None, True, None, None, {}, False))
        result = self.request("/login.cgi", {"UserName": username, "PassWord": base64.b64encode(password.encode()).decode(),
            "Language": "english", "x.X_HW_Token": nonce})
        if not re.search(r"(?:var\s+)?pageName\s*=\s*['\"]index\.asp['\"]", result):
            self.jar.clear()
            raise OntError("Inicio de sesión rechazado. Comprueba usuario y contraseña; no se reintentará automáticamente.")
        self.connected = True
        self.request("/index.asp")

    def close(self):
        if self.connected:
            try:
                self.request("/logout.cgi")
            except OntError:
                pass
        self.connected = False
        self.jar.clear()

    def read(self) -> Snapshot:
        if not self.connected:
            raise OntError("Primero conecta e inicia sesión.")
        dev = constructor(self.request(DEVICE), "stDeviceInfo", (11,))
        auth = constructor(self.request(AUTH), "stDevInfo", (6,))
        xgs = constructor(self.request(XGS), "stXDevInfo", (4, 5))
        serial = auth[1].upper()
        pw = auth[5].upper()
        if not re.fullmatch(r"[0-9A-F]{16}", serial) or dev[1].upper() != serial:
            raise OntError("Los datos de identidad no coinciden. No se permiten cambios.")
        if pw and not re.fullmatch(r"[0-9A-F]{20}", pw):
            raise OntError("Contraseña GPON actual en formato inesperado. No se permiten cambios.")
        mac = dev[7].upper()
        if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
            raise OntError("No se puede identificar la MAC física de esta ONT.")
        return Snapshot(dev[4], dev[2], dev[3], serial, pw, xgs, mac)

    def plan(self, before: Snapshot, idont: str, serial: str = "") -> Plan:
        if not before.supported:
            raise OntError("Modelo, hardware o firmware no admitidos para escritura. La lectura sí está disponible.")
        return Plan(before, normalize_idont(idont), normalize_serial(serial) if serial.strip() else before.serial)

    def restore_plan(self, before: Snapshot, data: dict) -> Plan:
        if not before.supported or (data["model"], data["hardware"], data["mac"]) != (before.model, before.hardware, before.mac):
            raise OntError("Esta copia no corresponde a la MAC física y hardware de la ONT conectada.")
        if not re.fullmatch(r"(?:[0-9A-F]{20})?", data["idont"]) or not re.fullmatch(r"[0-9A-F]{16}", data["serial"]):
            raise OntError("Identidad de la copia no válida.")
        return Plan(before, data["idont"], data["serial"], restore=True)

    @staticmethod
    def check_result(page: str):
        code = re.search(r"\bErrCode\s*=\s*['\"]?(-?\d+)", page)
        if code and int(code.group(1)) != 0:
            raise OntError("La ONT ha rechazado el cambio. Relee el estado antes de continuar.")

    def apply(self, plan: Plan, backup: Path, confirmed=False) -> str:
        if not confirmed:
            raise OntError("Es necesaria una confirmación explícita antes de escribir.")
        if not plan.before.supported:
            raise OntError("Firmware no admitido para escritura.")
        if plan.restore:
            if not re.fullmatch(r"(?:[0-9A-F]{20})?", plan.idont) or not re.fullmatch(r"[0-9A-F]{16}", plan.serial):
                raise OntError("La copia contiene valores no válidos.")
        elif plan.idont != normalize_idont(plan.idont):
            raise OntError("El plan contiene un IdONT no válido.")
        if not plan.restore and plan.serial != plan.before.serial and plan.serial != normalize_serial(plan.serial):
            raise OntError("El plan contiene un serial no válido.")
        if self.read() != plan.before:
            raise OntError("La configuración ha cambiado desde la lectura. Vuelve a leer y preparar el cambio.")
        if not plan.changed:
            return "Sin cambios: los valores ya coinciden. No se ha escrito ni guardado nada en la ONT."
        save_backup(backup, plan.before)
        # Recheck after local backup creation, immediately before the write.
        if self.read() != plan.before:
            raise OntError("La ONT cambió mientras se preparaba la copia. No se ha escrito nada.")
        auth_page = self.request(AUTH)
        current = constructor(auth_page, "stDevInfo", (6,))
        if current[1].upper() != plan.before.serial or current[5].upper() != plan.before.idont:
            raise OntError("La identidad ha cambiado. No se ha escrito nada.")
        fields = {}
        if plan.idont != plan.before.idont:
            fields["x.X_HW_PonHexPassword"] = plan.idont
        if plan.serial != plan.before.serial:
            fields["x.X_HW_PonSN"] = plan.serial
        fields["x.X_HW_ForceSet"] = "1"
        fields["x.X_HW_Token"] = token(auth_page)  # Keep token last, as required by this CGI.
        attempted = False
        try:
            attempted = True
            self.check_result(self.request(SET_AUTH, fields, AUTH))
            after = self.read()
            expected = Snapshot(plan.before.model, plan.before.hardware, plan.before.firmware, plan.serial, plan.idont, plan.before.xgs, plan.before.mac)
            if after != expected:
                raise OntError("La lectura posterior no coincide con el plan o ha cambiado otro parámetro. No se ha pedido guardar.")
            cfg_page = self.request(CFG)
            self.check_result(self.request(SAVE, {"x.X_HW_Token": token(cfg_page)}, CFG))
            if self.read() != expected:
                raise OntError("No se ha confirmado la lectura después de guardar.")
        except OntError as e:
            if attempted:
                raise OntError(str(e) + " El cambio pudo aplicarse total o parcialmente. No reintentes a ciegas ni reinicies; vuelve a leer. Conserva la copia de identidad.") from None
            raise
        return "Valores leídos correctamente después de aplicar y guardar. No se ha reiniciado. Falta verificar persistencia tras un reinicio e Internet en tu router."


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, decrypt=False) -> bytes:
    if sys.platform != "win32":
        raise OntError("La copia cifrada de esta versión requiere Windows.")
    raw = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OntError("Windows no puede procesar la copia cifrada. Utiliza la misma cuenta que la creó.")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(target.pbData)


MAGIC = b"HNONT-DPAPI-1\n"


def save_backup(path: Path, before: Snapshot):
    payload = json.dumps({"version": 1, "model": before.model, "hardware": before.hardware,
        "firmware": before.firmware, "serial": before.serial, "idont": before.idont, "mac": before.mac}).encode()
    encrypted = MAGIC + _dpapi(payload)
    try:
        with Path(path).open("xb") as f:
            f.write(encrypted)
    except OSError:
        raise OntError("No se puede crear una copia nueva. Elige otro archivo; no se sobrescriben copias existentes.") from None


def load_backup(path: Path) -> dict:
    try:
        path = Path(path)
        if path.stat().st_size > 65536:
            raise ValueError()
        raw = path.read_bytes()
        if len(raw) > 65536 or not raw.startswith(MAGIC):
            raise ValueError()
        data = json.loads(_dpapi(raw[len(MAGIC):], decrypt=True))
        if data.get("version") != 1 or data.get("model") != "HN8010Ts-20":
            raise ValueError()
        if not re.fullmatch(r"[0-9A-F]{16}", data["serial"]) or not re.fullmatch(r"(?:[0-9A-F]{20})?", data["idont"]):
            raise ValueError()
        if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", data["mac"]):
            raise ValueError()
        return data
    except OntError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise OntError("La copia no tiene un formato válido.") from None
