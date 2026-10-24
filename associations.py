import json
import os
import shutil
import subprocess
import sys

from common import install_path, log

BACKUP_NAME = "associations_backup.json"

WINDOWS_TYPES = {
    ".ass": ("AegiRPC.ASS", "Aegisub Subtitle File"),
    ".srt": ("AegiRPC.SRT", "SubRip Subtitle File"),
}

DESKTOP_FILE = "aegi-rpc.desktop"
MIME_TYPES = ["text/x-ssa", "application/x-ssa", "application/x-subrip", "application/x-ass"]


def desktop_quote(arg):
    """Quotes an argument for the Exec= line of a .desktop file."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    return f'"{escaped}"'


def _backup_file():
    return os.path.join(install_path(), BACKUP_NAME)


def _load_previous():
    try:
        with open(_backup_file(), encoding="utf-8") as f:
            return json.load(f).get("previous", {})
    except (OSError, ValueError):
        return {}


def _save_previous(previous):
    os.makedirs(install_path(), exist_ok=True)
    with open(_backup_file(), "w", encoding="utf-8") as f:
        json.dump({"previous": previous}, f, indent=2)


def _forget_previous():
    try:
        os.remove(_backup_file())
    except FileNotFoundError:
        pass


def associations_installed():
    if sys.platform == "win32":
        import winreg
        return _win_default(winreg, ".ass") == WINDOWS_TYPES[".ass"][0]
    return os.path.isfile(os.path.join(_applications_dir(), DESKTOP_FILE))


def install_associations(program_path):
    """Makes .ass/.srt open with program_path. Returns a list of warnings to show the user."""
    if sys.platform == "win32":
        return _install_windows(program_path)
    return _install_linux(program_path)


def remove_associations():
    """Restores the handlers that were set before install_associations(). Returns notes to show the user."""
    if sys.platform == "win32":
        return _remove_windows()
    return _remove_linux()


# Windows

def _classes_path(name):
    return f"Software\\Classes\\{name}"


def _win_default(winreg, ext):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _classes_path(ext)) as key:
            return winreg.QueryValueEx(key, "")[0] or None
    except FileNotFoundError:
        return None


def _win_user_choice(winreg, ext):
    path = f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\{ext}\\UserChoice"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "ProgId")[0]
    except FileNotFoundError:
        return None


def _win_delete_tree(winreg, path):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    with key:
        while True:
            try:
                sub = winreg.EnumKey(key, 0)
            except OSError:
                break
            _win_delete_tree(winreg, f"{path}\\{sub}")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


def _win_notify():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception as e:
        log.warning("Could not notify Explorer of the association change: %s", e)


def _install_windows(program_path):
    import winreg

    if getattr(sys, "frozen", False):
        cmd = f'"{program_path}" "%1"'
    else:
        cmd = f'"{sys.executable}" "{program_path}" "%1"'

    previous = _load_previous()
    for ext, (type_name, _) in WINDOWS_TYPES.items():
        current = _win_default(winreg, ext)
        if current != type_name:
            previous[ext] = current
    _save_previous(previous)

    warnings = []
    for ext, (type_name, desc) in WINDOWS_TYPES.items():
        winreg.SetValue(winreg.HKEY_CURRENT_USER, _classes_path(ext), winreg.REG_SZ, type_name)

        type_path = _classes_path(type_name)
        winreg.SetValue(winreg.HKEY_CURRENT_USER, type_path, winreg.REG_SZ, desc)
        winreg.SetValue(winreg.HKEY_CURRENT_USER, f"{type_path}\\DefaultIcon", winreg.REG_SZ, f'"{program_path}",0')
        winreg.SetValue(winreg.HKEY_CURRENT_USER, f"{type_path}\\shell\\open\\command", winreg.REG_SZ, cmd)

        choice = _win_user_choice(winreg, ext)
        if choice and choice != type_name:
            warnings.append(
                f"Windows is set to open {ext} files with '{choice}' and may ignore this change. "
                f"Right-click a {ext} file, choose Open with, then AegiRPC, and Always."
            )

    _win_notify()
    return warnings


def _remove_windows():
    import winreg

    previous = _load_previous()
    notes = []

    for ext, (type_name, _) in WINDOWS_TYPES.items():
        if _win_default(winreg, ext) == type_name:
            restore = previous.get(ext)
            path = _classes_path(ext)
            if restore:
                winreg.SetValue(winreg.HKEY_CURRENT_USER, path, winreg.REG_SZ, restore)
            else:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
                    winreg.DeleteValue(key, "")
                    subkeys, values, _ = winreg.QueryInfoKey(key)
                if not subkeys and not values:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        else:
            notes.append(f"{ext} is no longer set to AegiRPC, so its handler was left as it is.")

        _win_delete_tree(winreg, _classes_path(type_name))

    _forget_previous()
    _win_notify()
    return notes


# Linux

def _applications_dir():
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(data_home, "applications")


def _mimeapps_files():
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return [
        os.path.join(config_home, "mimeapps.list"),
        os.path.join(_applications_dir(), "mimeapps.list"),
    ]


def _xdg_mime(*args):
    return subprocess.run(["xdg-mime", *args], capture_output=True, text=True, timeout=5)


def _xdg_default(mime):
    return _xdg_mime("query", "default", mime).stdout.strip() or None


def _unset_mime_default(mime):
    """xdg-mime can't unset a default, so drop our entry from mimeapps.list directly."""
    for path in _mimeapps_files():
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()

        out, section, changed = [], None, False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped
            elif section == "[Default Applications]":
                key, _, value = stripped.partition("=")
                if key.strip() == mime:
                    apps = [a for a in value.split(";") if a]
                    kept = [a for a in apps if a != DESKTOP_FILE]
                    if len(kept) != len(apps):
                        changed = True
                        if kept:
                            out.append(f"{mime}={';'.join(kept)};")
                        continue
            out.append(line)

        if changed:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(out) + "\n")


