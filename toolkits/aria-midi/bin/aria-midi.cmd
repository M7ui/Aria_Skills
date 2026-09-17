@echo off
rem Aria aria-midi shim: add this dir to PATH to use the `aria-midi` command directly
python "%~dp0..\aria_midi.py" %*
