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
}

fn translate(language: Language, key: &str) -> Option<&'static str> {
    match language {
        Language::English => translate_english(key),
        Language::Chinese => translate_chinese(key),
        Language::French => translate_french(key),
        Language::Russian => translate_russian(key),
    }
}

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
