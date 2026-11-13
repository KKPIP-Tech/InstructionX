use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub struct ShortcutManager {
    root: PathBuf,
    uv_path: PathBuf,
}

impl ShortcutManager {
    pub fn new(root: PathBuf, uv_path: PathBuf) -> Self {
        Self { root, uv_path }
    }

    pub fn shortcut_path(&self) -> PathBuf {
        let desktop = desktop_directory();
        if cfg!(windows) {
            desktop.join("InstructionX.lnk")
        } else if cfg!(target_os = "macos") {
            desktop.join("InstructionX.app")
        } else {
            desktop.join("InstructionX.desktop")
        }
    }

    pub fn launcher_text(&self) -> String {
        let uv = self.uv_path.to_string_lossy().replace('\\', "/");
        let root = self.root.to_string_lossy().replace('\\', "/");
        if cfg!(windows) {
            format!(
                "Set shell = CreateObject(\"WScript.Shell\")\n\
                 shell.CurrentDirectory = \"{root}\"\n\
                 shell.Run \"\"{uv}\"\" run --frozen pythonw main.py\", 0, False\n"
            )
        } else if cfg!(target_os = "macos") {
            format!("#!/bin/bash\ncd \"{root}\"\n\"{uv}\" run --frozen python main.py\n")
        } else {
            format!(
                "[Desktop Entry]\nType=Application\nName=InstructionX\n\
                 Exec=\"{uv}\" run --frozen python main.py\nPath={root}\n\
                 Icon={root}/ui/logo.png\nTerminal=false\nCategories=Development;\n"
            )
        }
    }

    pub fn create(&self, dry_run: bool) -> Result<PathBuf, Box<dyn Error>> {
        let shortcut = self.shortcut_path();
        if dry_run {
            return Ok(shortcut);
        }
        let launchers = self.root.join(".tui/launchers");
        fs::create_dir_all(&launchers)?;
        if cfg!(windows) {
            self.create_windows(&launchers, &shortcut)?;
        } else if cfg!(target_os = "macos") {
            self.create_macos(&shortcut)?;
        } else {
            self.create_linux(&shortcut)?;
        }
        Ok(shortcut)
    }

    #[cfg(windows)]
    fn create_windows(&self, launchers: &Path, shortcut: &Path) -> Result<(), Box<dyn Error>> {
        let launcher = launchers.join("InstructionX.vbs");
        fs::write(&launcher, self.launcher_text())?;
        let script = launchers.join("create-shortcut.vbs");
        let arguments = format!(
            "Set shell = CreateObject(\"WScript.Shell\")\n\
             Set shortcut = shell.CreateShortcut(\"{}\")\n\
             shortcut.TargetPath = \"wscript.exe\"\n\
             shortcut.Arguments = \"{}\" \n\
             shortcut.WorkingDirectory = \"{}\"\n\
             shortcut.IconLocation = \"{}\"\n\
             shortcut.Save\n",
            shortcut.display(),
            launcher.display(),
            self.root.display(),
            self.root.join("ui/logo.ico").display()
        );
        fs::write(&script, arguments)?;
        let status = Command::new("wscript.exe").arg(&script).status()?;
        if !status.success() {
            return Err("Failed to create Windows shortcut".into());
        }
        Ok(())
    }

    #[cfg(target_os = "macos")]
    fn create_macos(&self, shortcut: &Path) -> Result<(), Box<dyn Error>> {
        let executable = shortcut.join("Contents/MacOS/InstructionX");
        if let Some(parent) = executable.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&executable, self.launcher_text())?;
        let plist = shortcut.join("Contents/Info.plist");
        fs::write(plist, macos_plist())?;
        let mut permissions = fs::metadata(&executable)?.permissions();
        use std::os::unix::fs::PermissionsExt;
        permissions.set_mode(0o755);
        fs::set_permissions(executable, permissions)?;
        Ok(())
    }

    #[cfg(target_os = "linux")]
    fn create_linux(&self, shortcut: &Path) -> Result<(), Box<dyn Error>> {
        if let Some(parent) = shortcut.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(shortcut, self.launcher_text())?;
        Ok(())
    }

    #[cfg(not(target_os = "linux"))]
    fn create_linux(&self, _shortcut: &Path) -> Result<(), Box<dyn Error>> {
        Err("Unsupported platform".into())
    }

    #[cfg(not(windows))]
    fn create_windows(&self, _launchers: &Path, _shortcut: &Path) -> Result<(), Box<dyn Error>> {
        Err("Unsupported platform".into())
    }

    #[cfg(not(target_os = "macos"))]
    fn create_macos(&self, _shortcut: &Path) -> Result<(), Box<dyn Error>> {
        Err("Unsupported platform".into())
    }
}

fn desktop_directory() -> PathBuf {
    if cfg!(windows) {
        return std::env::var_os("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."))
            .join("Desktop");
    }
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Desktop")
}

#[cfg(target_os = "macos")]
fn macos_plist() -> &'static str {
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
     <plist version=\"1.0\"><dict>\n\
     <key>CFBundleName</key><string>InstructionX</string>\n\
     <key>CFBundleExecutable</key><string>InstructionX</string>\n\
     <key>CFBundleIconFile</key><string>logo</string>\n\
     </dict></plist>\n"
}
