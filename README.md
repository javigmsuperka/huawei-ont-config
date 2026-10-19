# Huawei ONT Config

Programa para Windows que extrae el **IdONT y el serial óptico de tu Askey WiFi 7 de Movistar** y permite introducirlos en una **Huawei HN8010Ts-20**. Sirve para preparar la ONT Huawei para sustituir el HGU en una conexión Movistar XGS-PON.

## Descargar

[**Descargar el programa para Windows**](https://github.com/javigmsuperka/huawei-ont-config/releases/tag/v0.2.1)

Descarga `HuaweiONTConfig-0.2.1-Windows.zip`, descomprímelo y abre `HuaweiONTConfig.exe`. No necesitas instalar Python. El ejecutable no está firmado digitalmente.

### Si Windows 11 bloquea el programa

El **Control inteligente de aplicaciones** puede impedir que se ejecute esta aplicación porque el ejecutable no está firmado. Si te aparece ese bloqueo, para utilizar este ejecutable tendrás que desactivar esa función:

1. Abre **Inicio → Seguridad de Windows**.
2. Entra en **Control de aplicaciones y navegador**.
3. Abre **Configuración de Control inteligente de aplicaciones**.
4. Selecciona **Desactivado** y confirma.

**No es necesario hacerlo si el programa ya abre.** Desactivar esta función reduce la protección para todo el equipo, no solo para esta aplicación. En versiones antiguas de Windows, volver a activarla puede requerir restablecer o reinstalar Windows; las actualizaciones recientes permiten reactivarla sin una instalación limpia. Consulta la [información de Microsoft](https://support.microsoft.com/es-es/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions) antes de cambiarla.

## Equipos utilizados

- **Askey:** en la pegatina pone **RTF8317VW-D1-SX**; en su web aparece **RTF8317VW-SX**. Es la misma unidad.
- **ONT:** Huawei **HN8010Ts-20**, hardware **2D62.A**. El programa admite escritura con firmware **V5R022C00S462** o **V5R022C00S510**.

Otros modelos no se han probado. El lector para MitraStar no está implementado.

## Tutorial rápido

### 1. Sacar los datos del Askey

1. Conecta el PC por Ethernet al Askey y abre el programa.
2. En el apartado **Askey**, pulsa **Leer datos del Askey…**.
3. Introduce la IP del router —normalmente `192.168.1.1`—, su usuario y su contraseña de administración.
4. Al terminar, aparecerán el IdONT y el serial óptico en los cuadros del programa. **Deja la aplicación abierta** para conservarlos mientras cambias de equipo.

La extracción no modifica la configuración del Askey.

### 2. Configurar la Huawei

**Dónde va el IdONT:** en la configuración probada, el IdONT de Movistar se guarda en el parámetro interno **`X_HW_PonHexPassword`** de la Huawei. El programa lo escribe ahí aunque el panel web no muestre ese parámetro como un campo editable.

- **No va en `XGS Registration ID`**: es otro parámetro de autenticación; el programa no lo modifica.
- **No es el `ONT ID` de la pantalla de estado**: ese número lo asigna la OLT durante el registro. No es el IdONT de tu línea ni un campo donde debas pegarlo.
- El **serial óptico PON** es un dato distinto y se configura en `X_HW_PonSN`.

1. Conecta el PC por Ethernet a la Huawei. No hace falta mantener el Askey conectado.
2. Si la Huawei usa `192.168.100.1`, configura en esa tarjeta del PC la IP `192.168.100.10`, máscara `255.255.255.0` y deja puerta de enlace y DNS vacíos. Usa otra dirección si lo indica la etiqueta de tu ONT.
3. En el apartado **ONT**, introduce su IP, usuario y contraseña de administración. Pulsa **1 Leer ONT**.
4. Comprueba los datos extraídos del Askey y pulsa **2 Revisar cambio**.
5. Pulsa **3 Aplicar y guardar**, confirma y elige dónde guardar la copia cifrada de los identificadores anteriores.
6. Espera al resultado de la comprobación. Conserva la copia `.hnont` en la misma cuenta de Windows que la creó para poder restaurarla.

Al terminar, devuelve la tarjeta del PC a su configuración de red anterior. El programa no cambia automáticamente la red del PC.

### 3. Comprobar Internet

Conecta la fibra Movistar a la Huawei y su Ethernet al puerto WAN de tu router. Configura en el router el PPPoE y la VLAN 6 correspondientes a Movistar. Estos ajustes se hacen fuera del programa.

Comprueba que el router obtiene conexión y puedes navegar. Que la ONT marque O5, por sí solo, no demuestra que haya Internet.

## Estado del proyecto

**Experimental:** extracción comprobada con el Askey real. En la Huawei, la aplicación se ha probado en lectura, copia y simulación sin cambios; falta validar una escritura con valores diferentes en una ONT de pruebas. No se garantiza compatibilidad con todas las líneas.

La herramienta no flashea ni reinicia equipos. Los cambios de identidad pueden dejar la ONT sin servicio. Consulta la [guía completa](LEEME.md) para formatos, credenciales de administración, restauración y detalles técnicos.

Código abierto con licencia [MIT](LICENSE). Desarrollado con ayuda de Codex. No es un programa oficial de Movistar, Askey ni Huawei.
