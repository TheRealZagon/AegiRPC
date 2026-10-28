import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from associations import associations_installed, install_associations, remove_associations
from common import (
    DEFAULTS,
    SUPPORTED_EXTENSIONS,
    VERSION,
    find_aegisub,
    install_path,
    read_config,
    save_config_file,
    validate_config,
)

WINDOW_WIDTH = 550
MAX_WINDOW_HEIGHT = 760
PROGRAM_FILES = ("aegi_rpc.py", "gui.py", "common.py", "associations.py")


def installed_program():
    """Path the program has (or would have) in the install folder."""
    name = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "aegi_rpc.py"
    return os.path.join(install_path(), name)


def is_installed():
    return os.path.isfile(installed_program())


def install_files():
    """Copies the program into the install folder and returns the path to launch."""
    dest = install_path()
    os.makedirs(dest, exist_ok=True)

    if getattr(sys, "frozen", False):
        src, dst = sys.executable, installed_program()
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
            if sys.platform != "win32":
                os.chmod(dst, 0o755)
    else:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        for name in PROGRAM_FILES:
            src = os.path.join(script_dir, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(dest, name))

    return installed_program()


class AegiRPCGUI:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = {}
        self.aegisub_path = None
        self.result = None
        self.files = []

        self.root = tk.Tk()
        self.root.title(f"AegiRPC {VERSION}")
        self.root.resizable(False, False)

        self.load_config()
        self.detect_aegisub()
        self.build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.cancel)

    def center_window(self):
        """Sizes the window to its content, as far as the screen allows (the content scrolls)."""
        self.root.update_idletasks()
        wanted = self.scroll_frame.winfo_reqheight() + self.button_bar.winfo_reqheight() + 4
        height = min(wanted, MAX_WINDOW_HEIGHT, self.root.winfo_screenheight() - 80)
        x = (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{WINDOW_WIDTH}x{height}+{x}+{y}")

    def load_config(self):
        try:
            self.config = read_config(self.config_path)
        except Exception:
            self.config = DEFAULTS.copy()

        self.aegisub_path = self.config["aegisub_path"] or None

    def save_config(self):
        self.config["aegisub_path"] = self.aegisub_path or ""
        saved = save_config_file(self.config_path, self.config)
        if saved != self.config_path:
            messagebox.showinfo(
                "Settings saved elsewhere",
                f"{self.config_path}\nis read-only, so your settings were saved to:\n{saved}",
            )
            self.config_path = saved

    def detect_aegisub(self):
        if not (self.aegisub_path and os.path.isfile(self.aegisub_path)):
            self.aegisub_path = find_aegisub()

    def build_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        # Outside the scrolling area so the buttons stay visible
        self.button_bar = ttk.Frame(self.root, padding=(20, 10))
        self.button_bar.pack(side=tk.BOTTOM, fill=tk.X)

        canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        window_id = canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        main_frame = ttk.Frame(self.scroll_frame, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        if self.aegisub_path:
            self.build_settings_ui(main_frame)
        else:
            self.build_install_ui(main_frame)

        self.center_window()

    def build_install_ui(self, parent):
        ttk.Label(parent, text="AegiRPC Setup", font=("", 16, "bold")).pack(pady=(0, 10))
        ttk.Label(
            parent,
            text="Aegisub was not found in the expected locations.\nPlease locate the Aegisub executable:",
            justify=tk.CENTER
        ).pack(pady=(0, 15))

        path_frame = ttk.LabelFrame(parent, text="Aegisub Location", padding="10")
        path_frame.pack(fill=tk.X, pady=(0, 15))

        self.path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.path_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(path_frame, text="Browse", command=self.browse_aegisub).pack(side=tk.RIGHT)

        assoc_frame = ttk.LabelFrame(parent, text="File Associations", padding="10")
        assoc_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(assoc_frame, text="Set AegiRPC as the default editor for subtitle files.\nThis allows double-clicking .ass/.srt files to open them\nthrough AegiRPC with Discord Rich Presence.\n\nFiles will be installed to a permanent location so\nfile associations survive if you delete this folder.").pack(pady=(0, 10))
        ttk.Button(assoc_frame, text="Install & Set as Default Editor (.ass/.srt)", command=self.set_file_associations).pack()

        ttk.Button(self.button_bar, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        ttk.Button(self.button_bar, text="Save & Continue", command=self.save_install).pack(side=tk.RIGHT, padx=(0, 10))

    def build_settings_ui(self, parent):
        ttk.Label(parent, text="AegiRPC Settings", font=("", 16, "bold")).pack(pady=(0, 15))

        aegi_frame = ttk.LabelFrame(parent, text="Aegisub", padding="10")
        aegi_frame.pack(fill=tk.X, pady=(0, 10))

        aegi_path_frame = ttk.Frame(aegi_frame)
        aegi_path_frame.pack(fill=tk.X)

        self.aegi_path_var = tk.StringVar(value=self.aegisub_path)
        ttk.Label(aegi_path_frame, textvariable=self.aegi_path_var, wraplength=400).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(aegi_path_frame, text="Change", command=self.browse_aegisub).pack(side=tk.RIGHT)

        discord_frame = ttk.LabelFrame(parent, text="Discord", padding="10")
        discord_frame.pack(fill=tk.X, pady=(0, 10))

        self.edit_client_id_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(discord_frame, text="Edit Client ID (advanced - may break RPC if changed incorrectly)",
                         variable=self.edit_client_id_var, command=self.toggle_client_id).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

        ttk.Label(discord_frame, text="Client ID:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.client_id_var = tk.StringVar(value=self.config["client_id"])
        self.client_id_entry = ttk.Entry(discord_frame, textvariable=self.client_id_var, width=40, state="disabled")
        self.client_id_entry.grid(row=1, column=1, sticky=tk.EW, pady=2)

        self.button_enabled_var = tk.BooleanVar(value=self.config["button_enabled"])
        self.button_enabled_check = ttk.Checkbutton(discord_frame, text="Show Website Button", variable=self.button_enabled_var, command=self.toggle_button_fields)
        self.button_enabled_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)

        ttk.Label(discord_frame, text="Button Label:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.button_label_var = tk.StringVar(value=self.config["button_label"])
        self.button_label_entry = ttk.Entry(discord_frame, textvariable=self.button_label_var, width=40)
        self.button_label_entry.grid(row=3, column=1, sticky=tk.EW, pady=2)

        ttk.Label(discord_frame, text="Button URL:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.button_url_var = tk.StringVar(value=self.config["button_url"])
        self.button_url_entry = ttk.Entry(discord_frame, textvariable=self.button_url_var, width=40)
        self.button_url_entry.grid(row=4, column=1, sticky=tk.EW, pady=2)

        discord_frame.columnconfigure(1, weight=1)

        display_frame = ttk.LabelFrame(parent, text="Display", padding="10")
        display_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(display_frame, text="Project Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.project_name_var = tk.StringVar(value=self.config["project_name_source"])
        ttk.Combobox(display_frame, textvariable=self.project_name_var, values=["ass_filename", "ass_title"], state="readonly", width=37).grid(row=0, column=1, sticky=tk.EW, pady=2)

        self.hide_file_names_var = tk.BooleanVar(value=self.config["hide_file_names"])
        ttk.Checkbutton(display_frame, text="Hide file names (show only the default text)", variable=self.hide_file_names_var, command=self.update_preview).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)

        self.tooltip_var = tk.BooleanVar(value=self.config["tooltip_enabled"])
        ttk.Checkbutton(display_frame, text="Show Tooltip", variable=self.tooltip_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)

        self.hide_console_var = tk.BooleanVar(value=self.config["hide_console"])
        ttk.Checkbutton(display_frame, text="Hide Console (Windows)", variable=self.hide_console_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)

        display_frame.columnconfigure(1, weight=1)

        preview_frame = ttk.LabelFrame(parent, text="Discord Preview", padding="10")
        preview_frame.pack(fill=tk.X, pady=(0, 10))

        self.preview_canvas = tk.Canvas(preview_frame, width=320, height=180, bg="#2b2d31", highlightthickness=1, highlightbackground="#1e1f22")
        self.preview_canvas.pack(pady=5)

        self.button_label_var.trace_add("write", lambda *a: self.update_preview())
        self.button_url_var.trace_add("write", lambda *a: self.update_preview())
        self.update_preview()
        self.toggle_button_fields()

        assoc_frame = ttk.LabelFrame(parent, text="File Associations", padding="10")
        assoc_frame.pack(fill=tk.X, pady=(0, 10))

        if is_installed():
            ttk.Label(assoc_frame, text=f"AegiRPC is installed at:\n{install_path()}\n\nFile associations point to the installed copy.").pack(pady=(0, 10))
        else:
            ttk.Label(assoc_frame, text="Set AegiRPC as the default editor for subtitle files.\nFiles will be installed to a permanent location so\nfile associations survive if you delete this folder.").pack(pady=(0, 10))
        ttk.Button(assoc_frame, text="Install & Set as Default Editor (.ass/.srt)", command=self.set_file_associations).pack()
        self.remove_assoc_button = ttk.Button(assoc_frame, text="Remove & Restore Previous Defaults", command=self.remove_file_associations)
        self.remove_assoc_button.pack(pady=(5, 0))
        self.update_remove_button()

        launch_frame = ttk.LabelFrame(parent, text="Launch", padding="10")
        launch_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(launch_frame, text="Subtitle files to open with Aegisub (each opens in its own window):").pack(anchor=tk.W, pady=(0, 5))

        file_frame = ttk.Frame(launch_frame)
        file_frame.pack(fill=tk.X)

        self.file_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=50)
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        file_entry.bind("<Return>", lambda e: self.add_typed_file())
        ttk.Button(file_frame, text="Browse", command=self.browse_subtitle).pack(side=tk.RIGHT)
        ttk.Button(file_frame, text="Add", command=self.add_typed_file).pack(side=tk.RIGHT, padx=(0, 5))

        self.file_list = tk.Listbox(launch_frame, height=4, selectmode=tk.EXTENDED)
        self.file_list.pack(fill=tk.X, pady=(8, 4))
        for path in self.files:
            self.file_list.insert(tk.END, path)
        ttk.Button(launch_frame, text="Remove Selected", command=self.remove_selected_files).pack(anchor=tk.E)

        ttk.Button(self.button_bar, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        ttk.Button(self.button_bar, text="Save Only", command=self.save_only).pack(side=tk.RIGHT, padx=(0, 10))
        ttk.Button(self.button_bar, text="Save & Launch", command=self.save_and_launch).pack(side=tk.RIGHT, padx=(0, 10))

    def toggle_client_id(self):
        self.client_id_entry.config(state="normal" if self.edit_client_id_var.get() else "disabled")

    def toggle_button_fields(self):
        state = "normal" if self.button_enabled_var.get() else "disabled"
        self.button_label_entry.config(state=state)
        self.button_url_entry.config(state=state)
        self.update_preview()

    def update_preview(self):
        c = self.preview_canvas
        c.delete("all")

        c.create_rectangle(0, 0, 320, 180, fill="#313338", outline="")

        c.create_rectangle(16, 16, 56, 56, fill="#5865f2", outline="", width=0)
        c.create_text(36, 36, text="Ae", fill="white", font=("", 12, "bold"))

        c.create_oval(44, 44, 60, 60, fill="#23a559", outline="#313338", width=2)

        c.create_text(66, 24, anchor="w", text="AegiRPC", fill="#f2f3f5", font=("", 11, "bold"))
        c.create_text(66, 42, anchor="w", text="Playing a game", fill="#b5bac1", font=("", 9))

        c.create_text(24, 76, anchor="w", text="DETAILS", fill="#b5bac1", font=("", 8, "bold"))
        if self.hide_file_names_var.get():
            details, state = self.config["default_details"], self.config["default_state"]
        else:
            details, state = "Project: example.ass", "Video: episode01.mkv"
        c.create_text(24, 92, anchor="w", text=details, fill="#dbdee1", font=("", 9))

        c.create_text(24, 112, anchor="w", text="STATE", fill="#b5bac1", font=("", 8, "bold"))
        c.create_text(24, 128, anchor="w", text=state, fill="#dbdee1", font=("", 9))

        if self.button_enabled_var.get():
            label = self.button_label_var.get().strip() or "Website"
            btn_w = max(len(label) * 7 + 24, 60)
            btn_x, btn_y = 16, 152
            c.create_rectangle(btn_x, btn_y, btn_x + btn_w, btn_y + 24, fill="#4e5058", outline="#6d6f78", width=1)
            c.create_text(btn_x + btn_w // 2, btn_y + 12, text=label, fill="white", font=("", 9))

    def browse_aegisub(self):
        if sys.platform == "win32":
            filetypes = [("Executable", "*.exe"), ("All files", "*.*")]
        else:
            filetypes = [("All files", "*.*")]

        path = filedialog.askopenfilename(title="Select Aegisub Executable", filetypes=filetypes)
        if path:
            self.aegisub_path = path
            if hasattr(self, 'aegi_path_var'):
                self.aegi_path_var.set(path)
            if hasattr(self, 'path_var'):
                self.path_var.set(path)

    def browse_subtitle(self):
        filetypes = [
            ("Subtitle files", "*.ass *.srt"),
            ("ASS files", "*.ass"),
            ("SRT files", "*.srt"),
            ("All files", "*.*")
        ]
        paths = filedialog.askopenfilenames(title="Select Subtitle Files", filetypes=filetypes)
        for path in self.root.tk.splitlist(paths):
            self.add_file(path)

    def add_file(self, path):
        """Adds a subtitle file to the launch list. Returns False after warning if it can't be used."""
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if ext not in SUPPORTED_EXTENSIONS:
            messagebox.showwarning("Warning", "Only .ass and .srt files are supported.")
            return False

        if not os.path.isfile(path):
            messagebox.showwarning("Warning", f"File not found:\n{path}")
            return False

        if path not in self.files:
            self.files.append(path)
            self.file_list.insert(tk.END, path)
        return True

    def add_typed_file(self):
        # Explorer's "Copy as path" wraps the path in quotes
        path = self.file_var.get().strip().strip('"')
        if path and self.add_file(path):
            self.file_var.set("")
            return True
        return not path

    def remove_selected_files(self):
        for index in reversed(self.file_list.curselection()):
            self.file_list.delete(index)
            del self.files[index]

    def validate_ui(self):
        """Copies the form into self.config. Returns False after warning if it is invalid."""
        self.update_config_from_ui()
        errors = validate_config(self.config)
        if errors:
            messagebox.showwarning("Invalid settings", "\n".join(errors))
            return False
        return True

    def set_file_associations(self):
        if not self.aegisub_path:
            messagebox.showwarning("Warning", "Please set the Aegisub path first.")
            return

        if not self.validate_ui():
            return

        try:
            script_path = install_files()
            old_path = self.config_path
            self.config_path = os.path.join(install_path(), "config.xml")
            self.save_config()
            self.config_path = old_path
        except Exception as e:
            messagebox.showerror("Error", f"Failed to install files: {e}")
            return

        try:
            warnings = install_associations(script_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set file associations: {e}")
            return

        message = f"Files installed to:\n{install_path()}\n\nFile associations set successfully!\n.ass and .srt files will now open with AegiRPC."
        if warnings:
            message += "\n\n" + "\n".join(warnings)
        messagebox.showinfo("Success", message)
        self.update_remove_button()

    def remove_file_associations(self):
        if not messagebox.askyesno(
            "Remove associations",
            "Restore the programs that opened .ass and .srt files before AegiRPC?\n\n"
            f"AegiRPC's files and settings in {install_path()} are kept.",
        ):
            return

        try:
            notes = remove_associations()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to restore file associations: {e}")
            return

        message = "File associations restored."
        if notes:
            message += "\n\n" + "\n".join(notes)
        messagebox.showinfo("Done", message)
        self.update_remove_button()

    def update_remove_button(self):
        if hasattr(self, "remove_assoc_button"):
            state = "normal" if associations_installed() else "disabled"
            try:
                self.remove_assoc_button.config(state=state)
            except tk.TclError:
                pass

    def save_install(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("Warning", "Please select the Aegisub executable.")
            return

        if not os.path.isfile(path):
            messagebox.showerror("Error", "The specified path does not exist.")
            return

        self.aegisub_path = path
        self.save_config()
        self.build_ui()

    def update_config_from_ui(self):
        self.config["aegisub_path"] = self.aegisub_path or ""
        if not hasattr(self, "client_id_var"):
            # Setup screen: the settings form doesn't exist yet
            return
        self.config["client_id"] = self.client_id_var.get().strip()
        self.config["button_enabled"] = self.button_enabled_var.get()
        self.config["button_label"] = self.button_label_var.get().strip()
        self.config["button_url"] = self.button_url_var.get().strip()
        self.config["project_name_source"] = self.project_name_var.get()
        self.config["hide_file_names"] = self.hide_file_names_var.get()
        self.config["tooltip_enabled"] = self.tooltip_var.get()
        self.config["hide_console"] = self.hide_console_var.get()

    def save_and_launch(self):
        # A path typed or pasted but not added yet still counts
        if not self.add_typed_file():
            return

        if not self.files:
            messagebox.showwarning("Warning", "Please add a subtitle file to launch.")
            return

        if not self.validate_ui():
            return
        self.save_config()

        self.result = {"action": "launch", "files": list(self.files)}
        self.root.quit()

    def save_only(self):
        if not self.validate_ui():
            return
        self.save_config()
        messagebox.showinfo("Saved", "Configuration saved successfully!")

    def cancel(self):
        self.result = {"action": "quit"}
        self.root.quit()

    def run(self):
        self.root.mainloop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        return self.result


def run_gui(config_path):
    return AegiRPCGUI(config_path).run()
