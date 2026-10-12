$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$notebook = Join-Path $root 'notebooks/colab_vscode.ipynb'
& code --reuse-window $root $notebook
if ($LASTEXITCODE -ne 0) { throw 'VS Code could not open the Colab notebook' }
