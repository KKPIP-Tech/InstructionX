use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum Language {
    #[serde(rename = "zh")]
    Chinese,
    #[default]
    #[serde(rename = "en")]
    English,
    #[serde(rename = "fr")]
    French,
    #[serde(rename = "ru")]
    Russian,
}

impl Language {
    pub const ALL: [Language; 4] = [
        Language::English,
        Language::Chinese,
        Language::French,
        Language::Russian,
    ];

    pub const fn code(self) -> &'static str {
        match self {
            Self::Chinese => "zh",
            Self::English => "en",
            Self::French => "fr",
            Self::Russian => "ru",
        }
    }

    pub fn from_code(code: &str) -> Self {
        match code.trim().to_ascii_lowercase().as_str() {
            "zh" => Self::Chinese,
            "fr" => Self::French,
            "ru" => Self::Russian,
            _ => Self::English,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct I18n {
    language: Language,
}

impl I18n {
    pub const fn new(language: Language) -> Self {
        Self { language }
    }

    pub fn t<'a>(&self, key: &'a str) -> &'a str {
        translate(self.language, key)
            .or_else(|| translate(Language::English, key))
            .unwrap_or(key)
    }

    pub fn format(&self, key: &str, arguments: &[(String, String)]) -> String {
        let mut text = self.t(key).to_string();
        for (name, value) in arguments {
            text = text.replace(&format!("{{{name}}}"), value);
        }
        text
    }

    pub fn format_values(&self, key: &str, arguments: &[(&str, &str)]) -> String {
        let arguments: Vec<(String, String)> = arguments
            .iter()
            .map(|(name, value)| (name.to_string(), value.to_string()))
            .collect();
        self.format(key, &arguments)
    }
}

fn translate(language: Language, key: &str) -> Option<&'static str> {
    translate_feedback(language, key).or_else(|| match language {
        Language::English => translate_english(key),
        Language::Chinese => translate_chinese(key),
        Language::French => translate_french(key),
        Language::Russian => translate_russian(key),
    })
}

fn translate_feedback(language: Language, key: &str) -> Option<&'static str> {
    if key.starts_with("progress.") {
        return lookup_translation(language, key, PROGRESS_TRANSLATIONS);
    }
    if key.starts_with("result.") {
        return lookup_translation(language, key, RESULT_TRANSLATIONS);
    }
    lookup_translation(language, key, ACTIVITY_TRANSLATIONS)
        .or_else(|| lookup_translation(language, key, CONTENT_TRANSLATIONS))
}

fn lookup_translation(
    language: Language,
    key: &str,
    entries: &[(&'static str, [&'static str; 4])],
) -> Option<&'static str> {
    let (_, translations) = entries.iter().find(|(entry, _)| *entry == key)?;
    Some(translations[language_index(language)])
}

fn language_index(language: Language) -> usize {
    match language {
        Language::English => 0,
        Language::Chinese => 1,
        Language::French => 2,
        Language::Russian => 3,
    }
}

