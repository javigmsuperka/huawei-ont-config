# Huawei ONT Config

Aplicación para Windows que configura el IdONT GPON y, opcionalmente, el serial óptico de una Huawei HN8010Ts-20. Utiliza su interfaz web interna. No necesita SSH y no carga firmware.

## Uso rápido

1. Conecta el PC a la Huawei. La IP habitual de esta unidad es `192.168.100.1`; usa la indicada en tu etiqueta. Si hace falta, asigna al PC `192.168.100.10` con máscara `255.255.255.0` en esa conexión.
2. Abre `HuaweiONTConfig.exe` e introduce la IP, el usuario y la contraseña de administración de la Huawei. Con el firmware probado se utilizó `telecomadmin` y `admin@` seguido de la contraseña de su etiqueta. La herramienta no incluye ninguna contraseña de fábrica ni una contraseña particular.
3. Pulsa **1 Leer ONT**. Todavía no cambia nada.
4. Introduce el IdONT de tu línea. Admite 14 o 20 caracteres hexadecimales. Con 14 añade seis ceros a la derecha; con 20 los conserva. No elimina ceros iniciales. No acepta `0x` ni espacios internos.
5. Para cambiar también el serial, introduce el serial óptico del Askey: `ASKY` seguido de ocho caracteres hexadecimales, o la cadena equivalente de 16 hexadecimales. Si dejas este cuadro vacío, se conserva el serial actual.
6. Pulsa **2 Revisar cambio**. La herramienta indica qué cambiará, con identificadores parcialmente ocultos. Puedes mostrar el IdONT que has introducido mediante la casilla correspondiente.
7. Pulsa **3 Aplicar y guardar**, confirma la operación y elige dónde guardar una copia cifrada de la identidad anterior. No se sobrescriben copias existentes.
8. La herramienta aplica únicamente los campos que cambian, comprueba la lectura, solicita guardar y vuelve a leer. No reinicia. Comprueba por separado el registro de la ONT y PPPoE/Internet en tu router. Una lectura posterior al guardado no demuestra por sí sola persistencia después de apagar y encender.

Si los valores ya coinciden, no se escribe ni se solicita guardar.

## Los datos se obtienen del Askey

- IdONT: `http://192.168.1.1/instalacion`, campo **Identificador de la ONT configurado**.
- Serial óptico: **MENÚ → Configuración avanzada → Aceptar → Information**, campo **GPON Serial Number**. No es la MAC ni el número de serie comercial de la etiqueta.
- El prefijo `ASKY` se convierte a `41534B59`; los ocho caracteres hexadecimales finales se conservan, sin volver a convertirlos.

También puedes pulsar **Leer datos del Askey…** en la aplicación, introducir su IP, usuario (habitualmente `1234`) y contraseña de administración. Lee el IdONT GPON completo y el serial óptico, verifica que GPON y XGS coinciden con el formato probado, los carga en los cuadros y cierra la sesión del Askey. No guarda la contraseña y no escribe ajustes en ese router.

No recorta el IdONT a los 14 caracteres que muestra la pantalla: conserva los 20 del parámetro original, incluidos posibles caracteres finales distintos de cero.

Puedes hacerlo por etapas: primero conecta el PC al Askey y extrae; después, sin cerrar la aplicación, conecta el PC a la Huawei y ajusta la IP de esa conexión si hace falta. Los datos extraídos permanecen en memoria. Pulsa Leer ONT y Revisar cambio antes de Aplicar. No necesitas tener ambos equipos conectados a la vez.

La extracción se ha probado en un Askey `RTF8317VW-SX` con firmware `GL_g1.18_R8316_V2.19`. Solo se admite la estructura web de esta familia; si el modelo, formato o valores GPON/XGS no encajan, se detiene en vez de adivinar. Un Askey en modo GPON no se importa automáticamente en esta configuración de referencia XGS-PON. No se cambia su tecnología de fibra.

El cliente Askey tiene una lista cerrada de peticiones permitidas. No permite `cbSet*`, guardar configuración, cambiar modos, reiniciar ni cargar firmware.

## Qué modifica

| Campo | Uso |
|---|---|
| `X_HW_PonHexPassword` | IdONT de Movistar en hexadecimal |
| `X_HW_PonSN` | Serial óptico, solo si solicitas cambiarlo |

No modifica `XGS Registration ID`, LOID, autenticación mutua, MAC, VLAN, PPPoE, firmware ni ajustes del router. La existencia de O5 no demuestra que el servicio de Internet esté aprovisionado.

