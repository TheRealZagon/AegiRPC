import ntpath
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import psutil
import pypresence

from common import (
    SUPPORTED_EXTENSIONS,
    TOOLTIP_TEXT,
    VERSION,
    find_aegisub,
    find_config_file,
    log,
    read_config,
    setup_logging,
    validate_config,
)

POLL_SECONDS = 10
REFRESH_SECONDS = 60
RETRY_SECONDS = 10
DISCORD_TEXT_MAX = 128
DETECT_ATTEMPTS = 5
RECONNECT_ATTEMPTS = 3


USAGE = """\
Usage: aegi_rpc [subtitle_file ...]

  With no arguments, opens the settings window.
  With one or more .ass/.srt files, opens them in Aegisub and shows them in Discord.

  -h, --help     show this message
  -V, --version  show the version"""


def show_dialog(message, error=False):
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        show = messagebox.showerror if error else messagebox.showinfo
        show("AegiRPC", message)
        root.destroy()
    except Exception:
        pass


def fatal(message):
    """Logs the error and, when there is no terminal to read it from, shows a dialog."""
    log.error(message)
    if sys.stderr is None or not sys.stderr.isatty():
        show_dialog(message, error=True)
    sys.exit(1)


def say(message):
    """Prints to the terminal, or shows a dialog in the windowed Windows build, which has none."""
    if sys.stdout is not None:
        print(message)
    else:
        show_dialog(message)


def load_config(config_file):
    """Loads and validates the config, filling in the Aegisub path if it is not set."""
    try:
        config = read_config(config_file)
    except FileNotFoundError:
        fatal(f"Config file '{config_file}' not found.")
    except ET.ParseError:
        fatal(f"Invalid XML in '{config_file}'.")
    except Exception as e:
        fatal(f"Config load error: {e}")

    errors = validate_config(config)
    if errors:
        fatal(f"Invalid settings in '{config_file}':\n" + "\n".join(errors))

    if config["aegisub_path"] and os.path.isfile(config["aegisub_path"]):
        log.info("Using Aegisub from config: %s", config["aegisub_path"])
    else:
        found = find_aegisub()
        if not found:
            fatal("Could not find Aegisub. Set its path in the AegiRPC settings window or in config.xml.")
        log.info("Found Aegisub executable: %s", found)
        config["aegisub_path"] = found

    return config


def parse_ass_file(file_path):
    """Returns (video_file, title) from an ASS file."""
    video_file, title = "", ""
    in_garbage, in_script_info = False, False

    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line == "[Aegisub Project Garbage]":
                in_garbage, in_script_info = True, False
            elif line == "[Script Info]":
                in_script_info, in_garbage = True, False
            elif line.startswith("[") and line.endswith("]"):
                in_garbage, in_script_info = False, False
            elif in_garbage and line.startswith("Video File: "):
                video_file = line.split("Video File: ", 1)[1].strip()
            elif in_script_info and line.startswith("Title: "):
                title = line.split("Title: ", 1)[1].strip()

    return video_file, title