const ACTIVITY_TRANSLATIONS: &[(&str, [&str; 4])] = &[
    (
        "action.install_git",
        ["Install Git", "安装 Git", "Installer Git", "Установить Git"],
    ),
    (
        "action.install_uv",
        ["Install uv", "安装 uv", "Installer uv", "Установить uv"],
    ),
    (
        "action.clean_temp",
        [
            "Clean temporary files",
            "清理临时文件",
            "Nettoyer les fichiers temporaires",
            "Очистить временные файлы",
        ],
    ),
    (
        "action.uninstall",
        [
            "Uninstall environment",
            "卸载运行环境",
            "Désinstaller l’environnement",
            "Удалить окружение",
        ],
    ),
    ("status.ready", ["Ready", "已就绪", "Prêt", "Готово"]),
    (
        "status.running",
        [
            "Running: {operation}",
            "正在运行：{operation}",
            "En cours : {operation}",
            "Выполняется: {operation}",
        ],
    ),
    (
        "status.failed",
        [
            "Operation failed: {error}",
            "操作失败：{error}",
            "Échec de l’opération : {error}",
            "Операция не выполнена: {error}",
        ],
    ),
    (
        "status.cancelled",
        [
            "Operation cancelled before execution",
            "操作已在执行前取消",
            "Opération annulée avant exécution",
            "Операция отменена до выполнения",
        ],
    ),
    (
        "status.select_language",
        [
            "Select the interface language",
            "请选择界面语言",
            "Sélectionnez la langue",
            "Выберите язык интерфейса",
        ],
    ),
    (
        "activity.title",
        ["Activity", "活动", "Activité", "Действие"],
    ),
    (
        "activity.running",
        ["Running", "运行中", "En cours", "Выполняется"],
    ),
    (
        "activity.status",
        [
            "Status: {value}",
            "状态：{value}",
            "État : {value}",
            "Состояние: {value}",
        ],
    ),
    (
        "activity.progress",
        [
            "Progress: {value}",
            "进度：{value}",
            "Progression : {value}",
            "Прогресс: {value}",
        ],
    ),
    (
        "activity.log",
        [
            "Log: logs/tui_setup.log",
            "日志：logs/tui_setup.log",
            "Journal : logs/tui_setup.log",
            "Журнал: logs/tui_setup.log",
        ],
    ),
    (
        "activity.confirm",
        [
            "Confirm {operation}: press Enter again; Esc cancels",
            "确认{operation}：再次按 Enter 执行；Esc 取消",
            "Confirmer {operation} : Entrée pour exécuter ; Échap annule",
            "Подтвердить {operation}: Enter для запуска; Esc отменяет",
        ],
    ),
    (
        "activity.quit_blocked",
        [
            "An operation is still running; wait for its result before quitting",
            "操作仍在运行，请等待结果后再退出",
            "Une opération est en cours ; attendez son résultat avant de quitter",
            "Операция еще выполняется; дождитесь результата перед выходом",
        ],
    ),
    ("focus.label", ["Focus", "焦点", "Focus", "Фокус"]),
    ("focus.menu", ["Menu", "菜单", "Menu", "Меню"]),
    (
        "focus.content",
        ["Content", "内容", "Contenu", "Содержимое"],
    ),
    (
        "log.unavailable",
        [
            "Could not open logs/tui_setup.log; continuing without file logging",
            "无法打开 logs/tui_setup.log；将继续运行但不写入文件日志",
            "Impossible d’ouvrir logs/tui_setup.log ; exécution sans journal",
            "Не удалось открыть logs/tui_setup.log; продолжение без файлового журнала",
        ],
    ),
    (
        "log.write_failed",
        [
            "Could not write Setup log: {error}",
            "无法写入 Setup 日志：{error}",
            "Impossible d’écrire le journal : {error}",
            "Не удалось записать журнал: {error}",
        ],
    ),
    (
        "output.command",
        ["{value}", "{value}", "{value}", "{value}"],
    ),
];