def _install_linux(program_path):
    if not shutil.which("xdg-mime"):
        raise RuntimeError("xdg-mime was not found. Install xdg-utils to set file associations.")

    previous = _load_previous()
    for mime in MIME_TYPES:
        current = _xdg_default(mime)
        if current != DESKTOP_FILE:
            previous[mime] = current
    _save_previous(previous)

    if getattr(sys, "frozen", False):
        exec_line = f"{desktop_quote(program_path)} %f"
    else:
        exec_line = f"{desktop_quote(sys.executable)} {desktop_quote(program_path)} %f"

    desktop_dir = _applications_dir()
    os.makedirs(desktop_dir, exist_ok=True)
    desktop_path = os.path.join(desktop_dir, DESKTOP_FILE)
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write(f"""[Desktop Entry]
Name=AegiRPC
Comment=Discord Rich Presence for Aegisub
Exec={exec_line}
MimeType={';'.join(MIME_TYPES)};
Type=Application
Terminal=false
Categories=AudioVideo;Video;
""")
    os.chmod(desktop_path, 0o755)

    for mime in MIME_TYPES:
        _xdg_mime("default", DESKTOP_FILE, mime)

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", desktop_dir], capture_output=True, timeout=5)
    return []


def _remove_linux():
    previous = _load_previous()
    notes = []

    if shutil.which("xdg-mime"):
        for mime in MIME_TYPES:
            if _xdg_default(mime) != DESKTOP_FILE:
                continue
            restore = previous.get(mime)
            if restore:
                _xdg_mime("default", restore, mime)
            else:
                _unset_mime_default(mime)
    else:
        notes.append("xdg-mime was not found, so default applications could not be restored.")

    desktop_dir = _applications_dir()
    try:
        os.remove(os.path.join(desktop_dir, DESKTOP_FILE))
    except FileNotFoundError:
        pass
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", desktop_dir], capture_output=True, timeout=5)

    _forget_previous()
    return notes
