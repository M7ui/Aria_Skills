@echo off
rem Aria aria-decode shim: add this dir to PATH to use the `aria-decode` command directly
python "%~dp0..\aria_decode.py" %*
