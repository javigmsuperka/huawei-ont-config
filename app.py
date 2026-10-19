"""Windows desktop application. Credentials are not persisted."""
import argparse
import getpass
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from ont_config import Client, OntError, VERSION, load_backup
from askey import AskeyClient


class AskeyLoginDialog(simpledialog.Dialog):
    def body(self, master):
        self.ip = tk.StringVar(value="192.168.1.1")
        self.username = tk.StringVar(value="1234")
        self.password = tk.StringVar()
        for i, (label, variable) in enumerate((("IP del Askey", self.ip), ("Usuario", self.username), ("Contraseña del Askey", self.password))):
            ttk.Label(master, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=6)
            e = ttk.Entry(master, textvariable=variable, show="•" if i == 2 else "", width=35)
            e.grid(row=i, column=1, padx=8, pady=6)
            if i == 0:
                first = e
        ttk.Label(master, text="Solo lectura. No cambia modos, WiFi, IdONT ni serial del Askey.").grid(row=3, column=0, columnspan=2, padx=8, pady=8)
        return first

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="Leer datos", command=self.ok).pack(side="left", padx=8, pady=8)
        ttk.Button(box, text="Cancelar", command=self.cancel).pack(side="left", padx=8, pady=8)
        box.pack()
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def validate(self):
        from ont_config import local_url
        try:
            local_url(self.ip.get())
            if not self.username.get() or not self.password.get():
                raise OntError("Introduce usuario y contraseña del Askey.")
            return True
        except OntError as e:
            messagebox.showerror("Revisa el acceso", str(e), parent=self)
            return False

    def apply(self):
        self.result = (self.ip.get(), self.username.get(), self.password.get())
        self.password.set("")


