# InstructionX Plugin Development — An Introductory Guide

InstructionX is a plugin-integration framework of no small versatility. By the judicious combination of plugins serving differing ends, it enables the user to fashion a personalised, all-in-one toolkit exactly attuned to the manner in which they work.

## Part 1: The Preparation of the Environment

The InstructionX framework has been composed in Python 3.14.x upon PySide6, and depends upon `uv` for the governance of its Python environment. It is therefore incumbent upon you, before all else, to install `uv` upon your machine.

Upon an IBM-compatible computer — that is to say, upon the Windows platform — be so good as to issue the following command from PowerShell:

```shell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Upon a Macintosh, or upon a Linux desktop, be so good as to run the following instead:

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Having installed `uv`, open `PowerShell` (or `Terminal`) within the folder in which you propose to house the project, and thereupon clone the framework from this project's GitHub repository:

```shell
git clone https://github.com/KKPIP-Tech/InstructionX.git
```

Thereafter, proceed into the directory thus created:

```shell
cd InstructionX
```

Commence the application by means of the command set out below. Upon its very first run, `uv` will attend to the configuration of the environment on your behalf, taking its direction from `uv.lock`:

```shell
uv run main.py
```

It should be observed that `uv run` brings the environment into harmony with `uv.lock`, establishing a virtual environment should none presently exist, and thereafter sets the application in motion. This is the manner of launch recommended by the framework.

## Part 2: The Disposition of Your Plugin Repository

Before you commence, I would ask you to take a moment to acquaint yourself with the framework's branches:

- `main` — the release branch, upon which versions are promulgated and hotfixes issued;
- `dev` — the development branch, which bears the latest features and corrections;
- `test` — the branch upon which the framework's tests are maintained.

You shall further be required to determine whether you are developing in the capacity of an **official** developer or of a **third-party** developer:

- Should you be an official developer, your plugin repository is to reside in the framework's `plugin` directory;
- should you be a third-party developer, it is to reside in the `custom_plugin` directory.

> Permit me to impress upon you that your plugin repository is a git repository **in its own right** — it possesses its own `.git`, and stands wholly apart from the framework. You are to clone it into the framework's root, and thereupon move it into (or rename it to) `plugin` or `custom_plugin`, according to your development mode. Whatever you commit therein appertains to your repository alone, and exercises no influence whatsoever upon the framework. The framework itself is **furnished with no plugins whatever**: `plugin/` and `custom_plugin/` come into being containing nothing more than an `__init__.py` (the local development copy, it should be added, likewise holds a small number of official and example plugins, retained solely for local verification).

Your plugin repository ought to maintain no fewer than three branches — `main`, `dev` and `test` — to the end that its code be kept in good order; larger teams may extend this scheme as they judge fit.

Should you maintain a remote repository, you may, once initialisation is complete, push all three branches to it.

> **A word upon the internal disposition of the repository**: an `IXRepo.json` index is seated at its root, and every plugin occupies a first-level sub-directory of its own (containing `IXPlugin.json`, `entrance.py`, `information.py`, `service.py`, `config/`, `text/` and so forth). For the full disposition of the repository, for the field-by-field conventions governing the descriptor files, and for the complete process of development, you are to defer to **`AGENTS-for-PLUGIN-DEV.md`** at the repository root, which stands as the authoritative reference.

## Part 3: The Assistance of AI

For the better accommodation of AI-assisted development, the repository is accompanied by two AGENTS files. Both are, at present, known to serve well with `Kimi Code (CLI)`, `Claude Code (CLI)`, `OpenCode` and `Codex`.

At the root of the repository you will find `AGENTS.md` and `AGENTS-for-PLUGIN-DEV.md`.

Should your present session be concerned chiefly with the framework itself — as, for example, in raising an issue against the `InstructionX` repository, or in proffering a pull request for the correction of a fault — it suffices that you state your requirement to the AI tool directly.

Should your present session, on the other hand, be concerned with the development of a plugin, open your first exchange with the AI by means of the prompt set out below, amending those portions enclosed within `<>` as your circumstances demand:

```
I am an <official/third-party> plugin developer. Please take AGENTS.md as your starting point, and hold `AGENTS-for-PLUGIN-DEV.md` as your reference. I am at present engaged in the development of a plugin upon the <main/dev/test> branch.

I have the following requirement to lay before you: <state your requirement here>, set out in detail as:

1. <requirement 1>
2. <requirement 2>
    ...
n. <requirement n>

Kindly enter plan mode, and set before me a detailed and workable plan of action.
```

## Part 4: The Framework's Documentation

The framework is attended by a complete and carefully tended body of documentation, to be found under the `docs/` path. That you may orient yourself with all due expedition, you would do well to begin with `docs/README.md`.