const CONTENT_TRANSLATIONS: &[(&str, [&str; 4])] = &[
    (
        "install.tools",
        [
            "Tools: git={git} uv={uv} (g install Git, v install uv)",
            "工具：Git={git}，uv={uv}（g 安装 Git，v 安装 uv）",
            "Outils : Git={git}, uv={uv} (g installe Git, v installe uv)",
            "Инструменты: Git={git}, uv={uv} (g устанавливает Git, v — uv)",
        ],
    ),
    (
        "release.empty",
        [
            "No Releases loaded. Install loads the latest automatically; Check loads the timeline.\n",
            "尚未加载 Release。安装会自动加载最新版；检查操作会加载时间线。\n",
            "Aucune Release chargée. L’installation charge la dernière ; Vérifier charge la chronologie.\n",
            "Releases не загружены. Установка загрузит последнюю; Проверка загрузит временную шкалу.\n",
        ],
    ),
    (
        "release.latest",
        ["latest", "最新", "dernière", "последняя"],
    ),
    (
        "release.current",
        ["current", "当前", "actuelle", "текущая"],
    ),
    (
        "release.prerelease",
        ["Pre-release", "预发布", "Préversion", "Предварительная"],
    ),
    (
        "release.unrecognized",
        ["unrecognized", "无法识别", "non reconnue", "не распознана"],
    ),
    (
        "environment.empty",
        [
            "No package information. Select Query package list to load it.\n",
            "没有包信息。请选择“查询包列表”加载。\n",
            "Aucune information. Sélectionnez Afficher la liste des paquets.\n",
            "Нет данных о пакетах. Выберите показ списка пакетов.\n",
        ],
    ),
    (
        "environment.select_hint",
        [
            "Space: select package",
            "Space：勾选包",
            "Espace : sélectionner le paquet",
            "Пробел: выбрать пакет",
        ],
    ),
    (
        "environment.protected",
        ["protected", "受保护", "protégé", "защищен"],
    ),
    (
        "common.unknown",
        ["unknown", "未知", "inconnu", "неизвестно"],
    ),
    ("common.failed", ["FAILED", "失败", "ÉCHEC", "ОШИБКА"]),
    (
        "detail.backup",
        [
            "Backup: {path}",
            "备份：{path}",
            "Sauvegarde : {path}",
            "Резервная копия: {path}",
        ],
    ),
    (
        "detail.shortcut",
        [
            "Shortcut: {path}",
            "快捷方式：{path}",
            "Raccourci : {path}",
            "Ярлык: {path}",
        ],
    ),
    (
        "plugin.empty",
        [
            "No plugins found. Select Refresh plugin list to reload.\n",
            "未发现插件。请选择“刷新插件列表”重新加载。\n",
            "Aucun plugin. Sélectionnez Actualiser la liste des plugins.\n",
            "Плагины не найдены. Выберите обновление списка плагинов.\n",
        ],
    ),
    (
        "plugin.official",
        ["official", "官方", "officiel", "официальный"],
    ),
    (
        "plugin.thirdparty",
        ["thirdparty", "第三方", "tiers", "сторонний"],
    ),
    (
        "plugin.unchecked",
        ["unchecked", "未检查", "non vérifié", "не проверен"],
    ),
    (
        "plugin.checking",
        ["checking", "检查中", "vérification", "проверка"],
    ),
    (
        "plugin.latest",
        ["latest", "已是最新", "à jour", "актуальная"],
    ),
    (
        "plugin.update_available",
        [
            "update: {version}",
            "可更新：{version}",
            "mise à jour : {version}",
            "доступно обновление: {version}",
        ],
    ),
    (
        "plugin.failed",
        [
            "error: {error}",
            "错误：{error}",
            "erreur : {error}",
            "ошибка: {error}",
        ],
    ),
    (
        "plugin.dependency",
        [
            "Dependency {plugin}: {status} {detail}",
            "依赖 {plugin}：{status} {detail}",
            "Dépendance {plugin} : {status} {detail}",
            "Зависимость {plugin}: {status} {detail}",
        ],
    ),
    (
        "overview.os",
        [
            "OS: {name} {version} ({architecture})",
            "操作系统：{name} {version}（{architecture}）",
            "OS : {name} {version} ({architecture})",
            "ОС: {name} {version} ({architecture})",
        ],
    ),
    (
        "overview.kernel_host",
        [
            "Kernel: {kernel} | Host: {host}",
            "内核：{kernel} | 主机：{host}",
            "Noyau : {kernel} | Hôte : {host}",
            "Ядро: {kernel} | Хост: {host}",
        ],
    ),
    (
        "overview.cpu",
        [
            "CPU: {model} | Cores: {physical} physical / {logical} logical",
            "CPU：{model} | 核心：{physical} 物理 / {logical} 逻辑",
            "CPU : {model} | Cœurs : {physical} physiques / {logical} logiques",
            "CPU: {model} | Ядра: {physical} физических / {logical} логических",
        ],
    ),
    (
        "overview.memory",
        [
            "Memory: {total} total / {available} available",
            "内存：总计 {total} / 可用 {available}",
            "Mémoire : {total} total / {available} disponible",
            "Память: всего {total} / доступно {available}",
        ],
    ),
    (
        "overview.ram",
        [
            "RAM {slot}: {capacity} {manufacturer} {part} {speed} MT/s",
            "内存 {slot}：{capacity} {manufacturer} {part} {speed} MT/s",
            "RAM {slot} : {capacity} {manufacturer} {part} {speed} MT/s",
            "ОЗУ {slot}: {capacity} {manufacturer} {part} {speed} MT/s",
        ],
    ),
    (
        "overview.disk",
        [
            "Disk: {model} ({size})",
            "磁盘：{model}（{size}）",
            "Disque : {model} ({size})",
            "Диск: {model} ({size})",
        ],
    ),
    (
        "overview.volume",
        [
            "Volume {mount} [{filesystem}]: {total} total / {free} free",
            "卷 {mount} [{filesystem}]：总计 {total} / 可用 {free}",
            "Volume {mount} [{filesystem}] : {total} total / {free} libre",
            "Том {mount} [{filesystem}]: всего {total} / свободно {free}",
        ],
    ),
    (
        "overview.monitor",
        [
            "Monitor {name}: {details}",
            "显示器 {name}：{details}",
            "Écran {name} : {details}",
            "Монитор {name}: {details}",
        ],
    ),
    (
        "overview.network",
        [
            "Network {name} [{mac}]: {addresses}",
            "网卡 {name} [{mac}]：{addresses}",
            "Réseau {name} [{mac}] : {addresses}",
            "Сеть {name} [{mac}]: {addresses}",
        ],
    ),
    (
        "overview.warning",
        [
            "Warning: {warning}",
            "警告：{warning}",
            "Avertissement : {warning}",
            "Предупреждение: {warning}",
        ],
    ),
    (
        "overview.tui_path",
        [
            "TUI path: {path}",
            "TUI 路径：{path}",
            "Chemin TUI : {path}",
            "Путь TUI: {path}",
        ],
    ),
    (
        "overview.framework",
        [
            "Framework: {status} | version: {version}",
            "框架：{status} | 版本：{version}",
            "Framework : {status} | version : {version}",
            "Фреймворк: {status} | версия: {version}",
        ],
    ),
    (
        "overview.tools",
        [
            "Git: {git} | uv: {uv} | .venv: {venv}",
            "Git：{git} | uv：{uv} | .venv：{venv}",
            "Git : {git} | uv : {uv} | .venv : {venv}",
            "Git: {git} | uv: {uv} | .venv: {venv}",
        ],
    ),
    (
        "overview.public_ip",
        [
            "Public IP: {address} (press p to refresh)",
            "公网 IP：{address}（按 p 刷新）",
            "IP publique : {address} (p pour actualiser)",
            "Публичный IP: {address} (p для обновления)",
        ],
    ),
    (
        "overview.installed",
        ["installed", "已安装", "installé", "установлен"],
    ),
    (
        "overview.not_installed",
        ["not installed", "未安装", "non installé", "не установлен"],
    ),
    (
        "overview.not_fetched",
        ["not fetched", "尚未获取", "non récupérée", "не получен"],
    ),
    (
        "overview.unavailable",
        [
            "Unavailable: {error}",
            "不可用：{error}",
            "Indisponible : {error}",
            "Недоступно: {error}",
        ],
    ),
    (
        "terminal.too_small",
        [
            "Terminal too small: {width}x{height}",
            "终端窗口过小：{width}x{height}",
            "Terminal trop petit : {width}x{height}",
            "Терминал слишком мал: {width}x{height}",
        ],
    ),
];

