# AegiRPC

Discord Rich Presence for [Aegisub](https://aegisub.org). AegiRPC launches Aegisub with your subtitle file and shows what you're working on in your Discord status: the project name, the video file, the time elapsed and an optional website button. When you close Aegisub it clears the status and exits.

Supports SubStation Alpha (`.ass`) and SubRip (`.srt`) files, on Windows and Linux. Not affiliated with the Aegisub project.

## Usage

Start AegiRPC with no arguments to open the settings window, where you can pick the Aegisub executable, adjust the presence and launch one or more subtitle files. Or pass the files directly:

```
AegiRPC.exe subtitle.ass
python aegi_rpc.py subtitle.srt
```

`--help` and `--version` do what you'd expect.

Discord must be running (the desktop app, not the browser). If it isn't, AegiRPC keeps retrying until you start it or close Aegisub.

### Privacy

By default your Discord profile shows the subtitle file name and the name of the video it is attached to. Both are visible to anyone who can see your status, which may give away unreleased work. Turn on **Hide file names** in the settings window (or `hide_file_names` in `config.xml`) to show only the `default_details` and `default_state` text instead. The website button and the elapsed time stay.

### Installation (Default editor)

The settings window has an **Install & Set as Default Editor** button. It copies AegiRPC to a permanent location, so you can delete the download folder, and makes `.ass`/`.srt` files open through it.

| OS      | Installed to                  | What changes                                                      |
|---------|-------------------------------|-------------------------------------------------------------------|
| Windows | `%LOCALAPPDATA%\AegiRPC`      | `HKCU\Software\Classes` entries for `.ass` and `.srt`             |
| Linux   | `~/.local/share/aegi_rpc`     | `~/.local/share/applications/aegi-rpc.desktop` and `xdg-mime` defaults |

The previous handlers are saved to `associations_backup.json` in the install folder first. **Remove & Restore Previous Defaults** in the same window puts them back and removes the entries above; the installed files and your settings are kept, and can be deleted by hand.

On Windows 10/11 the OS may keep a previous choice; if so, use *Open with → Choose another app → AegiRPC* once.

## Configuration

Settings live in `config.xml`, next to the program, or in the install folder above. The settings window edits it for you.

| Key                   | Meaning                                                           |
|-----------------------|-------------------------------------------------------------------|
| `client_id`           | Discord application ID the presence is published under            |
| `default_details`     | First line when no project name is available                      |
| `default_state`       | Second line when no video file is known                           |
| `large_image`, `small_image`, `small_text` | Art asset names and tooltip of the small image |
| `aegisub_path`        | Path to Aegisub. Leave empty to auto-detect                       |
| `button_enabled`, `button_label`, `button_url` | Optional button (label up to 32 characters, `http(s)` URL) |
| `project_name_source` | `ass_filename` or `ass_title` (the `Title:` in the script info)   |
| `hide_file_names`     | Don't show the subtitle or video file name; show the default text |
| `tooltip_enabled`     | Show a tooltip on the large image                                 |
| `hide_console`        | Hide the console window on Windows when running from source       |

### Using your own Discord application

The default `client_id`, images and button belong to the author's fansub group. To use your own, create an application in the [Discord Developer Portal](https://discord.com/developers/applications), upload art under *Rich Presence → Art Assets* with the names set in `large_image` / `small_image`, and put the application ID in `client_id`. The button and the large-image tooltip text can be changed or turned off in the settings window.

## Running from source

Requires Python 3.9+ with Tk (on Linux, install your distro's `python3-tk`).

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python aegi_rpc.py
```

## Building an executable

```
pip install -r requirements-dev.txt
pyinstaller AegiRPC.spec
```

PyInstaller does not cross-compile: build the Windows `.exe` on Windows. The GitHub Actions workflow in `.github/workflows/build.yml` does this for you: it runs the tests, builds the Windows and Linux binaries on every push, and pushing a tag like `v1.0.0` publishes them as a release together with `SHA256SUMS.txt`. To release, bump `VERSION` in `common.py`, commit, then tag with the same number (the workflow fails if they differ). Unsigned PyInstaller executables are sometimes flagged by antivirus software; compare the SHA-256 of a download against the one published with the release.

## Logs and tests

Messages are also written to `aegirpc.log` in the install folder, which is the only place to look for errors in the windowed Windows build.

```
python -m unittest discover -s tests
```

## License

BSD 3-Clause, the same license as Aegisub. See [LICENSE](LICENSE). The icon is derived from the Aegisub logo; see [NOTICE](NOTICE). The icon is derived from the Aegisub logo; see [NOTICE](NOTICE).
