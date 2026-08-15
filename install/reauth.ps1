# reauth.ps1 — Re-authenticate with Toodledo (Windows)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$ScriptDir\reauth.py" @args