const PROGRESS_TRANSLATIONS: &[(&str, [&str; 4])] = &[
    (
        "progress.check_uv",
        [
            "Check the uv package manager",
            "检查 uv 包管理器",
            "Vérifier le gestionnaire uv",
            "Проверить менеджер uv",
        ],
    ),
    (
        "progress.using_uv",
        [
            "Using uv: {path}",
            "使用 uv：{path}",
            "Utilisation de uv : {path}",
            "Используется uv: {path}",
        ],
    ),
    (
        "progress.uv_installed",
        [
            "uv installed: {path}",
            "uv 已安装：{path}",
            "uv installé : {path}",
            "uv установлен: {path}",
        ],
    ),
    (
        "progress.resolve_release",
        [
            "Resolve the requested Release",
            "解析请求的 Release",
            "Résoudre la Release demandée",
            "Определить запрошенный Release",
        ],
    ),
    (
        "progress.local_archive",
        [
            "Using local archive: {path}",
            "使用本地归档：{path}",
            "Utiliser l’archive locale : {path}",
            "Использовать локальный архив: {path}",
        ],
    ),
    (
        "progress.fetch_release_timeline",
        [
            "Fetch the complete GitHub Release timeline",
            "获取完整 GitHub Release 时间线",
            "Récupérer la chronologie GitHub Release",
            "Получить полную временную шкалу GitHub Release",
        ],
    ),
    (
        "progress.download_release",
        [
            "Download Release {tag}",
            "下载 Release {tag}",
            "Télécharger Release {tag}",
            "Скачать Release {tag}",
        ],
    ),
    (
        "progress.download_complete",
        [
            "Download complete; SHA-256: {checksum}",
            "下载完成；SHA-256：{checksum}",
            "Téléchargement terminé ; SHA-256 : {checksum}",
            "Загрузка завершена; SHA-256: {checksum}",
        ],
    ),
    (
        "progress.copy_archive",
        [
            "Validate, extract and copy the Release archive",
            "校验、解压并复制 Release 归档",
            "Valider, extraire et copier l’archive Release",
            "Проверить, распаковать и скопировать архив Release",
        ],
    ),
    (
        "progress.install_framework_dependencies",
        [
            "Install framework dependencies",
            "安装框架依赖",
            "Installer les dépendances du framework",
            "Установить зависимости фреймворка",
        ],
    ),
    (
        "progress.verify_python",
        [
            "Verify required Python components",
            "验证必需的 Python 组件",
            "Vérifier les composants Python requis",
            "Проверить необходимые компоненты Python",
        ],
    ),
    (
        "progress.archive_completed",
        [
            "Installation and verification completed",
            "安装与验证已完成",
            "Installation et vérification terminées",
            "Установка и проверка завершены",
        ],
    ),
    (
        "progress.read_packages",
        [
            "Read installed and outdated Python packages",
            "读取已安装及可更新的 Python 包",
            "Lire les paquets Python installés et obsolètes",
            "Прочитать установленные и устаревшие пакеты Python",
        ],
    ),
    (
        "progress.update_package",
        [
            "Update {package}",
            "更新 {package}",
            "Mettre à jour {package}",
            "Обновить {package}",
        ],
    ),
    (
        "progress.remove_package",
        [
            "Remove {package}",
            "移除 {package}",
            "Supprimer {package}",
            "Удалить {package}",
        ],
    ),
    (
        "progress.refresh_packages",
        [
            "Refresh the package list",
            "刷新包列表",
            "Actualiser la liste des paquets",
            "Обновить список пакетов",
        ],
    ),
    (
        "progress.rebuild_environment",
        [
            "Delete .venv and reinstall locked framework dependencies",
            "删除 .venv 并按锁文件重装框架依赖",
            "Supprimer .venv et réinstaller les dépendances verrouillées",
            "Удалить .venv и переустановить зависимости из lock-файла",
        ],
    ),
    (
        "progress.install_plugin_dependencies",
        [
            "Install dependencies for every plugin",
            "逐个安装插件依赖",
            "Installer les dépendances de chaque plugin",
            "Установить зависимости каждого плагина",
        ],
    ),
    (
        "progress.refresh_plugins",
        [
            "Read plugin descriptors and registry",
            "读取插件描述与注册表",
            "Lire les descripteurs et le registre des plugins",
            "Прочитать дескрипторы и реестр плагинов",
        ],
    ),
    (
        "progress.check_plugin_updates",
        [
            "Check each plugin's published versions",
            "检查各插件已发布版本",
            "Vérifier les versions publiées des plugins",
            "Проверить опубликованные версии плагинов",
        ],
    ),
    (
        "progress.create_shortcut",
        [
            "Create and verify the desktop shortcut",
            "创建并验证桌面快捷方式",
            "Créer et vérifier le raccourci",
            "Создать и проверить ярлык",
        ],
    ),
    (
        "progress.install_git",
        [
            "Install Git with the platform package manager",
            "使用平台包管理器安装 Git",
            "Installer Git avec le gestionnaire de paquets",
            "Установить Git через системный менеджер пакетов",
        ],
    ),
    (
        "progress.install_uv",
        [
            "Download and verify the uv executable",
            "下载并验证 uv 可执行文件",
            "Télécharger et vérifier l’exécutable uv",
            "Скачать и проверить исполняемый файл uv",
        ],
    ),
    (
        "progress.clean_temp",
        [
            "Clean temporary files",
            "清理临时文件",
            "Nettoyer les fichiers temporaires",
            "Очистить временные файлы",
        ],
    ),
    (
        "progress.uninstall_data",
        [
            "Remove the virtual environment and runtime data",
            "删除虚拟环境与运行数据",
            "Supprimer l’environnement virtuel et les données",
            "Удалить виртуальное окружение и данные",
        ],
    ),
    (
        "progress.uninstall_shortcut",
        [
            "Remove the desktop shortcut",
            "删除桌面快捷方式",
            "Supprimer le raccourci",
            "Удалить ярлык",
        ],
    ),
];

