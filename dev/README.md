# Mongoose Development Environment

Use the development environment when you want to test the current repository
code without replacing the installed `mongoose` release.

The setup creates:

- `.dev-bin\mongoose-dev.cmd`
- `.dev-bin\Njord-dev.cmd`
- `.dev-localappdata\Agents\...`

The normal installed command remains separate:

```powershell
mongoose --version
```

The source-backed development command is:

```powershell
.\dev\setup-dev-env.ps1
.\.dev-bin\mongoose-dev.cmd --version
```

For a shorter terminal session:

```powershell
.\dev\setup-dev-env.ps1
$env:Path = "$PWD\.dev-bin;$env:Path"
mongoose-dev --version
mongoose-dev install Njord
Njord-dev
```

`mongoose-dev` runs `mongoose\mongoose.py` from the current checkout every
time. After editing source code, run the same command again; no release build,
GitHub Release, or normal install update is required.

`Njord-dev` runs `agents\njord\agent.py` from the current checkout and points
LLM invocation at `mongoose-dev` state. Configure a dev LLM profile separately
from your normal install:

```powershell
mongoose-dev llm setup
mongoose-dev llm ping
Njord-dev
```

Reset the dev state:

```powershell
.\dev\setup-dev-env.ps1 -Reset
```

This removes `.dev-localappdata` and recreates the source-backed shims. It does
not touch `%LOCALAPPDATA%\Agents`, the official `mongoose.exe`, or normal
installed agents.