La escritura está limitada a **HN8010Ts-20, hardware 2D62.A, firmware V5R022C00S462 o V5R022C00S510**. Otros modelos o versiones no están admitidos para escritura. La lectura depende de que expongan la misma estructura web.

Los cambios de identidad pueden interrumpir el registro y dejar Movistar sin servicio hasta configurar valores aceptados. La herramienta comprueba formato y lectura, pero no puede garantizar que la OLT de tu línea acepte una ONT externa.

## Copias y restauración

La copia `.hnont` contiene los identificadores anteriores, el modelo, hardware, firmware y MAC física para identificar el equipo. **Es una copia de identidad, no una copia completa de la configuración de la ONT.** No contiene la contraseña de administración.

Se cifra con Windows DPAPI para la cuenta de Windows que la crea. Consérvala en esa cuenta; no es una copia portátil para otro PC o usuario. No restaures Windows ni borres ese perfil suponiendo que podrás descifrarla después.

Para restaurar:

1. Lee la ONT con **1 Leer ONT**.
2. Pulsa **Restaurar copia…** y elige el archivo creado con la misma cuenta de Windows.
3. La aplicación verifica el modelo, hardware y MAC física de destino y prepara una revisión, sin escribir todavía.
4. Confirma **Aplicar y guardar**. Antes se crea otra copia nueva del estado actual.

La restauración admite recuperar el serial de fábrica y una contraseña GPON inicialmente vacía. Tampoco reinicia automáticamente.

Si el equipo deja de responder tras una escritura, la aplicación no reintenta ni asegura éxito: indica que el cambio pudo aplicarse y pide releer antes de continuar. No hay reversión automática, porque un segundo cambio a ciegas también podría dejar el equipo inaccesible.

## Privacidad

- No guarda las credenciales de administración ni los formularios web en archivos o registros.
- La contraseña se borra del cuadro de entrada al conectar; las credenciales y cookies necesarias durante la sesión permanecen en memoria. No se promete un borrado seguro de la memoria de Python.
- El informe de lectura oculta los identificadores completos. Las copias cifradas sí contienen esos identificadores para poder recuperarlos.
- Solo admite IP privadas IPv4 o un túnel en `127.0.0.1`; no usa proxies configurados en el sistema. Bloquea redirecciones hacia otro origen.
- HTTP no cifra el enlace. Utilízalo mediante una conexión local de confianza o un túnel. Si la ONT dispone de HTTPS con un certificado válido puedes introducir su URL; no se desactiva la comprobación de certificados.

## Validación de esta versión

- 42 pruebas automáticas con datos inventados: conversión, cookies, lectura, validación de destino, confirmación, cambios concurrentes, fallo de copia, rechazo de escritura, conservación de XGS, guardado después de lectura, restauración y confirmación en la interfaz.
- Prueba real de extracción contra un Askey RTF8317VW-SX conectado a un laboratorio aislado en PVE1: inicio de sesión, IdONT, serial, coincidencia con la extracción original y cierre de sesión. Cero peticiones de configuración.
- Prueba real contra una HN8010Ts-20 2D62.A con S510: autenticación, lectura de los parámetros, coincidencia con los datos del Askey, copia DPAPI y simulación sin cambios. No se enviaron escrituras ni guardados en esa prueba real.
- La secuencia de escritura se basa en las peticiones usadas durante la configuración original de esa instalación. El ejecutable nuevo no ha sido validado aplicando valores distintos contra una ONT de pruebas desconectada de producción. Antes de publicarlo como solución general, falta esa validación y comparar con otras líneas/OLT.

El `.exe` no está firmado digitalmente. Se incluye el código fuente para revisarlo y ejecutarlo sin depender del binario.

## Ejecutar el código fuente

Python 3.12 o posterior en Windows con Tkinter. El programa no necesita paquetes externos para funcionar:

```powershell
python app.py
```

Lectura o simulación por consola, sin aplicar cambios:

```powershell
python app.py --read --address 192.168.100.1
python app.py --check --address 192.168.100.1
python app.py --read-askey --address 192.168.1.1 --username 1234
```

La contraseña se solicita oculta, no como argumento de la línea de comandos. La escritura solo se ofrece desde la interfaz gráfica con revisión y confirmación.

Pruebas y compilación:

```powershell
python -m unittest discover -s tests -v
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm --onefile --windowed --name HuaweiONTConfig app.py
```

No distribuyas tus copias `.hnont`, identificadores reales ni credenciales junto con el programa.