const RESULT_TRANSLATIONS: &[(&str, [&str; 4])] = &[
    (
        "result.install",
        [
            "Installation completed; {count} files copied",
            "安装完成；已复制 {count} 个文件",
            "Installation terminée ; {count} fichiers copiés",
            "Установка завершена; скопировано файлов: {count}",
        ],
    ),
    (
        "result.repair",
        [
            "Repair completed; {count} files copied",
            "修复完成；已复制 {count} 个文件",
            "Réparation terminée ; {count} fichiers copiés",
            "Восстановление завершено; скопировано файлов: {count}",
        ],
    ),
    (
        "result.upgrade",
        [
            "Upgrade completed; {count} files copied",
            "升级完成；已复制 {count} 个文件",
            "Mise à jour terminée ; {count} fichiers copiés",
            "Обновление завершено; скопировано файлов: {count}",
        ],
    ),
    (
        "result.releases",
        [
            "Loaded {count} Releases",
            "已加载 {count} 个 Release",
            "{count} Releases chargées",
            "Загружено Releases: {count}",
        ],
    ),
    (
        "result.packages",
        [
            "Package list updated; {count} packages",
            "包列表已更新；共 {count} 个包",
            "Liste actualisée ; {count} paquets",
            "Список обновлен; пакетов: {count}",
        ],
    ),
    (
        "result.updated_packages",
        [
            "Updated {count} packages",
            "已更新 {count} 个包",
            "{count} paquets mis à jour",
            "Обновлено пакетов: {count}",
        ],
    ),
    (
        "result.removed_packages",
        [
            "Removed {count} packages",
            "已移除 {count} 个包",
            "{count} paquets supprimés",
            "Удалено пакетов: {count}",
        ],
    ),
    (
        "result.plugins",
        [
            "Plugin list refreshed; {count} plugins",
            "插件列表已刷新；共 {count} 个插件",
            "Liste actualisée ; {count} plugins",
            "Список плагинов обновлен; плагинов: {count}",
        ],
    ),
    (
        "result.plugin_updates",
        [
            "Plugin updates checked; {count} updates available",
            "插件更新检查完成；{count} 个可用更新",
            "Plugins vérifiés ; {count} mises à jour disponibles",
            "Плагины проверены; доступно обновлений: {count}",
        ],
    ),
    (
        "result.dependencies",
        [
            "Plugin dependency installation finished; {count} failed",
            "插件依赖安装结束；{count} 项失败",
            "Installation des dépendances terminée ; {count} échecs",
            "Установка зависимостей завершена; ошибок: {count}",
        ],
    ),
    (
        "result.shortcut",
        [
            "Desktop shortcut created",
            "桌面快捷方式已创建",
            "Raccourci créé",
            "Ярлык создан",
        ],
    ),
    (
        "result.git",
        [
            "Git installed successfully",
            "Git 安装成功",
            "Git installé avec succès",
            "Git успешно установлен",
        ],
    ),
    (
        "result.uv",
        [
            "uv installed successfully",
            "uv 安装成功",
            "uv installé avec succès",
            "uv успешно установлен",
        ],
    ),
    (
        "result.clean_temp",
        [
            "Temporary files cleaned",
            "临时文件已清理",
            "Fichiers temporaires nettoyés",
            "Временные файлы удалены",
        ],
    ),
    (
        "result.uninstall",
        [
            "Environment and shortcuts removed; program files and plugins were kept",
            "环境与快捷方式已删除；程序文件和插件已保留",
            "Environnement et raccourcis supprimés ; programmes et plugins conservés",
            "Окружение и ярлыки удалены; файлы программы и плагины сохранены",
        ],
    ),
];

