//! Setup 的对外发布版本号，与框架版本相互独立。

pub const SETUP_VERSION: &str = "20261114-01";

const SETUP_PLATFORM: &str = if cfg!(windows) {
    "win"
} else if cfg!(target_os = "macos") {
    "macos"
} else {
    std::env::consts::OS
};
const SETUP_ARCHITECTURE: &str = if cfg!(target_arch = "x86_64") {
    "x86_64"
} else if cfg!(target_arch = "aarch64") {
    "aarch64"
} else {
    std::env::consts::ARCH
};

/// 返回包含日期序号、目标平台和架构的完整构建版本。
pub fn setup_build_version() -> String {
    format!("{SETUP_VERSION}.{SETUP_PLATFORM}.{SETUP_ARCHITECTURE}")
}
