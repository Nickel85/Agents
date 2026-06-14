# Repository Working Rules

## Development Testing

Use the source-backed development environment for testing current code changes.
Do not replace the normal installed `mongoose` release just to test repository
logic.

Preferred setup from the repository root:

```powershell
.\dev\setup-dev-env.ps1
$env:Path = "$PWD\.dev-bin;$env:Path"
```

Use these commands for source-change testing:

```powershell
mongoose-dev --version
mongoose-dev list
mongoose-dev install Njord
mongoose-dev run Njord hello-world --name Dev
Njord-dev
```

`mongoose-dev` and `Njord-dev` run the current checkout and keep state under
`.dev-localappdata`. The normal installed `mongoose` command and
`%LOCALAPPDATA%\Agents` state are reserved for explicit installed-release,
installer, self-update, and release-asset validation.

When validating a change:

- Prefer `mongoose-dev` for Mongoose CLI behavior that should reflect the
  current checkout.
- Prefer `Njord-dev` for interactive Njord REPL behavior.
- Use direct `python tests\...` or `powershell ... tests\...` validation scripts
  when they intentionally isolate state for repeatable automation.
- Use installed `mongoose` only when the task is specifically about the
  installed release, the compiled executable, update behavior, or PATH
  integration.