fn translate_english(key: &str) -> Option<&'static str> {
    match key {
        "menu.overview" => Some("Overview"),
        "menu.install" => Some("Install & Repair"),
        "menu.environment" => Some("Environment"),
        "menu.upgrade" => Some("Upgrade Management"),
        "menu.plugins" => Some("Plugins"),
        "menu.misc" => Some("Miscellaneous"),
        "language.title" => Some("Select interface language"),
        "language.hint" => Some("↑↓ Move   Enter Confirm   q Quit"),
        "nav.hint" => Some("↑↓ Select  → Enter  ← Back  PgUp/PgDn Page  q Quit"),
        "overview.placeholder" => Some("System information is being prepared..."),
        "action.install" => Some("Install InstructionX"),
        "action.repair" => Some("Repair InstructionX"),
        "action.check_releases" => Some("Check GitHub Releases"),
        "action.check_updates" => Some("Check for updates"),
        "action.upgrade_selected" => Some("Upgrade to selected version"),
        "action.query_packages" => Some("Query package list"),
        "action.update_selected" => Some("Update selected packages"),
        "action.remove_selected" => Some("Remove selected packages"),
        "action.rebuild_environment" => Some("Rebuild environment"),
        "action.refresh_plugins" => Some("Refresh plugin list"),
        "action.check_plugin_updates" => Some("Check plugin updates"),
        "action.install_plugin_dependencies" => Some("Install plugin dependencies"),
        "action.create_shortcut" => Some("Create desktop shortcut"),
        "action.language" => Some("TUI language"),
        _ => None,
    }
}

