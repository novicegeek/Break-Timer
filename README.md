# Break Timer

A small desktop break reminder for Windows. It alternates between a **work**
timer and a **break** timer, and when either one runs out it pops up a separate
alert window with the next action one click away.

The UI is HTML/CSS rendered in a native window through
[pywebview](https://pywebview.flowrl.com/) (Microsoft Edge WebView2 on Windows),
while the timer itself is plain Python.

## Features

- Work / break countdown with a progress ring
- Independent pop-up alert window when a timer finishes, shown next to the
  main window and raised above other applications once
- Start, pause, reset, and switch between work and break at any time
- `+5 Minutes` shortcut to extend the current stage from the alert
- Settings (work and break durations) are saved to `settings.json` and restored
  on the next launch
- Optional audible cue (Web Audio beep) together with the alert
- Ships as a single `.exe` that runs by double-clicking — no Python required

## Requirements

- Windows 10/11 with the WebView2 runtime (pre-installed on Windows 11)
- Python 3.13 for running from source
- [`pywebview`](https://pypi.org/project/pywebview/) 6.x
- [`pyinstaller`](https://pypi.org/project/pyinstaller/) 6.x for building the exe

Install the dependencies:

```powershell
pip install pywebview pyinstaller
```

## Run from source

```powershell
python timer.py
```

## Build the executable

The build is driven by `Break Timer.spec`, which bundles `index.html`,
`alert.html`, and `timer.png` and uses `timer.ico` as the executable icon:

```powershell
pyinstaller --noconfirm "Break Timer.spec"
```

The result is `dist\Break Timer.exe`. Keep `settings.json` next to the
executable if you want to carry your durations over; it is created automatically
on first change.

## Usage

1. Set the **Work** and **Break** durations in minutes and seconds.
2. Press **Start** to begin the work timer.
3. When work ends, an alert window appears with **Start Break**, **+5 Minutes**,
   and the usual close button.
4. When the break ends, the same alert offers **Start Working**.

## Project layout

| File | Purpose |
| --- | --- |
| `timer.py` | Application entry point: timer state machine, pywebview bridge, and the alert pop-up |
| `index.html` | Main window UI (timer ring, buttons, settings) |
| `alert.html` | Content of the pop-up alert window |
| `Break Timer.spec` | PyInstaller build description |
| `timer.png` | Source image used to generate the window/executable icon |
| `timer.ico` | Icon generated from `timer.png` and embedded in the exe |
| `settings.json` | Saved work/break durations (generated at runtime) |
| `dist\Break Timer.exe` | Packaged application |

## Notes

- The alert window appears at the position of the main window, so it always
  lands on-screen on scaled (high-DPI) displays.
- The alert is raised above other windows only when it opens; it is not kept
  pinned on top afterwards.
- Only Windows is supported: the alert placement and foreground handling use
  Win32 APIs (`ctypes`) and the WinForms backend of pywebview.
