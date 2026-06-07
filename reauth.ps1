# reauth.ps1 — Re-authenticate with Toodledo and save fresh OAuth tokens.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$ScriptDir\reauth.py" @args