fn translate_chinese(key: &str) -> Option<&'static str> {
    match key {
        "menu.overview" => Some("总览"),
        "menu.install" => Some("安装与修复"),
        "menu.environment" => Some("环境配置 | 环境修复"),
        "menu.upgrade" => Some("升级管理"),
        "menu.plugins" => Some("插件列表"),
        "menu.misc" => Some("杂项"),
        "language.title" => Some("选择界面语言"),
        "language.hint" => Some("↑↓ 移动   Enter 确认   q 退出"),
        "nav.hint" => Some("↑↓ 选择  → 进入  ← 返回  PgUp/PgDn 翻页  q 退出"),
        "overview.placeholder" => Some("正在准备系统信息..."),
        "action.install" => Some("安装 InstructionX"),
        "action.repair" => Some("修复 InstructionX"),
        "action.check_releases" => Some("检查 GitHub Release"),
        "action.check_updates" => Some("检查更新"),
        "action.upgrade_selected" => Some("升级到所选版本"),
        "action.query_packages" => Some("查询包列表"),
        "action.update_selected" => Some("更新所选包"),
        "action.remove_selected" => Some("移除所选包"),
        "action.rebuild_environment" => Some("重建环境"),
        "action.refresh_plugins" => Some("刷新插件列表"),
        "action.check_plugin_updates" => Some("检查插件更新"),
        "action.install_plugin_dependencies" => Some("安装插件依赖"),
        "action.create_shortcut" => Some("创建桌面快捷方式"),
        "action.language" => Some("TUI 语言"),
        _ => None,
    }
}

