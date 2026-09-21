<div align="center">

<img src="./assets/logo.png" alt="InstructionX Logo" width="100%">


**Un framework d'application de bureau orienté plugins, basé sur PySide6 — intégration de LLM · prise en charge bidirectionnelle du protocole MCP · système de plugins remplaçables à chaud**

[![CI](https://github.com/KKPIP-Tech/InstructionX/actions/workflows/test.yml/badge.svg)](https://github.com/KKPIP-Tech/InstructionX/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10+-green.svg)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)](#)
[![Version](https://img.shields.io/badge/Alpha-1.1.1%20CE-red.svg)](#)
[![License](https://img.shields.io/badge/License-AGPL--3.0%2B%20%2B%20%C2%A77%20Terms-blue.svg)](LICENSE)

[中文版](README.md) | [English Version](README_EN.md) | Version française | [Русская версия](README_RU.md)

</div>

---

## Introduction

InstructionX est un **framework d'application de bureau orienté plugins** construit sur PySide6. Il réunit au sein d'une infrastructure unique le remplacement à chaud des plugins, l'intégration de grands modèles de langage (LLM) de plusieurs fournisseurs, la prise en charge bidirectionnelle du protocole MCP, la persistance des données et la gestion des tâches d'arrière-plan, permettant aux utilisateurs de composer librement des plugins d'outils autour de leurs propres flux de travail et de bâtir un ensemble d'outils tout-en-un personnalisé (Tools Cluster).

Le framework n'intègre aucune fonctionnalité métier : toutes les capacités sont ajoutées sous forme de plugins et distribuées via l'écosystème de dépôts de plugins GitHub. Les développeurs peuvent rapidement créer et publier leurs propres plugins grâce aux interfaces de plugins standardisées, au conteneur de services à injection de dépendances et à la bibliothèque de composants UIKit.

> Il s'agit d'un projet applicatif : il s'exécute directement depuis les sources et n'est pas distribué comme une bibliothèque.

## Captures d'écran

<!-- TODO : captures d'écran de l'application à ajouter. Placer les images dans assets/ (par ex. assets/screenshot-main.png) et remplacer ce placeholder. -->

> Les captures d'écran de l'application seront bientôt disponibles.

## Fonctionnalités principales

### Système de plugins

- **Gestion du cycle de vie** : chargement / déchargement / rechargement à chaud des plugins sans redémarrer l'application ; la désinstallation nettoie automatiquement les données associées, telles que l'identité du plugin et les surcharges linguistiques
- **Installation et mises à jour** : l'installateur GitHub intégré prend en charge les dépôts monoplugin (IXPlugin.json) et multiplugins (IXRepo.json), avec installation en arrière-plan et affichage de la progression ; installation locale depuis un zip (détection automatique des paquets monoplugin / multiplugins et des niveaux d'imbrication multiples dans l'archive, aperçu des relations mise à niveau / réinstallation / rétrogradation avant l'installation, la rétrogradation exigeant une confirmation supplémentaire), mise à niveau / rétrogradation via GitHub Release avec détection des relations de version ; les dépôts de l'organisation KKPIP-Tech sont automatiquement classés comme plugins officiels
- **Gouvernance des versions et des identités** : versions sémantiques des plugins (alpha / beta / pre-release / release) et identité UUID propre à chaque plugin ; le registre des plugins installés consigne la version / la provenance / la date d'installation et sert de base aux mises à niveau et aux vérifications de mise à jour ; les dépendances Python déclarées par les plugins sont installées automatiquement par le framework (uv en priorité, pip en repli)
- **Collaboration inter-plugins** : déclarer `service_api` enregistre automatiquement des API inter-plugins et les expose comme outils MCP ; les plugins peuvent également enregistrer des outils directement auprès du LLM via `llm_tools`
- **Organisation du panneau** : le panneau de compétences prend en charge des groupes personnalisés, le repli et un ordre mixte ; l'état de l'interface d'un plugin est mis en cache lors du changement de plugin et intégralement restauré au retour

### Intégration LLM

- **Prise en charge multi-fournisseurs** : cinq préréglages intégrés — MiniMax, SiliconFlow, Zhipu GLM, Ollama et OpenAI — plus un adaptateur de repli `openai-compatible` permettant d'intégrer tout point de terminaison compatible OpenAI sans écrire de code
- **Gestion multi-conversations** : création / bascule / persistance des conversations, avec troncature automatique du contexte fondée sur une estimation des tokens lorsque la fenêtre est dépassée (le prompt système et les messages récents sont conservés)
- **Automatisation des appels d'outils** : ToolCallExecutor gère automatiquement la boucle multi-tours des appels d'outils (`max_turns=5` par défaut) ; les plugins n'ont qu'à enregistrer leurs outils
- **Multimodal** : compréhension d'images (Vision), génération d'images, synthèse vocale TTS et plongements vectoriels (Embedding)
- **Statistiques d'utilisation** : consommation de tokens et estimation des coûts, par conversation et globalement, avec un panneau de visualisation intégré (AI → Utilisation)

### Prise en charge bidirectionnelle du protocole MCP

- **Serveur MCP** : expose automatiquement toutes les API des plugins comme outils MCP via les transports stdio et HTTP, avec authentification Bearer optionnelle ; les clients MCP tels que Claude Code peuvent invoquer directement les capacités des plugins
- **Client MCP** : se connecte à des serveurs MCP externes et enregistre leurs outils dans le ToolRegistry local, à disposition du LLM
- **Pont bidirectionnel** : MCPBridge synchronise automatiquement le registre d'API des plugins avec le serveur MCP

### Persistance des données

- **SQLite WAL + transactions explicites** : le backend par défaut, résistant aux interruptions inopinées ; un backend JSON est disponible via une variable d'environnement
- **Double espace de noms** : l'espace PRIVATE n'est visible qu'au sein du plugin ; l'espace PUBLIC permet le partage entre plugins
- **Publication / abonnement** : les plugins peuvent s'abonner aux modifications de données pour des interactions réactives ; un cache en mémoire réduit les E/S disque

### Système de tâches d'arrière-plan

- **Tâches asynchrones en pool de threads** : quatre threads de travail préservent la réactivité de l'interface
- **Tâches planifiées et de longue durée** : exécution récurrente à intervalle fixe ; les tâches de longue durée prennent en charge l'arrêt propre et le redémarrage automatique
- **Persistance des tâches** : les états des tâches survivent aux redémarrages et sont reconstruits automatiquement grâce au mécanisme de fabrique de tâches

### Internationalisation (i18n)

- **Fichiers de langue XML** : le framework comme les plugins suivent la convention « un fichier XML par langue », avec le chinois (par défaut), l'anglais, le russe et le français intégrés
- **Bascule en direct** : changez instantanément la langue de l'interface depuis le menu Édition → Langue, sans redémarrage
- **Chaîne de repli** : les entrées absentes de la langue courante se replient automatiquement sur la langue par défaut
- **Surcharge linguistique par plugin** : chaque plugin peut utiliser une langue d'interface différente de celle du framework

### Interface utilisateur

- **Bibliothèque de composants InstructionX_UIKit** : 58 composants + 13 dispositions + 52 animations, dont un moteur de graphiques natif (double viewport GL / logiciel), un graphe de nœuds blueprint, un éditeur de code façon VS Code et le rendu Mermaid ; trois modes de thème globaux (clair / sombre / auto) avec des design tokens qui réappliquent les styles en temps réel
- **Gestionnaire de polices** : installation / désinstallation / aperçu de polices au niveau de l'application (effectif dans le processus, sans écriture dans le répertoire des polices système), avec repli automatique sur les polices système en cas d'absence
- **Zone de notification** : le menu de la zone de notification présente en temps réel les plugins et les tâches d'arrière-plan en cours ; la fermeture de la fenêtre principale affiche une boîte de dialogue de confirmation permettant de quitter le programme ou de réduire l'application dans la zone de notification

## Démarrage rapide

### Option A : assistant TUI (recommandé pour les non-développeurs)

**Double-cliquez** sur `setup.bat` (Windows) ou `setup.command` (macOS).

L'assistant est un **script natif** (Windows : PowerShell 5.1 ; macOS : le bash intégré au système) et n'exige
**ni Python ni aucun paquet tiers** — il fonctionne donc également sur une machine totalement dépourvue de Python :

```powershell
# Windows (ligne de commande, options facultatives)
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1            # ouvre l'assistant en chinois/anglais
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -Check     # bilan de santé de l'environnement uniquement
```

```bash
# macOS (ligne de commande, options facultatives)
./setup.sh            # ouvre l'assistant en chinois/anglais
./setup.sh --check    # bilan de santé de l'environnement uniquement
```

L'assistant couvre **l'installation / la réparation de l'environnement, la mise à niveau du framework, la gestion de l'environnement, le bilan de santé en un clic, le nettoyage et la désinstallation, ainsi que le lancement de l'application**, avec des indications en langage clair, la préparation automatique de uv et de Python 3.14, des conseils précis en cas d'échec et un journal complet consigné dans `logs/tui_setup.log`. Les deux plateformes affichent une interface identique au caractère près. Voir [Assistant d'installation](docs/tui-setup.md) (en chinois, avec un résumé en anglais).

### Option B : installation manuelle (développeurs)

#### Prérequis

- Windows 10 / 11 (plateforme cible principale ; macOS fonctionne également, certaines intégrations système étant limitées)
- Python 3.14 ou version supérieure
- [uv](https://docs.astral.sh/uv/) (gestionnaire d'environnements virtuels et de dépendances Python)

#### Installer uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Installer les dépendances

Le premier lancement de `uv run main.py` crée automatiquement un environnement virtuel et synchronise les dépendances depuis `uv.lock` ; vous pouvez également les installer explicitement au préalable :

```bash
uv venv
uv pip install -r requirements.txt
```

> Remarque : n'utilisez **pas** `uv sync` pour réparer un environnement existant — la commande aligne strictement l'environnement sur `uv.lock` et **supprime** les paquets supplémentaires qui y ont été installés (par exemple les dépendances de plugins installées via le DependencyManager du framework, ou les dépendances de test). Pour une installation **neuve** (le répertoire `.venv` n'existe pas encore), vous pouvez utiliser `uv sync --no-dev --no-install-project` (c'est la stratégie adoptée par l'assistant TUI).

#### Exécution

```bash
uv run main.py
```

Les répertoires `data/` et `config/` sont créés automatiquement au premier lancement.

## Écosystème de plugins

InstructionX est un framework de plugins et ne livre aucun plugin métier intégré. Moyens d'obtenir des plugins :

- **Installation depuis GitHub** : menu « Édition → Installer un plugin depuis GitHub... » — saisissez l'URL d'un dépôt de plugin pour une installation en un clic
- **Installation manuelle** : copiez les plugins obtenus auprès de développeurs tiers dans le répertoire `custom_plugin/`

### Structure d'un plugin

Chaque plugin est un sous-répertoire de premier niveau sous `plugin/` (officiel) ou `custom_plugin/` (tiers) :

```
my_plugin/
├── entrance.py      # Requis : point d'entrée du plugin, définit la sous-classe IPlugin
├── information.py   # Requis : métadonnées du plugin (sous-classe IPluginInfo : version, icône, service_api, etc.)
├── service.py       # Requis : service du plugin / couche d'API publique
├── config/          # Requis : répertoire de configuration du plugin
├── text/            # Requis : répertoire des packs de langue (<code-langue>.xml, un fichier par langue)
└── assets/          # Optionnel : répertoire de ressources statiques
```

Lorsque `service_api` est fourni et que le nom de la classe de service se termine par `Service`, le framework enregistre automatiquement l'API inter-plugins et la synchronise comme outils MCP.

### Métadonnées d'un plugin

Un dépôt de plugin décrit chaque plugin via `IXPlugin.json`, dont les champs `name` et `description` acceptent des valeurs multilingues :

```json
{
    "id": "my-plugin",
    "name": {"zh": "我的插件", "en": "My Plugin"},
    "version": "release.1.0.0",
    "main": "entrance.py",
    "description": {"zh": "插件简介", "en": "Short description."},
    "author": "Your Name",
    "keywords": ["instructionx", "plugin"]
}
```

Les dépôts multiplugins exigent en outre un fichier d'index `IXRepo.json`.

### Services du framework accessibles aux plugins

Lors de la création d'une instance de plugin, le framework injecte automatiquement le conteneur `PluginServices`, donnant au plugin un accès direct à l'ensemble de l'infrastructure du framework :

| Service | Description |
|---------|-------------|
| `services.llm_facade` | Façade de services LLM pour plugins : conversations multiples, appels d'outils, multimodal, statistiques d'utilisation |
| `services.data_provider` | Couche de données DataProvider : espaces de noms PRIVATE / PUBLIC, publication / abonnement |
| `services.task_manager` | BackgroundTaskManager : tâches asynchrones / planifiées / de longue durée |
| `services.logger` | Interface de journalisation (ILogger) |
| `services.mcp_manager` | Gestion du serveur MCP : exposer les API des plugins comme outils MCP |
| `services.mcp_client` | Client MCP : connexion à des serveurs MCP externes |
| `services.font_manager` | Gestionnaire de polices : résolution de polices avec chaînes de repli |
| `services.localization` | Façade i18n (liée à l'UUID du plugin) |

### Exemple minimal de plugin

```python
from core import IPlugin
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class MyPlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        """Nom affiché dans le panneau de compétences"""
        return "Mon\nPlugin"

    @property
    def skill_description(self) -> str:
        return "Ceci est un plugin d'exemple"

    def _create_widget(self, parent=None, data_provider=None):
        """Crée l'interface du plugin"""
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Hello from MyPlugin!"))
        return widget
```

### Plugins d'exemple

Le répertoire `plugin/` fournit des exemples de référence pour le développement local : [framework-api-demo](plugin/framework-api-demo) (démonstrations des API cœur du framework : persistance des données, tâches d'arrière-plan, LLM, MCP, appels inter-plugins), [ui-demo](plugin/ui-demo) et [blueprint-opencv](plugin/blueprint-opencv). Voir l'[index des plugins](docs/plugins/index.md) pour plus de détails.

### Documentation de développement de plugins

- [Guide de développement de plugins (anglais)](Plugin-Development-Guide.md)
- [Guide de développement de plugins (chinois)](docs/core/plugin-system/plugin-development.md)
- [Détails de l'interface IPlugin](docs/core/plugin-system/iplugin.md)
- [Guide d'intégration LLM](docs/plugins/llm-integration-guide.md)

## Documentation

La documentation technique complète (en chinois) est disponible sous [docs/](docs/README.md) et couvre :

- **Architecture** : [Vue d'ensemble de l'architecture système](docs/architecture/overview.md), [Dépendances entre modules](docs/architecture/module-dependencies.md)
- **Modules centraux** : [Système de plugins](docs/core/plugin-system/overview.md), [DataProvider](docs/core/data-provider/overview.md), [Tâches d'arrière-plan](docs/core/background-task/overview.md), [LLM Provider](docs/core/llm-provider/overview.md), [Protocole MCP](docs/core/mcp/overview.md), [Sous-système i18n](docs/core/i18n/overview.md), [Gestionnaire de polices](docs/core/font-manager/overview.md)
- **Interface** : [Fenêtre principale](docs/ui/main-window.md), [Zone de notification et comportement de fermeture](docs/ui/system-tray.md), [Système de thèmes UIKit](docs/utils/uikit-theme.md)
- **Référence API** : [Index complet de l'API](docs/api/full-reference.md)

## Structure du projet

```
main.py            # Point d'entrée de l'application
core/              # Cœur du framework : interfaces / système de plugins / couche de données / tâches d'arrière-plan / LLM / MCP / polices / i18n
ui/                # Couche interface : fenêtre principale / panneau de compétences / zone de travail / zone de notification / boîtes de dialogue / InstructionX_UIKit
utils/             # Modules utilitaires (journalisation, marshaling inter-threads, etc.)
plugin/            # Plugins officiels / d'exemple (pour la vérification en développement local)
custom_plugin/     # Répertoire des plugins tiers
scripts/           # Scripts de smoke test / captures d'écran / démonstration
test/              # Tests pytest
docs/              # Documentation technique
config/            # Généré à l'exécution : fichiers de configuration
data/              # Généré à l'exécution : base de données, états des tâches, polices, etc.
logs/              # Généré à l'exécution : journaux de l'application
```

## Configuration et données

Les fichiers suivants sont générés à l'exécution ; ne modifiez pas leur structure manuellement :

| Fichier | Rôle |
|---------|------|
| `config/llm_providers.json` | Configuration des instances de fournisseurs LLM (clés API stockées de manière obfusquée) |
| `config/llm_models_cache.json` | Cache des listes de modèles |
| `config/mcp_config.json` | Configuration du serveur / client MCP |
| `config/plugin_order.json` | Ordre d'affichage des plugins non groupés |
| `config/plugin_groups.json` | Groupes de plugins personnalisés et ordre du panneau |
| `config/plugin_registry.json` | Registre des plugins installés (base des mises à niveau / rétrogradations) |
| `config/i18n.json` | Paramètres de langue du framework |
| `config/plugin_languages.json` | Surcharges linguistiques par plugin |
| `data/data.db` | Données des plugins (SQLite + WAL) |
| `data/tasks.json` | États des tâches d'arrière-plan |
| `data/llm_usage.json` | Enregistrements d'utilisation LLM |
| `data/conversations.json` | Persistance des conversations LLM |
| `data/fonts/` | Polices installées par le framework et leur registre |
| `logs/application.log` | Journaux de l'application |

### Variables d'environnement

| Variable | Rôle |
|----------|------|
| `INSTRUCTIONX_DATAPROVIDER_BACKEND` | Backend de la couche de données : `sqlite` (par défaut) / `json` |
| `INSTRUCTIONX_MCP_CONFIG` | Remplace le chemin du fichier de configuration MCP |
| `INSTRUCTIONX_GITHUB_TOKEN` | Jeton d'API GitHub : relève les limites de débit pour l'installation de plugins et les vérifications de mise à jour |
| `INSTRUCTIONX_LOG_DIR` | Remplace le répertoire de sortie des journaux |
| `INSTRUCTIONX_LOG_LEVEL` | Remplace le niveau de journalisation (`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`) |
| `DEVELOPMENT_MODE` | Bascule du mode développement |

## Tests et CI

```bash
pip install -e ".[test]"
python -m pytest test/ -q --tb=short -p no:cacheprovider
```

- La CI s'exécute sur GitHub Actions (`windows-latest` + Python 3.14), déclenchée par les pushes vers `dev` / `main` et par toutes les pull requests
- Le répertoire `scripts/` fournit des scripts de smoke test hors ligne pour les parcours critiques (`smoke_*.py`), des vérifications d'exhaustivité des fichiers de langue (`check_i18n_completeness.py`), des smoke tests du SDK MCP et d'autres scripts de vérification autonomes

## Contribution et support

- **Signalement de problèmes** : si vous rencontrez un problème ou avez une suggestion de fonctionnalité, ouvrez une [Issue](https://github.com/KKPIP-Tech/InstructionX/issues)
- **Contribution au code** : en soumettant une contribution à ce projet, vous acceptez le [Contrat de licence de contributeur individuel (ICLA) d'InstructionX](ICLA.md) — vous conservez le droit d'auteur sur vos contributions tout en accordant au producteur les licences requises par le modèle de double licence (édition communautaire AGPL + éditions commerciales propriétaires)
- **Conventions de branches** : `dev` est la branche de développement (sans code de test), le code de test pytest réside exclusivement sur la branche `test`, et `main` est la branche de publication
- **Langue de la documentation** : la documentation du projet et les commentaires du code sont principalement rédigés en chinois

## Pile technique

| Technologie | Rôle | Version |
|-------------|------|---------|
| Python | Langage de programmation | >= 3.14 |
| PySide6 | Framework Qt GUI | >= 6.10 |
| mcp | Protocole MCP (FastMCP) | >= 1.28.1, < 2 |
| requests / aiohttp | HTTP / HTTP asynchrone | >= 2.32 / >= 3.11 |
| orjson | Sérialisation JSON haute performance | >= 3.11.0, < 4 |
| matplotlib | Statistiques d'utilisation et rendu de formules LaTeX du MarkdownView d'UIKit | >= 3.10 |
| packaging | Vérification des versions de dépendances des plugins | >= 23.0 |
| qrcode[pil] | Composant QRCodeView d'UIKit | >= 7.4 |
| numpy | Moteur de graphiques UIKit (pipeline grandes données / sous-échantillonnage) | >= 2.0 |
| InstructionX_UIKit | Thème d'interface et bibliothèque de composants | Intégrée (alpha-v1.0.3) |

## Licence

InstructionX est un logiciel open source, publié sous licence **GNU AGPL v3** (ou toute version ultérieure), assortie de deux conditions additionnelles ajoutées conformément à la section 7 de l'AGPL :

- **Préservation des mentions d'attribution et des signes distinctifs** (§7b) : toute copie ou version interactive en réseau incluant l'interface utilisateur du framework (le répertoire `./ui/`) doit préserver le nom InstructionX, le logo, la mention de droit d'auteur et les descriptions identifiant le produit
- **Non-concession de marque** (§7e) : la présente licence n'accorde aucun droit d'utilisation du nom ou du logo InstructionX à titre de marque

**Licence commerciale (double licence)** — une licence commerciale écrite distincte est requise pour les scénarios suivants (contact : dakuang2002@126.com) :

1. Exploitation d'un SaaS / d'un service multi-locataires à code source fermé (un locataire correspond à un espace de travail)
2. Intégration d'InstructionX dans un produit commercial ou une plateforme commerciale tiers (sans respecter les obligations du copyleft)
3. Utilisation d'InstructionX comme service backend d'un SaaS ou d'une plateforme tiers (sans respecter les obligations du copyleft)
4. Utilisation en marque blanche : suppression, modification ou remplacement du logo, du nom, des mentions de droit d'auteur ou des descriptions identifiant le produit
5. Vente de lots groupés du framework avec des plugins (que le code source de l'ensemble groupé soit rendu disponible ou non)

Les plugins développés indépendamment, qui interagissent avec le framework uniquement via ses interfaces de plugins publiées, sont des œuvres indépendantes, dont la licence est laissée à la discrétion de leurs auteurs.

Voir [LICENSE](LICENSE) pour les conditions complètes.