def read_subtitle_file(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        fatal(
            f"Unsupported file extension '.{ext}' for '{path}'.\n"
            f"Supported extensions: {', '.join('.' + e for e in SUPPORTED_EXTENSIONS)}"
        )
    if not os.path.isfile(path):
        fatal(f"Subtitle file '{path}' not found.")

    is_srt = ext == "srt"
    video_file, title = "", ""
    if not is_srt:
        try:
            video_file, title = parse_ass_file(path)
        except OSError as e:
            fatal(f"Could not read '{path}': {e}")

    return {
        "file_name": os.path.basename(path),
        "video_file": video_file,
        "title": title,
        "is_srt": is_srt,
        "path": path,
    }


def running_process_names():
    for proc in psutil.process_iter(["name", "status"]):
        if proc.info["status"] != psutil.STATUS_ZOMBIE:
            yield (proc.info["name"] or "").lower()


def is_aegisub_running(config):
    if sys.platform == "win32":
        known_names = {"aegisub.exe", "aegisub32.exe"}
    else:
        known_names = {"aegisub", "aegisub-arch1t3cht", "aegisub32"}
    known_names.add(os.path.basename(config["aegisub_path"]).lower())

    return any(name in known_names for name in running_process_names())


def capture_child_pids(pid):
    """Returns child PIDs of a process, for wrapper scripts that spawn the real Aegisub."""
    child_pids = []
    try:
        proc = psutil.Process(pid)
        for _ in range(5):
            child_pids = [child.pid for child in proc.children(recursive=True)]
            if child_pids:
                break
            time.sleep(0.1)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return child_pids


def is_alive(proc):
    # Children we launched and never wait() on stay zombies, which is_running() still reports as running
    return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE


def are_aegisub_instances_running(pids, config=None):
    """True if any tracked Aegisub PID or its children are still alive."""
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            if is_alive(proc):
                return True
            for child in proc.children(recursive=True):
                if is_alive(child):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sys.platform != "win32" and config is not None:
        return is_aegisub_running(config)

    return False


def instances_alive(pids, config):
    if pids:
        return are_aegisub_instances_running(pids, config)
    return is_aegisub_running(config)


def project_name(fd, config):
    if fd["is_srt"] or config["project_name_source"] != "ass_title":
        return fd["file_name"]
    return fd["title"] or None


def format_multi_details(file_data_list, config):
    names = [project_name(fd, config) or fd["file_name"] for fd in file_data_list]

    if len(names) == 1:
        return f"Editing {names[0]}"
    if len(names) == 2:
        return f"Editing {names[0]} and {names[1]}"
    return f"Editing {names[0]} and {len(names) - 1} others"


def build_buttons(config):
    label, url = config["button_label"], config["button_url"]
    if config["button_enabled"] and label and url:
        return [{"label": label, "url": url}]
    return None


def build_presence(config, file_data_list, start_time):
    details = config["default_details"]
    state = config["default_state"]

    if not config["hide_file_names"]:
        if len(file_data_list) > 1:
            details = format_multi_details(file_data_list, config)
        else:
            name = project_name(file_data_list[0], config)
            if name:
                details = f"Project: {name}"

        video_file = file_data_list[-1]["video_file"]
        if video_file:
            # Project files may have been saved on another OS
            state = f"Video: {ntpath.basename(video_file)}"

    presence = {
        "details": details[:DISCORD_TEXT_MAX],
        "state": state[:DISCORD_TEXT_MAX],
        "large_image": config["large_image"],
        "small_image": config["small_image"],
        "small_text": config["small_text"],
        "start": start_time,
    }

    if config["tooltip_enabled"]:
        presence["large_text"] = TOOLTIP_TEXT

    buttons = build_buttons(config)
    if buttons:
        presence["buttons"] = buttons

    return presence


def hide_console():
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        log.info("Console window hidden.")
    except Exception as e:
        log.warning("Error hiding console: %s", e)


def cleanup_rpc(rpc):
    if rpc:
        log.info("Closing RPC...")
        try:
            rpc.close()
        except Exception as e:
            log.warning("RPC close error: %s", e)
        log.info("RPC closed.")


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        say(USAGE)
        return
    if len(sys.argv) == 2 and sys.argv[1] in ("-V", "--version"):
        say(f"AegiRPC {VERSION}")
        return

    setup_logging()

    if len(sys.argv) < 2:
        try:
            from gui import run_gui
        except ImportError as e:
            fatal(
                f"Could not start the settings window: {e}\n"
                "On Linux, install the Tk package for Python (e.g. python3-tk).\n"
                f"{USAGE}"
            )

        try:
            config_path = find_config_file()
        except OSError as e:
            fatal(str(e))

        result = run_gui(config_path)
        if not result or result.get("action") != "launch":
            sys.exit(0)
        subtitle_files = result["files"]

        # Settings may have been saved to a different file than the one the window opened
        config_path = find_config_file()
    else:
        try:
            config_path = find_config_file()
        except OSError as e:
            fatal(str(e))
        subtitle_files = sys.argv[1:]

    config = load_config(config_path)
    file_data_list = [read_subtitle_file(sf) for sf in subtitle_files]

    start_time = int(time.time())
    pids = []
    try:
        for fd in file_data_list:
            log.info('Launching Aegisub: "%s" "%s"', config["aegisub_path"], fd["path"])
            proc = subprocess.Popen([config["aegisub_path"], fd["path"]])
            pids.append(proc.pid)
            child_pids = capture_child_pids(proc.pid)
            pids.extend(child_pids)
            if child_pids:
                log.info("  Captured child PIDs: %s", child_pids)
            time.sleep(1)

        log.info("Waiting for Aegisub to start...")
        time.sleep(3)

        if config["hide_console"] and sys.platform == "win32":
            hide_console()

    except FileNotFoundError:
        fatal(f"Aegisub not found at '{config['aegisub_path']}'.")
    except Exception as e:
        fatal(f"Aegisub launch error: {e}")

    for i in range(DETECT_ATTEMPTS):
        if is_aegisub_running(config):
            log.info("Aegisub is running! Setting up Discord Rich Presence...")
            break
        if i < DETECT_ATTEMPTS - 1:
            log.info("Waiting for Aegisub to start (attempt %d/%d)...", i + 1, DETECT_ATTEMPTS)
            time.sleep(2)
    else:
        log.warning("Could not detect Aegisub running after multiple attempts.")
        log.warning("Continuing anyway - Discord status will update when Aegisub is detected.")

    presence = build_presence(config, file_data_list, start_time)
    rpc = None
    try:
        def connect_rpc():
            nonlocal rpc
            cleanup_rpc(rpc)
            rpc = None
            new_rpc = pypresence.Presence(config["client_id"])
            new_rpc.connect()
            rpc = new_rpc
            log.info("Discord Rich Presence connected.")
            rpc.update(**presence)
            log.info("RPC updated.")

        log.info("Connecting to Discord...")
        while True:
            try:
                connect_rpc()
                break
            except pypresence.exceptions.InvalidID:
                fatal(f"Invalid client ID: {config['client_id']}. Check config.xml.")
            except pypresence.exceptions.DiscordNotFound:
                log.info("Discord not found. Retrying in %ds (Ctrl+C to exit)...", RETRY_SECONDS)
            except Exception as e:
                log.warning("Discord connection error: %s. Retrying in %ds (Ctrl+C to exit)...", e, RETRY_SECONDS)

            time.sleep(RETRY_SECONDS)
            if not instances_alive(pids, config):
                log.info("Aegisub closed before Discord was reachable. Exiting.")
                return

        last_refresh = time.monotonic()

        log.info("Monitoring Aegisub (press Ctrl+C to exit)...")
        while True:
            time.sleep(POLL_SECONDS)

            if not instances_alive(pids, config):
                log.info("All Aegisub instances closed. Exiting.")
                break

            # Same payload and start time: this only detects a dropped connection
            if time.monotonic() - last_refresh < REFRESH_SECONDS:
                continue

            try:
                rpc.update(**presence)
                last_refresh = time.monotonic()
            except (pypresence.exceptions.PyPresenceException, OSError, AttributeError) as e:
                log.warning("Discord connection lost: %s", e)
                reconnected = False
                for attempt in range(RECONNECT_ATTEMPTS):
                    wait = 2 ** (attempt + 1)
                    log.info("Reconnecting in %ds (attempt %d/%d)...", wait, attempt + 1, RECONNECT_ATTEMPTS)
                    time.sleep(wait)
                    try:
                        connect_rpc()
                        log.info("Reconnected to Discord.")
                        last_refresh = time.monotonic()
                        reconnected = True
                        break
                    except Exception as retry_e:
                        log.warning("Reconnect failed: %s", retry_e)
                if not reconnected:
                    log.error("Max retries reached. Exiting.")
                    break

    except KeyboardInterrupt:
        log.info("Exiting.")
    except Exception as e:
        fatal(f"Discord RPC error: {e}")
    finally:
        cleanup_rpc(rpc)


if __name__ == "__main__":
    main()