fn translate_french(key: &str) -> Option<&'static str> {
    match key {
        "menu.overview" => Some("Vue d’ensemble"),
        "menu.install" => Some("Installation et réparation"),
        "menu.environment" => Some("Environnement"),
        "menu.upgrade" => Some("Gestion des mises à jour"),
        "menu.plugins" => Some("Plugins"),
        "menu.misc" => Some("Divers"),
        "language.title" => Some("Choisir la langue de l’interface"),
        "language.hint" => Some("↑↓ Naviguer   Entrée Valider   q Quitter"),
        "nav.hint" => Some("↑↓ Choisir  → Entrer  ← Retour  PgUp/PgDn Page  q Quitter"),
        "overview.placeholder" => Some("Préparation des informations système..."),
        "action.install" => Some("Installer InstructionX"),
        "action.repair" => Some("Réparer InstructionX"),
        "action.check_releases" => Some("Vérifier les Releases GitHub"),
        "action.check_updates" => Some("Rechercher des mises à jour"),
        "action.upgrade_selected" => Some("Mettre à jour vers la version sélectionnée"),
        "action.query_packages" => Some("Afficher la liste des paquets"),
        "action.update_selected" => Some("Mettre à jour les paquets sélectionnés"),
        "action.remove_selected" => Some("Supprimer les paquets sélectionnés"),
        "action.rebuild_environment" => Some("Reconstruire l’environnement"),
        "action.refresh_plugins" => Some("Actualiser la liste des plugins"),
        "action.check_plugin_updates" => Some("Vérifier les mises à jour des plugins"),
        "action.install_plugin_dependencies" => Some("Installer les dépendances des plugins"),
        "action.create_shortcut" => Some("Créer un raccourci sur le bureau"),
        "action.language" => Some("Langue du TUI"),
        _ => None,
    }
}

fn translate_russian(key: &str) -> Option<&'static str> {
    match key {
        "menu.overview" => Some("Обзор"),
        "menu.install" => Some("Установка и восстановление"),
        "menu.environment" => Some("Окружение"),
        "menu.upgrade" => Some("Обновления"),
        "menu.plugins" => Some("Плагины"),
        "menu.misc" => Some("Разное"),
        "language.title" => Some("Выберите язык интерфейса"),
        "language.hint" => Some("↑↓ Выбор   Enter Подтвердить   q Выход"),
        "nav.hint" => Some("↑↓ Выбор  → Войти  ← Назад  PgUp/PgDn Стр.  q Выход"),
        "overview.placeholder" => Some("Подготовка системной информации..."),
        "action.install" => Some("Установить InstructionX"),
        "action.repair" => Some("Восстановить InstructionX"),
        "action.check_releases" => Some("Проверить GitHub Release"),
        "action.check_updates" => Some("Проверить обновления"),
        "action.upgrade_selected" => Some("Обновить до выбранной версии"),
        "action.query_packages" => Some("Показать список пакетов"),
        "action.update_selected" => Some("Обновить выбранные пакеты"),
        "action.remove_selected" => Some("Удалить выбранные пакеты"),
        "action.rebuild_environment" => Some("Пересоздать окружение"),
        "action.refresh_plugins" => Some("Обновить список плагинов"),
        "action.check_plugin_updates" => Some("Проверить обновления плагинов"),
        "action.install_plugin_dependencies" => Some("Установить зависимости плагинов"),
        "action.create_shortcut" => Some("Создать ярлык на рабочем столе"),
        "action.language" => Some("Язык TUI"),
        _ => None,
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Preferences {
    pub language: Language,
    pub needs_language_selection: bool,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            language: Language::English,
            needs_language_selection: true,
        }
    }
}

impl Preferences {
    pub fn load(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        if !path.exists() {
            let legacy = path.with_file_name("lang");
            if legacy.is_file() {
                return Ok(Self {
                    language: Language::from_code(&fs::read_to_string(legacy)?),
                    needs_language_selection: false,
                });
            }
            return Ok(Self::default());
        }
        let content = fs::read_to_string(path)?;
        let preferences = toml::from_str(&content)?;
        Ok(preferences)
    }

    pub fn save(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let content = toml::to_string_pretty(self)?;
        let temporary = path.with_extension("toml.tmp");
        fs::write(&temporary, content)?;
        fs::rename(temporary, path)?;
        Ok(())
    }
}