class App:
    def __init__(self, window):
        self.window = window
        window.title("Huawei ONT Config " + VERSION)
        window.geometry("880x" + str(min(760, max(590, window.winfo_screenheight() - 90))))
        window.minsize(780, 580)
        self.client = None
        self.snapshot = None
        self.prepared = None
        self.busy = False
        self.messages = queue.Queue()
        self.status = tk.StringVar(value="Conecta el PC a la Huawei. Ningún botón reinicia ni flashea la ONT.")
        self.address = tk.StringVar(value="192.168.100.1")
        self.username = tk.StringVar(value="telecomadmin")
        self.password = tk.StringVar()
        self.idont = tk.StringVar()
        self.serial = tk.StringVar()
        root = ttk.Frame(window, padding=20)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        ttk.Label(root, text="Askey Movistar", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        source_actions = ttk.Frame(root)
        source_actions.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 10))
        self.askey_button = ttk.Button(source_actions, text="Leer datos del Askey…", command=self.import_askey)
        self.askey_button.pack(side="left")
        ttk.Label(source_actions, text="Extrae el IdONT y el serial óptico.").pack(side="left", padx=12)
        self.entries = []
        for row, label, variable, hidden in [(9, "IP de la ONT", self.address, False),
                 (10, "Usuario de la ONT", self.username, False),
                 (11, "Contraseña de la ONT", self.password, True)]:
            ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            e = ttk.Entry(root, textvariable=variable, show="•" if hidden else "")
            e.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
            self.entries.append(e)
        actions = ttk.Frame(root)
        actions.grid(row=12, column=0, columnspan=3, sticky="w", pady=(8, 4))
        self.read_button = ttk.Button(actions, text="1  Leer ONT", command=self.read)
        self.read_button.pack(side="left")
        self.disconnect_button = ttk.Button(actions, text="Desconectar", command=self.disconnect)
        self.disconnect_button.pack(side="left", padx=8)
        ttk.Separator(root).grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(root, text="ONT Huawei HN8010Ts-20", font=("Segoe UI", 18, "bold")).grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 8))
        ttk.Label(root, text="IdONT de Movistar").grid(row=2, column=0, sticky="w")
        self.idont_entry = ttk.Entry(root, textvariable=self.idont, show="•")
        self.idont_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(root, text="14 o 20 caracteres hexadecimales. Se conserva cualquier cero inicial.").grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Label(root, text="Serial óptico del Askey").grid(row=4, column=0, sticky="w", pady=5)
        self.serial_entry = ttk.Entry(root, textvariable=self.serial)
        self.serial_entry.grid(row=4, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(root, text="ASKY + 8 caracteres, o 16 hexadecimales. Vacío = conservar el serial actual.").grid(row=5, column=1, columnspan=2, sticky="w")
        self.visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(root, text="Mostrar IdONT introducido", variable=self.visible,
                        command=lambda: self.idont_entry.configure(show="" if self.visible.get() else "•")).grid(row=6, column=1, sticky="w", pady=5)
        buttons = ttk.Frame(root)
        buttons.grid(row=13, column=0, columnspan=3, sticky="w", pady=(10, 12))
        self.preview_button = ttk.Button(buttons, text="2  Revisar cambio", command=self.preview)
        self.preview_button.pack(side="left")
        self.apply_button = ttk.Button(buttons, text="3  Aplicar y guardar", command=self.apply, state="disabled")
        self.apply_button.pack(side="left", padx=8)
        self.restore_button = ttk.Button(buttons, text="Restaurar copia…", command=self.restore)
        self.restore_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Ayuda", command=self.help).pack(side="left")
        ttk.Label(root, textvariable=self.status, wraplength=800).grid(row=14, column=0, columnspan=3, sticky="w", pady=(3, 10))
        self.output = tk.Text(root, wrap="word", height=7, state="disabled", font=("Consolas", 10))
        self.output.grid(row=15, column=0, columnspan=3, sticky="nsew")
        root.rowconfigure(15, weight=1)
        self.idont.trace_add("write", self.invalidate)
        self.serial.trace_add("write", self.invalidate)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(100, self.poll)

    def invalidate(self, *_):
        self.prepared = None
        self.apply_button.configure(state="disabled")

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def work(self, fn, done):
        if self.busy:
            return
        self.busy = True
        self.status.set("Operación en curso…")
        self.read_button.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.disconnect_button.configure(state="disabled")
        self.restore_button.configure(state="disabled")
        self.askey_button.configure(state="disabled")
        self.idont_entry.configure(state="disabled")
        self.serial_entry.configure(state="disabled")
        for e in self.entries:
            e.configure(state="disabled")
        def worker():
            try:
                self.messages.put((done, fn(), None))
            except OntError as e:
                self.messages.put((done, None, str(e)))
            except Exception:
                self.messages.put((done, None, "Error interno. No se muestran datos de sesión. Vuelve a leer la ONT antes de continuar."))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            done, value, error = self.messages.get_nowait()
        except queue.Empty:
            self.window.after(100, self.poll)
            return
        self.busy = False
        self.read_button.configure(state="normal")
        self.preview_button.configure(state="normal")
        self.disconnect_button.configure(state="normal")
        self.restore_button.configure(state="normal")
        self.askey_button.configure(state="normal")
        self.idont_entry.configure(state="normal")
        self.serial_entry.configure(state="normal")
        for e in self.entries:
            e.configure(state="disabled" if self.client else "normal")
        if error:
            self.snapshot = None
            self.prepared = None
            self.status.set("Operación detenida. Lee el estado de nuevo antes de aplicar.")
            self.log(error)
            messagebox.showerror("Operación detenida", error)
        else:
            done(value)
        self.window.after(100, self.poll)

    def read(self):
        self.invalidate()
        address, username, password = self.address.get(), self.username.get(), self.password.get()
        client = self.client
        def operation():
            c = client or Client(address)
            try:
                if not c.connected:
                    c.login(username, password)
                return c, c.read()
            except Exception:
                if client is None:
                    c.close()
                raise
        def done(value):
            self.client, self.snapshot = value
            self.password.set("")
            for e in self.entries:
                e.configure(state="disabled")
            self.log(json.dumps(self.snapshot.masked(), ensure_ascii=False, indent=2))
            self.status.set("Lectura terminada. Todavía no se ha escrito nada.")
        self.work(operation, done)

    def import_askey(self):
        if self.busy:
            return
        dialog = AskeyLoginDialog(self.window, "Leer IdONT y serial del Askey")
        if not dialog.result:
            return
        address, username, password = dialog.result
        dialog.result = None
        def operation():
            c = AskeyClient(address)
            try:
                c.login(username, password)
                return c.read()
            finally:
                c.close()
        def done(data):
            self.idont.set(data.idont)
            self.serial.set(data.serial)
            self.log("DATOS EXTRAÍDOS\n" + json.dumps(data.masked(), ensure_ascii=False, indent=2))
            self.status.set("Datos del Askey cargados en memoria. Conecta y lee la Huawei; después pulsa Revisar cambio. No se ha escrito en ningún equipo.")
        self.work(operation, done)

    def preview(self):
        if self.busy:
            return
        if not self.client or self.snapshot is None:
            messagebox.showinfo("Primero lee la ONT", "Pulsa 1 Leer ONT antes de preparar un cambio.")
            return
        try:
            self.prepared = self.client.plan(self.snapshot, self.idont.get(), self.serial.get())
        except OntError as e:
            messagebox.showerror("Revisa los datos", str(e))
            return
        p = self.prepared
        self.log("REVISIÓN\n" + json.dumps(p.masked(), ensure_ascii=False, indent=2))
        if p.changed:
            self.apply_button.configure(state="normal")
            self.status.set("Cambio preparado. No se aplicará hasta que confirmes el paso 3.")
        else:
            self.status.set("Los valores ya coinciden. No es necesario escribir ni guardar.")

    def apply(self):
        if self.busy or self.prepared is None:
            return
        plan = self.prepared
        if not messagebox.askyesno("Confirmar cambio en la ONT", "Se modificarán únicamente los valores marcados en la revisión.\n\nEl cambio de identidad puede interrumpir Movistar hasta que el equipo registre de nuevo. No se reiniciará ni flasheará la ONT.\n\n¿Aplicar y guardar estos cambios?"):
            return
        name = filedialog.asksaveasfilename(title="Guardar copia cifrada de la identidad anterior", defaultextension=".hnont", filetypes=[("Copia de identidad cifrada", "*.hnont")])
        if not name:
            return
        self.prepared = None
        def done(value):
            self.snapshot = None
            self.status.set("Operación terminada. Lee otra vez la ONT para preparar otro cambio.")
            self.log(value)
            messagebox.showinfo("Resultado", value)
        self.work(lambda: self.client.apply(plan, Path(name), confirmed=True), done)

    def restore(self):
        if self.busy:
            return
        if not self.client or self.snapshot is None:
            messagebox.showinfo("Primero lee la ONT", "Lee la ONT antes de cargar una copia.")
            return
        name = filedialog.askopenfilename(title="Copia cifrada creada con esta cuenta de Windows", filetypes=[("Copia de identidad cifrada", "*.hnont")])
        if not name:
            return
        try:
            self.prepared = self.client.restore_plan(self.snapshot, load_backup(Path(name)))
        except OntError as e:
            self.invalidate()
            messagebox.showerror("No se puede restaurar", str(e))
            return
        self.log("REVISIÓN DE RESTAURACIÓN\n" + json.dumps(self.prepared.masked(), ensure_ascii=False, indent=2))
        self.apply_button.configure(state="normal" if self.prepared.changed else "disabled")
        self.status.set("Copia cargada. Revisa los cambios y pulsa Aplicar y guardar para confirmar la restauración.")

    def disconnect(self):
        if self.busy:
            return
        c = self.client
        def done(_):
            self.client = self.snapshot = self.prepared = None
            for e in self.entries:
                e.configure(state="normal")
            self.password.set("")
            self.status.set("Sesión cerrada.")
        if c:
            self.work(c.close, done)
        else:
            done(None)

    def help(self):
        messagebox.showinfo("Cómo usarlo", "1. Conecta el PC a la Huawei y pulsa Leer ONT.\n2. Introduce el IdONT y, si quieres cambiarlo, el serial óptico del Askey.\n3. Revisa el cambio y confirma Aplicar y guardar.\n\nEl IdONT va a X_HW_PonHexPassword, no al campo XGS Registration ID. El serial puede requerir un cambio de registro en la OLT.\n\nSolo se admite escritura para HN8010Ts-20, hardware 2D62.A y firmware S462/S510. La aplicación no garantiza compatibilidad con tu línea.\n\nLa copia .hnont contiene solo los dos identificadores anteriores, cifrados para tu cuenta de Windows; no es una copia completa del router. No contiene la contraseña de administración. Consulta LEEME para restaurarla.")

    def close(self):
        if self.busy:
            messagebox.showinfo("Operación en curso", "Espera a que termine antes de cerrar.")
            return
        if self.client:
            self.client.close()
        self.window.destroy()


def cli(args):
    c = Client(args.address or "192.168.100.1")
    try:
        c.login(args.username or "telecomadmin", getpass.getpass("Contraseña Huawei: "))
        snap = c.read()
        print(json.dumps(snap.masked(), ensure_ascii=False, indent=2))
        if args.check:
            identifier = getpass.getpass("IdONT (no se guarda): ")
            serial = input("Serial Askey (vacío = conservar): ")
            print(json.dumps(c.plan(snap, identifier, serial).masked(), ensure_ascii=False, indent=2))
            print("Solo simulación. No se han enviado cambios ni una petición de guardado.")
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser(description="Huawei HN8010Ts-20 web configurator")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--read", action="store_true", help="Lectura por consola, sin escritura")
    parser.add_argument("--check", action="store_true", help="Simular un cambio por consola")
    parser.add_argument("--read-askey", action="store_true", help="Leer los datos del Askey por consola sin escribir")
    parser.add_argument("--address", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--gui-smoke", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.read_askey:
        c = AskeyClient(args.address or "192.168.1.1")
        try:
            c.login(args.username or "1234", getpass.getpass("Contraseña Askey: "))
            print(json.dumps(c.read().masked(), ensure_ascii=False, indent=2))
        except OntError as e:
            parser.exit(1, str(e) + "\n")
        finally:
            c.close()
    elif args.read or args.check:
        try:
            cli(args)
        except OntError as e:
            parser.exit(1, str(e) + "\n")
    else:
        window = tk.Tk()
        App(window)
        if args.gui_smoke:
            window.after(800, window.destroy)
        window.mainloop()


if __name__ == "__main__":
    main()
