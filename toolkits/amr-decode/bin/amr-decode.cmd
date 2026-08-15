@echo off
rem AMIDI amr-decode 垫片：把本目录加入 PATH 后即可直接使用 amr-decode
python "%~dp0..\amr_decode.py" %*
