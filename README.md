# Huawei ONT Config

Herramienta abierta para Windows que lee el IdONT y el serial óptico de un Askey WiFi 7 de Movistar y permite configurarlos en una Huawei HN8010Ts-20 a través de su interfaz web interna.

Nació de unas pruebas reales sustituyendo el HGU por una ONT externa en una línea Movistar XGS-PON. Desarrollada con ayuda de Codex. No es una herramienta oficial de Huawei, Askey ni Movistar.

**Versión experimental.** La extracción del Askey se ha probado contra un equipo real. En la Huawei, esta aplicación se ha probado en lectura, copia cifrada y simulación sin cambios. Las escrituras con valores diferentes están cubiertas por pruebas automáticas, pero falta validarlas con esta aplicación en una ONT de pruebas. El funcionamiento de una instalación no garantiza compatibilidad con otras líneas u OLT.

## Descargar y usar

Descarga el ZIP de Windows desde [Releases](https://github.com/javigmsuperka/huawei-ont-config/releases), extráelo y abre `HuaweiONTConfig.exe`. El ejecutable no está firmado digitalmente.

1. En el apartado **Askey**, pulsa **Leer datos del Askey…** e introduce IP, usuario y contraseña. Carga el IdONT y el serial sin modificar el router.
2. Conecta el PC a la **ONT Huawei**. Si hace falta, configura una IP compatible en la tarjeta de red del PC.
3. Introduce el acceso a la Huawei y pulsa **1 Leer ONT**.
4. Pulsa **2 Revisar cambio** y comprueba los datos.
5. **3 Aplicar y guardar** pide confirmación y crea una copia cifrada de la identidad anterior antes de escribir.

Puedes leer el Askey y después conectar la Huawei sin cerrar la aplicación. No hace falta tener los dos conectados a la vez. La herramienta no crea rutas ni cambia la configuración de tu router o del PC.

Consulta [las instrucciones completas](LEEME.md), incluidos los formatos de los identificadores, la restauración y las limitaciones.

## Compatibilidad

| Función | Referencia probada o admitida |
|---|---|
| Extracción Askey real | Pegatina: **RTF8317VW-D1-SX** · Web del equipo: **RTF8317VW-SX** · Firmware: GL_g1.18_R8316_V2.19 |
| Lectura Huawei real | HN8010Ts-20, hardware 2D62.A, firmware V5R022C00S510 |
| Escritura admitida por el programa | HN8010Ts-20 / 2D62.A / V5R022C00S462 o V5R022C00S510 |
| Sistema | Windows con interfaz gráfica; Python 3.12 o posterior para el código fuente |

El equipo usado en las pruebas es el **Askey RTF8317VW-D1-SX**, según su pegatina; su web devuelve **RTF8317VW-SX**. Son las dos denominaciones observadas en la misma unidad. La cadena `R8316` del firmware no se utiliza para deducir el modelo.

| Fabricante | Modelo de la pegatina | Pruebas con esta aplicación |
|---|---|---|
| Askey | RTF8316VW | No probado |
| Askey | RTF8317VW-D1 | No probado |
| Askey | **RTF8317VW-D1-SX** | **Extracción real probada**; su web indica RTF8317VW-SX |
| Askey | RTF8317VW-D2 | No probado |
| Askey | RTF8317VW-D2-SX | No probado |
| MitraStar | GPT-6841JL4L4-v11 | No probado; lector no implementado |

El lector Askey reconoce la estructura de la familia RTF8316/8317, pero eso no significa que todas sus variantes estén probadas o admitidas por el validador. Comprueba XGS-PON y la correspondencia entre los parámetros GPON/XGS; si el formato no coincide, detiene la importación.

## Qué hace

- Askey: inicia sesión, lee datos y cierra la sesión. Una lista cerrada de peticiones bloquea las operaciones de configuración.
- Huawei: permite cambiar `X_HW_PonHexPassword` y, opcionalmente, `X_HW_PonSN`. Relee el estado antes y después de escribir y de solicitar el guardado.
- Conserva los ceros del IdONT y convierte únicamente el prefijo `ASKY` cuando corresponde.
- La copia `.hnont` protege la identidad anterior con Windows DPAPI y depende del usuario de Windows que la crea. No es una copia completa de la ONT ni es portátil entre cuentas.

No carga firmware, no reinicia equipos ni configura PPPoE, VLAN o MAC. La contraseña de administración no se guarda. Con HTTP, las credenciales viajan sin cifrado por la red local: utiliza una conexión de confianza. Un estado O5 no demuestra que haya Internet.

## Ejecutar y probar desde el código

No requiere paquetes externos para funcionar; necesita Tkinter y Windows para las copias DPAPI.

```powershell
python app.py
python -m unittest discover -s tests -v
```

Hay 42 pruebas automáticas con datos sintéticos, comprobadas localmente en Windows.

Para compilar el ejecutable:

```powershell
python -m pip install pyinstaller==6.22.3
python -m PyInstaller --clean --noconfirm --onefile --windowed --name HuaweiONTConfig app.py
```

## Colaborar

Las mejoras y los informes de compatibilidad son bienvenidos. Indica modelo, hardware, firmware, versión de la aplicación y el error. No publiques IdONT, seriales completos, contraseñas, cookies, capturas sin censurar ni copias `.hnont` en incidencias o solicitudes de cambios.

Licencia [MIT](LICENSE).
