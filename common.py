import logging
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from logging.handlers import RotatingFileHandler

VERSION = "1.0.0"
TOOLTIP_TEXT = "AegiRPC by Zagon"
SUPPORTED_EXTENSIONS = ("ass", "srt")

DEFAULTS = {
    "client_id": "736734207556059187",
    "default_details": "Working on Subtitles",
    "default_state": "General Editing",
    "large_image": "aegisub_large",
    "small_image": "aegisub_small",
    "small_text": "Aegisub",
    "aegisub_path": "",
    "button_enabled": True,
    "button_label": "Fansub website",
    "button_url": "https://www.zagonsubs.org",
    "project_name_source": "ass_filename",
    "hide_file_names": False,
    "tooltip_enabled": False,
    "hide_console": True,
}
BOOL_KEYS = ("hide_file_names", "tooltip_enabled", "hide_console", "button_enabled")

DISCORD_BUTTON_LABEL_MAX = 32
DISCORD_BUTTON_URL_MAX = 512

log = logging.getLogger("aegirpc")


def install_path():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local")), "AegiRPC")
    return os.path.expanduser("~/.local/share/aegi_rpc")


def setup_logging():
    if log.handlers:
        return
    log.setLevel(logging.INFO)

    # Windowed builds have no stderr
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(console)

    try:
        os.makedirs(install_path(), exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(install_path(), "aegirpc.log"),
            maxBytes=256 * 1024, backupCount=1, encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(file_handler)
    except OSError:
        pass


def read_config(path):
    """Loads the XML config over DEFAULTS. Raises OSError or ET.ParseError."""
    config = DEFAULTS.copy()
    root = ET.parse(path).getroot()

    for key in DEFAULTS:
        elem = root.find(key)
        text = elem.text.strip() if elem is not None and elem.text else ""
        if not text:
            continue
        if key in BOOL_KEYS:
            config[key] = text.lower() == "true"
        elif key == "project_name_source":
            config[key] = text.lower()
        else:
            config[key] = text
    return config


def write_config(path, config):
    root = ET.Element("config")
    for key in DEFAULTS:
        value = config.get(key, DEFAULTS[key])
        ET.SubElement(root, key).text = str(value).lower() if isinstance(value, bool) else str(value)
    ET.indent(root, space="    ")
    with open(path, "wb") as f:
        f.write(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def validate_config(config):
    """Returns a list of problems that would make Discord reject the presence."""
    errors = []

    if not config["client_id"].strip().isdigit():
        errors.append("Client ID must be a number.")

    if config["button_enabled"]:
        label = config["button_label"].strip()
        url = config["button_url"].strip()
        if len(label) > DISCORD_BUTTON_LABEL_MAX:
            errors.append(f"Button label must be at most {DISCORD_BUTTON_LABEL_MAX} characters.")
        if url and (len(url) > DISCORD_BUTTON_URL_MAX or not re.match(r"https?://\S+$", url)):
            errors.append("Button URL must start with http:// or https://.")

    return errors


def is_writable(path):
    """Tries to open the file for writing without changing it (os.access ignores ACLs on Windows)."""
    try:
        with open(path, "ab"):
            return True
    except OSError:
        return False


def save_config_file(path, config):
    """Writes the config to path, or to the user's folder if path is read-only. Returns where it went."""
    try:
        write_config(path, config)
        return path
    except OSError as e:
        fallback = os.path.join(install_path(), "config.xml")
        if os.path.abspath(fallback) == os.path.abspath(path):
            raise
        log.warning("Could not write %s (%s). Saving to %s instead.", path, e, fallback)
        os.makedirs(install_path(), exist_ok=True)
        write_config(fallback, config)
        return fallback


def find_config_file():
    """Returns the path of an existing config.xml, creating a default one if there is none."""
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    local = os.path.join(script_dir, "config.xml")
    user = os.path.join(install_path(), "config.xml")

    # A config we can't write (e.g. in Program Files) is only a template. Saved settings go to
    # the user's folder, so that copy has to win once it exists.
    if os.path.isfile(local) and not is_writable(local) and os.path.isfile(user):
        possible_locations = [user]
    else:
        possible_locations = [local, user, "config.xml"]
    for location in possible_locations:
        if os.path.isfile(location):
            log.info("Using config file: %s", location)
            return location

    for directory in (script_dir, install_path()):
        path = os.path.join(directory, "config.xml")
        try:
            os.makedirs(directory, exist_ok=True)
            write_config(path, DEFAULTS)
        except OSError as e:
            log.warning("Could not create config at %s: %s", path, e)
            continue
        log.info("No config.xml found. Created default at: %s", path)
        return path

    raise OSError("Could not create a config.xml anywhere")


def find_aegisub():
    """Returns the path of the Aegisub executable, or None."""
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    if sys.platform == "win32":
        names = ("aegisub.exe", "aegisub32.exe")
        candidates = [os.path.join(script_dir, n) for n in names]
        candidates += [shutil.which(n) for n in names]
        candidates += [
            r"C:\Program Files\Aegisub\aegisub.exe",
            r"C:\Program Files (x86)\Aegisub\aegisub.exe",
        ]
    else:
        candidates = [
            shutil.which("aegisub"),
            os.path.join(script_dir, "aegisub"),
            "/usr/bin/aegisub",
            "/usr/local/bin/aegisub",
        ]

    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None
